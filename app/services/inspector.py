from app import db
from app.models.server import Server
from app.models.inspection import InspectionRecord
from app.models.alert import Alert, AlertConfig
import paramiko
import json
import time
import re
import os
import socket
from datetime import datetime
import logging
try:
    import winrm
except Exception:
    winrm = None

logger = logging.getLogger(__name__)


def _ignored_service_patterns():
    """
    读取服务忽略规则。
    默认过滤“某某服务”类占位/已知无需关注的服务；
    也支持通过环境变量 INSPECTION_IGNORE_SERVICES 追加，逗号分隔。
    """
    defaults = ['某某服务']
    extra = os.environ.get('INSPECTION_IGNORE_SERVICES', '')
    extras = [s.strip() for s in extra.split(',') if s.strip()]
    return defaults + extras


def _is_ignored_service(name: str) -> bool:
    if not name:
        return True
    lowered = name.lower()
    for pattern in _ignored_service_patterns():
        p = pattern.strip()
        if not p:
            continue
        if p.lower() in lowered:
            return True
    return False


def _extract_first_number(text: str) -> float:
    if not text:
        return 0.0
    m = re.search(r'[-+]?\d+(?:[.,]\d+)?', text.strip())
    if not m:
        return 0.0
    token = m.group(0).replace(',', '.')
    try:
        return float(token)
    except Exception:
        return 0.0


def _clamp_percentage(value: float) -> float:
    try:
        v = float(value)
    except Exception:
        return 0.0
    if v < 0:
        return 0.0
    if v > 100:
        return 100.0
    return round(v, 1)


class Inspector:
    """服务器巡检引擎（支持 Linux / Windows / macOS SSH）"""
    
    def __init__(self, server: Server):
        self.server = server
        self.ssh = None
        self.winrm_session = None
        self.use_winrm = False
        self.timeout = 30
        self.winrm_endpoint = ''
        self.winrm_transport = ''

    def connect(self):
        if self.server.os_type == 'windows':
            self._connect_windows_winrm()
        else:
            self._connect_ssh()

    def _connect_ssh(self):
        self.ssh = paramiko.SSHClient()
        self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        password = self.server.get_password()
        self.ssh.connect(
            hostname=self.server.ip,
            port=self.server.ssh_port,
            username=self.server.username,
            password=password,
            timeout=self.timeout,
            auth_timeout=self.timeout,
            banner_timeout=self.timeout,
            allow_agent=False,
            look_for_keys=False
        )

    def _connect_windows_winrm(self):
        if winrm is None:
            raise RuntimeError("Windows巡检需要安装 pywinrm 依赖")
        password = self.server.get_password()
        if not password:
            raise RuntimeError("Windows巡检需要管理员账号密码")
        errors = []
        candidates = self._build_windows_winrm_candidates()
        for endpoint, transport, port in candidates:
            if not self._tcp_reachable(self.server.ip, port):
                errors.append(f"{endpoint} 不可达")
                continue
            try:
                session_kwargs = dict(
                    target=endpoint,
                    auth=(self.server.username, password),
                    transport=transport,
                    server_cert_validation='ignore',
                    read_timeout_sec=self.timeout,
                    operation_timeout_sec=min(20, self.timeout),
                )
                # plaintext/basic 模式在部分内网主机上可用
                if transport == 'plaintext':
                    session_kwargs['message_encryption'] = 'auto'

                session = winrm.Session(**session_kwargs)
                probe = session.run_ps("$os=(Get-CimInstance Win32_OperatingSystem).Caption; Write-Output ('OK|' + $os)")
                if probe.status_code == 0:
                    self.winrm_session = session
                    self.use_winrm = True
                    self.winrm_endpoint = endpoint
                    self.winrm_transport = transport
                    return
                err = probe.std_err.decode('utf-8', errors='replace').strip()
                errors.append(f"{endpoint} [{transport}] 状态码 {probe.status_code} {err}".strip())
            except Exception as e:
                errors.append(f"{endpoint} [{transport}] {e}")

        hint = "请确认目标机已启用 WinRM（5985/5986）并放通防火墙，RDP(3389)可用不代表可巡检。"
        details = "; ".join(errors[:4])
        raise RuntimeError(f"Windows WinRM连接失败。{hint} 尝试结果: {details}")

    def _build_windows_winrm_candidates(self):
        raw_port = self.server.ssh_port if self.server.ssh_port else 5985
        ports = []
        for p in (raw_port, 5985, 5986):
            if p and p not in ports:
                ports.append(p)

        candidates = []
        for p in ports:
            if p == 5986:
                schemes = ['https']
            elif p == 5985:
                schemes = ['http', 'https']
            else:
                schemes = ['http', 'https']
            for scheme in schemes:
                endpoint = f"{scheme}://{self.server.ip}:{p}/wsman"
                for transport in ('ntlm', 'plaintext'):
                    candidates.append((endpoint, transport, p))
        return candidates

    def _tcp_reachable(self, host: str, port: int, timeout: float = 1.5) -> bool:
        try:
            with socket.create_connection((host, int(port)), timeout=timeout):
                return True
        except Exception:
            return False

    def disconnect(self):
        if self.ssh:
            try:
                self.ssh.close()
            except Exception:
                pass
            self.ssh = None
        self.winrm_session = None
        self.use_winrm = False
        self.winrm_endpoint = ''
        self.winrm_transport = ''

    def exec(self, cmd, powershell=False):
        """执行命令并返回输出"""
        if self.use_winrm and self.winrm_session is not None:
            if powershell:
                resp = self.winrm_session.run_ps(cmd)
            else:
                resp = self.winrm_session.run_cmd(cmd)
            out = resp.std_out.decode('utf-8', errors='replace').strip()
            err = resp.std_err.decode('utf-8', errors='replace').strip()
            return out or err
        stdin, stdout, stderr = self.ssh.exec_command(cmd, timeout=self.timeout)
        out = stdout.read().decode('utf-8', errors='replace').strip()
        return out

    def inspect(self) -> dict:
        """执行巡检，返回巡检结果字典"""
        start = time.time()
        result = {
            'cpu_usage': 0.0, 'mem_total': 0.0, 'mem_used': 0.0, 'mem_usage': 0.0,
            'load_avg': '', 'uptime': '', 'disk_info': [], 'open_ports': [],
            'top_processes': [], 'services': [], 'status': 'unknown', 'error_message': '',
        }
        try:
            self.connect()
            if self.server.os_type == 'linux':
                result = self._inspect_linux()
            elif self.server.os_type == 'macos':
                result = self._inspect_macos()
            elif self.server.os_type == 'windows':
                result = self._inspect_windows()
            else:
                raise ValueError(f"不支持的系统类型: {self.server.os_type}")
            result['status'] = 'normal'
        except Exception as e:
            logger.error(f"巡检失败 {self.server.ip}: {e}")
            result['status'] = 'offline'
            result['error_message'] = str(e)
        finally:
            self.disconnect()
        result['duration'] = round(time.time() - start, 2)
        return result

    def _inspect_linux(self) -> dict:
        result = {}
        
        # CPU 使用率
        try:
            cpu_out = self.exec("top -bn1 | grep 'Cpu(s)' | awk '{print $2+$4}'")
            if not cpu_out:
                cpu_out = self.exec("top -bn1 | grep '%Cpu' | awk '{print $2}'")
            result['cpu_usage'] = float(cpu_out.split('\n')[0]) if cpu_out else 0.0
        except Exception:
            result['cpu_usage'] = 0.0

        # 内存
        try:
            mem_out = self.exec("free -m | grep Mem")
            parts = mem_out.split()
            mem_total = float(parts[1])
            mem_used = float(parts[2])
            result['mem_total'] = mem_total
            result['mem_used'] = mem_used
            result['mem_usage'] = round(mem_used / mem_total * 100, 1) if mem_total > 0 else 0.0
        except Exception:
            result['mem_total'] = result['mem_used'] = result['mem_usage'] = 0.0

        # 负载和运行时间
        try:
            uptime_out = self.exec("uptime")
            result['uptime'] = uptime_out
            load_match = re.search(r'load average[s]?:\s*([\d.]+)[,\s]+([\d.]+)[,\s]+([\d.]+)', uptime_out)
            if load_match:
                result['load_avg'] = f"{load_match.group(1)} {load_match.group(2)} {load_match.group(3)}"
        except Exception:
            result['uptime'] = result['load_avg'] = ''

        # 磁盘
        try:
            df_out = self.exec("df -h --output=source,size,used,avail,pcent,target 2>/dev/null | tail -n +2")
            disks = []
            for line in df_out.splitlines():
                parts = line.split()
                if len(parts) >= 6 and parts[5].startswith('/'):
                    mount = parts[5]
                    if any(skip in mount for skip in ['/proc', '/sys', '/dev/pts', '/run', '/snap']):
                        continue
                    usage_str = parts[4].replace('%', '')
                    try:
                        usage_pct = float(usage_str)
                    except Exception:
                        usage_pct = 0.0
                    disks.append({
                        'device': parts[0], 'size': parts[1], 'used': parts[2],
                        'avail': parts[3], 'usage_pct': usage_pct, 'mount': mount
                    })
            result['disk_info'] = disks
        except Exception:
            result['disk_info'] = []

        # 监听端口
        try:
            port_out = self.exec("ss -tlnp 2>/dev/null | tail -n +2 || netstat -tlnp 2>/dev/null | tail -n +3")
            ports = []
            for line in port_out.splitlines()[:20]:
                parts = line.split()
                if len(parts) >= 4:
                    local = parts[3] if 'ss' in port_out or ':' in parts[3] else parts[3]
                    port_match = re.search(r':(\d+)$', local)
                    if port_match:
                        ports.append({'port': int(port_match.group(1)), 'address': local})
            seen = set()
            unique_ports = []
            for p in ports:
                if p['port'] not in seen:
                    seen.add(p['port'])
                    unique_ports.append(p)
            result['open_ports'] = unique_ports[:30]
        except Exception:
            result['open_ports'] = []

        # Top 进程（CPU占用最高）
        try:
            ps_out = self.exec("ps aux --sort=-%cpu | head -11 | tail -n +2")
            processes = []
            for line in ps_out.splitlines():
                parts = line.split(None, 10)
                if len(parts) >= 11:
                    processes.append({
                        'user': parts[0], 'pid': parts[1],
                        'cpu': parts[2], 'mem': parts[3], 'cmd': parts[10][:80]
                    })
            result['top_processes'] = processes
        except Exception:
            result['top_processes'] = []

        # 失败的系统服务
        try:
            svc_out = self.exec("systemctl list-units --state=failed --no-legend 2>/dev/null | head -20")
            services = []
            for line in svc_out.splitlines():
                parts = line.split()
                if len(parts) >= 4:
                    services.append({
                        'name': parts[0], 'load': parts[1],
                        'active': parts[2], 'sub': parts[3], 'status': 'failed'
                    })
            result['services'] = services
        except Exception:
            result['services'] = []

        return result

    def _inspect_macos(self) -> dict:
        result = {}

        # CPU 使用率
        try:
            cpu_out = self.exec("top -l 2 -n 0 | grep 'CPU usage' | tail -1")
            cpu_match = re.search(r'([\d.]+)% user,\s*([\d.]+)% sys', cpu_out)
            if cpu_match:
                result['cpu_usage'] = round(float(cpu_match.group(1)) + float(cpu_match.group(2)), 1)
            else:
                result['cpu_usage'] = 0.0
        except Exception:
            result['cpu_usage'] = 0.0

        # 内存（vm_stat）
        try:
            vm_out = self.exec("vm_stat")
            page_size_match = re.search(r'page size of (\d+) bytes', vm_out)
            page_size = int(page_size_match.group(1)) if page_size_match else 4096

            pages = {}
            for line in vm_out.splitlines():
                m = re.match(r'^(.*?)\:\s+([0-9\.]+)\.?$', line.strip())
                if not m:
                    continue
                key = m.group(1).strip()
                val = int(float(m.group(2)))
                pages[key] = val

            pages_active = pages.get('Pages active', 0)
            pages_inactive = pages.get('Pages inactive', 0)
            pages_wired = pages.get('Pages wired down', 0)
            pages_compressor = pages.get('Pages occupied by compressor', 0)
            pages_free = pages.get('Pages free', 0)
            pages_spec = pages.get('Pages speculative', 0)

            total_pages = pages_active + pages_inactive + pages_wired + pages_compressor + pages_free + pages_spec
            used_pages = pages_active + pages_wired + pages_compressor

            mem_total = total_pages * page_size / 1024 / 1024
            mem_used = used_pages * page_size / 1024 / 1024
            result['mem_total'] = round(mem_total, 0)
            result['mem_used'] = round(mem_used, 0)
            result['mem_usage'] = round(mem_used / mem_total * 100, 1) if mem_total > 0 else 0.0
        except Exception:
            result['mem_total'] = result['mem_used'] = result['mem_usage'] = 0.0

        # 负载和运行时间
        try:
            uptime_out = self.exec("uptime")
            result['uptime'] = uptime_out
            load_match = re.search(r'load averages?:\s*([\d.]+)\s+([\d.]+)\s+([\d.]+)', uptime_out)
            if load_match:
                result['load_avg'] = f"{load_match.group(1)} {load_match.group(2)} {load_match.group(3)}"
            else:
                result['load_avg'] = ''
        except Exception:
            result['uptime'] = result['load_avg'] = ''

        # 磁盘
        try:
            # 使用 POSIX 输出格式，避免不同 macOS 版本列格式差异
            df_out = self.exec("df -hP 2>/dev/null | tail -n +2")
            disks = []
            for line in df_out.splitlines():
                parts = line.split()
                if len(parts) < 6:
                    continue
                device, size, used, avail, usage_raw, mount = parts[0], parts[1], parts[2], parts[3], parts[4], parts[5]

                # 仅统计真实块设备，排除 devfs/map 等伪文件系统
                if not device.startswith('/dev/'):
                    continue
                if not mount.startswith('/'):
                    continue
                # 排除系统/临时挂载点，避免把只读卷或虚拟卷的 100% 当作业务磁盘
                if mount.startswith('/System/Volumes') or mount.startswith('/private/var/vm') or mount == '/dev':
                    continue
                usage_str = usage_raw.replace('%', '')
                try:
                    usage_pct = float(usage_str)
                except Exception:
                    usage_pct = 0.0
                disks.append({
                    'device': device, 'size': size, 'used': used,
                    'avail': avail, 'usage_pct': usage_pct, 'mount': mount
                })
            result['disk_info'] = disks
        except Exception:
            result['disk_info'] = []

        # 监听端口
        try:
            port_out = self.exec("lsof -nP -iTCP -sTCP:LISTEN 2>/dev/null | tail -n +2")
            ports = []
            for line in port_out.splitlines()[:50]:
                parts = line.split()
                if len(parts) < 9:
                    continue
                local = parts[8]
                port_match = re.search(r':(\d+)(?:->|$)', local)
                if port_match:
                    ports.append({'port': int(port_match.group(1)), 'address': local})
            seen = set()
            unique_ports = []
            for p in ports:
                if p['port'] not in seen:
                    seen.add(p['port'])
                    unique_ports.append(p)
            result['open_ports'] = unique_ports[:30]
        except Exception:
            result['open_ports'] = []

        # Top 进程（CPU 占用）
        try:
            ps_out = self.exec("ps aux -arcpu | head -11 | tail -n +2")
            processes = []
            for line in ps_out.splitlines():
                parts = line.split(None, 10)
                if len(parts) >= 11:
                    processes.append({
                        'user': parts[0], 'pid': parts[1],
                        'cpu': parts[2], 'mem': parts[3], 'cmd': parts[10][:80]
                    })
            result['top_processes'] = processes
        except Exception:
            result['top_processes'] = []

        # 异常 launchd 服务（返回码非 0）
        try:
            svc_out = self.exec("launchctl list | awk '$1 != \"0\" {print $3}' | head -20")
            services = []
            for line in svc_out.splitlines():
                name = line.strip()
                if name and not _is_ignored_service(name):
                    services.append({
                        'name': name, 'load': 'loaded',
                        'active': 'inactive', 'sub': 'error', 'status': 'failed'
                    })
            result['services'] = services
        except Exception:
            result['services'] = []

        return result

    def _inspect_windows(self) -> dict:
        result = {}

        # CPU 使用率（PowerShell）
        try:
            cpu_out = self.exec(
                "$v=(Get-Counter '\\Processor(_Total)\\% Processor Time' -SampleInterval 1 -MaxSamples 2).CounterSamples | Select-Object -Last 1 -ExpandProperty CookedValue; [math]::Round($v,1)",
                powershell=True
            )
            cpu_val = _extract_first_number(cpu_out)
            if cpu_val <= 0:
                cpu_fallback = self.exec(
                    "Get-CimInstance Win32_Processor | Measure-Object -Property LoadPercentage -Average | Select-Object -ExpandProperty Average",
                    powershell=True
                )
                cpu_val = _extract_first_number(cpu_fallback)
            result['cpu_usage'] = _clamp_percentage(cpu_val)
        except Exception:
            result['cpu_usage'] = 0.0

        # 内存
        try:
            mem_out = self.exec(
                "$os=Get-CimInstance Win32_OperatingSystem; Write-Output ('{0} {1}' -f $os.TotalVisibleMemorySize, $os.FreePhysicalMemory)",
                powershell=True
            )
            parts = mem_out.strip().split()
            mem_total = float(parts[0]) / 1024  # KB -> MB
            mem_free = float(parts[1]) / 1024
            mem_used = mem_total - mem_free
            result['mem_total'] = round(mem_total, 0)
            result['mem_used'] = round(mem_used, 0)
            result['mem_usage'] = round(mem_used / mem_total * 100, 1) if mem_total > 0 else 0.0
        except Exception:
            result['mem_total'] = result['mem_used'] = result['mem_usage'] = 0.0

        # 运行时间
        try:
            uptime_out = self.exec(
                "(Get-Date) - (gcim Win32_OperatingSystem).LastBootUpTime | Select-Object -ExpandProperty TotalHours",
                powershell=True
            )
            hours = float(uptime_out.strip())
            days = int(hours // 24)
            hrs = int(hours % 24)
            result['uptime'] = f"已运行 {days} 天 {hrs} 小时"
            result['load_avg'] = ''
        except Exception:
            result['uptime'] = result['load_avg'] = ''

        # 磁盘
        try:
            disk_out = self.exec(
                "Get-PSDrive -PSProvider FileSystem | Select-Object Name,@{N='Used';E={[math]::Round($_.Used/1GB,2)}},@{N='Free';E={[math]::Round($_.Free/1GB,2)}} | ConvertTo-Csv -NoTypeInformation",
                powershell=True
            )
            disks = []
            for line in disk_out.splitlines()[1:]:
                parts = [p.strip('"') for p in line.split(',')]
                if len(parts) >= 3:
                    try:
                        used = float(parts[1])
                        free = float(parts[2])
                        total = used + free
                        pct = round(used / total * 100, 1) if total > 0 else 0
                        disks.append({
                            'device': parts[0] + ':', 'size': f"{total:.1f}G",
                            'used': f"{used:.1f}G", 'avail': f"{free:.1f}G",
                            'usage_pct': pct, 'mount': parts[0] + ':\\'
                        })
                    except Exception:
                        continue
            result['disk_info'] = disks
        except Exception:
            result['disk_info'] = []

        # 停止的服务
        try:
            svc_out = self.exec(
                "Get-Service | Where-Object {$_.StartType -eq 'Automatic' -and $_.Status -ne 'Running'} | Select-Object Name,Status | ConvertTo-Csv -NoTypeInformation | Select-Object -First 21",
                powershell=True
            )
            services = []
            for line in svc_out.splitlines()[1:]:
                parts = [p.strip('"') for p in line.split(',')]
                if len(parts) >= 2:
                    services.append({'name': parts[0], 'status': parts[1], 'active': 'inactive', 'load': 'loaded', 'sub': 'dead'})
            result['services'] = services
        except Exception:
            result['services'] = []

        # Top 进程
        try:
            ps_out = self.exec(
                "$lp=(Get-CimInstance Win32_ComputerSystem).NumberOfLogicalProcessors; "
                "if(-not $lp -or $lp -lt 1){$lp=1}; "
                "Get-CimInstance Win32_PerfFormattedData_PerfProc_Process | "
                "Where-Object {$_.Name -notin @('_Total','Idle')} | "
                "Sort-Object PercentProcessorTime -Descending | "
                "Select-Object -First 10 "
                "@{N='Name';E={$_.Name}},"
                "@{N='Id';E={$_.IDProcess}},"
                "@{N='CPU';E={[math]::Round(($_.PercentProcessorTime / $lp),1)}},"
                "@{N='WorkingSetMB';E={[math]::Round(($_.WorkingSetPrivate/1MB),1)}} | "
                "ConvertTo-Csv -NoTypeInformation",
                powershell=True
            )
            processes = []
            for line in ps_out.splitlines()[1:]:
                parts = [p.strip('"') for p in line.split(',')]
                if len(parts) >= 4:
                    try:
                        cpu = _clamp_percentage(_extract_first_number(parts[2]))
                        mem = round(float(parts[3]) if parts[3] else 0, 1)
                    except Exception:
                        cpu = mem = 0
                    processes.append({'user': 'SYSTEM', 'pid': parts[1], 'cpu': str(cpu), 'mem': f"{mem}MB", 'cmd': parts[0]})
            result['top_processes'] = processes
        except Exception:
            result['top_processes'] = []

        try:
            port_out = self.exec(
                "Get-NetTCPConnection -State Listen | Select-Object -First 30 LocalAddress,LocalPort | ConvertTo-Csv -NoTypeInformation",
                powershell=True
            )
            ports = []
            for line in port_out.splitlines()[1:]:
                parts = [p.strip('"') for p in line.split(',')]
                if len(parts) >= 2 and parts[1].isdigit():
                    ports.append({'port': int(parts[1]), 'address': f"{parts[0]}:{parts[1]}"})
            result['open_ports'] = ports
        except Exception:
            result['open_ports'] = []
        return result


def run_inspection(server_id: int, triggered_by: str = 'auto'):
    """执行单台服务器巡检并保存结果"""
    from flask import current_app
    
    server = Server.query.get(server_id)
    if not server or not server.enabled:
        return None

    inspector = Inspector(server)
    raw = inspector.inspect()

    record = InspectionRecord(
        server_id=server_id,
        inspected_at=datetime.now(),
        cpu_usage=raw.get('cpu_usage', 0),
        mem_total=raw.get('mem_total', 0),
        mem_used=raw.get('mem_used', 0),
        mem_usage=raw.get('mem_usage', 0),
        load_avg=raw.get('load_avg', ''),
        uptime=raw.get('uptime', ''),
        disk_info=json.dumps(raw.get('disk_info', []), ensure_ascii=False),
        open_ports=json.dumps(raw.get('open_ports', []), ensure_ascii=False),
        top_processes=json.dumps(raw.get('top_processes', []), ensure_ascii=False),
        services=json.dumps(raw.get('services', []), ensure_ascii=False),
        status=raw.get('status', 'unknown'),
        error_message=raw.get('error_message', ''),
        duration=raw.get('duration', 0),
        triggered_by=triggered_by,
    )

    # 判断告警级别
    if raw['status'] != 'offline':
        config = AlertConfig.get()
        if not config:
            config = AlertConfig()
        record.status = _evaluate_status(raw, config)
        _generate_alerts(server, record, raw, config)

    db.session.add(record)
    db.session.commit()
    return record


def _evaluate_status(raw: dict, config: AlertConfig) -> str:
    status = 'normal'
    cpu = raw.get('cpu_usage', 0)
    mem = raw.get('mem_usage', 0)
    disks = raw.get('disk_info', [])
    max_disk = max((d.get('usage_pct', 0) for d in disks), default=0)

    if (cpu >= config.cpu_critical or mem >= config.mem_critical or max_disk >= config.disk_critical):
        status = 'critical'
    elif (cpu >= config.cpu_warning or mem >= config.mem_warning or max_disk >= config.disk_warning):
        status = 'warning'
    
    if raw.get('services'):
        if status == 'normal':
            status = 'warning'
    return status


def _generate_alerts(server: Server, record: InspectionRecord, raw: dict, config: AlertConfig):
    alerts = []
    cpu = raw.get('cpu_usage', 0)
    mem = raw.get('mem_usage', 0)
    disks = raw.get('disk_info', [])

    def make_alert(level, metric, message, value, threshold):
        return Alert(
            server_id=server.id,
            record_id=record.id,
            level=level,
            metric=metric,
            message=message,
            value=value,
            threshold=threshold,
        )

    if cpu >= config.cpu_critical:
        alerts.append(make_alert('critical', 'cpu', f"CPU使用率 {cpu:.1f}% 超过严重阈值 {config.cpu_critical}%", cpu, config.cpu_critical))
    elif cpu >= config.cpu_warning:
        alerts.append(make_alert('warning', 'cpu', f"CPU使用率 {cpu:.1f}% 超过警告阈值 {config.cpu_warning}%", cpu, config.cpu_warning))

    if mem >= config.mem_critical:
        alerts.append(make_alert('critical', 'memory', f"内存使用率 {mem:.1f}% 超过严重阈值 {config.mem_critical}%", mem, config.mem_critical))
    elif mem >= config.mem_warning:
        alerts.append(make_alert('warning', 'memory', f"内存使用率 {mem:.1f}% 超过警告阈值 {config.mem_warning}%", mem, config.mem_warning))

    for disk in disks:
        d_pct = disk.get('usage_pct', 0)
        mount = disk.get('mount', '')
        if d_pct >= config.disk_critical:
            alerts.append(make_alert('critical', 'disk', f"磁盘 {mount} 使用率 {d_pct:.1f}% 超过严重阈值 {config.disk_critical}%", d_pct, config.disk_critical))
        elif d_pct >= config.disk_warning:
            alerts.append(make_alert('warning', 'disk', f"磁盘 {mount} 使用率 {d_pct:.1f}% 超过警告阈值 {config.disk_warning}%", d_pct, config.disk_warning))

    if raw.get('services'):
        for svc in raw['services']:
            alerts.append(make_alert('warning', 'service', f"服务 {svc.get('name', '')} 处于异常状态", 0, 0))

    for a in alerts:
        db.session.add(a)


def run_all_inspections(triggered_by: str = 'auto'):
    """巡检所有启用的服务器"""
    servers = Server.query.filter_by(enabled=True).all()
    results = []
    for server in servers:
        try:
            r = run_inspection(server.id, triggered_by)
            results.append({'server_id': server.id, 'status': r.status if r else 'error'})
        except Exception as e:
            logger.error(f"巡检服务器 {server.id} 失败: {e}")
            results.append({'server_id': server.id, 'status': 'error'})
    return results
