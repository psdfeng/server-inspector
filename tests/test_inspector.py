"""
测试：巡检引擎 OS 分发逻辑（Linux / Windows / macOS）
"""

from app.services.inspector import Inspector
import app.services.inspector as inspector_module


class _DummyServer:
    def __init__(self, os_type):
        self.os_type = os_type
        self.ip = '127.0.0.1'
        self.ssh_port = 22
        self.username = 'u'

    def get_password(self):
        return ''


def test_inspector_dispatch_linux(monkeypatch):
    server = _DummyServer('linux')
    inspector = Inspector(server)

    monkeypatch.setattr(inspector, 'connect', lambda: None)
    monkeypatch.setattr(inspector, 'disconnect', lambda: None)
    monkeypatch.setattr(inspector, '_inspect_linux', lambda: {'cpu_usage': 1})
    monkeypatch.setattr(inspector, '_inspect_windows', lambda: {'cpu_usage': 2})
    monkeypatch.setattr(inspector, '_inspect_macos', lambda: {'cpu_usage': 3})

    result = inspector.inspect()
    assert result['cpu_usage'] == 1
    assert result['status'] == 'normal'


def test_inspector_dispatch_windows(monkeypatch):
    server = _DummyServer('windows')
    inspector = Inspector(server)

    monkeypatch.setattr(inspector, 'connect', lambda: None)
    monkeypatch.setattr(inspector, 'disconnect', lambda: None)
    monkeypatch.setattr(inspector, '_inspect_linux', lambda: {'cpu_usage': 1})
    monkeypatch.setattr(inspector, '_inspect_windows', lambda: {'cpu_usage': 2})
    monkeypatch.setattr(inspector, '_inspect_macos', lambda: {'cpu_usage': 3})

    result = inspector.inspect()
    assert result['cpu_usage'] == 2
    assert result['status'] == 'normal'


def test_inspector_dispatch_macos(monkeypatch):
    server = _DummyServer('macos')
    inspector = Inspector(server)

    monkeypatch.setattr(inspector, 'connect', lambda: None)
    monkeypatch.setattr(inspector, 'disconnect', lambda: None)
    monkeypatch.setattr(inspector, '_inspect_linux', lambda: {'cpu_usage': 1})
    monkeypatch.setattr(inspector, '_inspect_windows', lambda: {'cpu_usage': 2})
    monkeypatch.setattr(inspector, '_inspect_macos', lambda: {'cpu_usage': 3})

    result = inspector.inspect()
    assert result['cpu_usage'] == 3
    assert result['status'] == 'normal'


def test_inspector_unknown_os_returns_offline(monkeypatch):
    server = _DummyServer('solaris')
    inspector = Inspector(server)

    monkeypatch.setattr(inspector, 'connect', lambda: None)
    monkeypatch.setattr(inspector, 'disconnect', lambda: None)

    result = inspector.inspect()
    assert result['status'] == 'offline'
    assert '不支持的系统类型' in result['error_message']


def test_macos_disk_ignore_pseudo_filesystems(monkeypatch):
    server = _DummyServer('macos')
    inspector = Inspector(server)

    fake_outputs = {
        "top -l 2 -n 0 | grep 'CPU usage' | tail -1": "CPU usage: 7.0% user, 3.0% sys, 90.0% idle",
        "vm_stat": (
            "Mach Virtual Memory Statistics: (page size of 4096 bytes)\n"
            "Pages free: 100000.\n"
            "Pages active: 100000.\n"
            "Pages inactive: 100000.\n"
            "Pages wired down: 100000.\n"
            "Pages occupied by compressor: 100000.\n"
            "Pages speculative: 0.\n"
        ),
        "uptime": "20:00  up 1 day, 2 users, load averages: 1.00 0.80 0.60",
        "df -hP 2>/dev/null | tail -n +2": (
            "devfs           375Ki  375Ki    0Bi 100% /dev\n"
            "/dev/disk3s5s1  460Gi  200Gi  260Gi  43% /\n"
            "/dev/disk3s4    460Gi  460Gi    0Bi 100% /System/Volumes/Update\n"
        ),
        "lsof -nP -iTCP -sTCP:LISTEN 2>/dev/null | tail -n +2": "",
        "ps aux -arcpu | head -11 | tail -n +2": "",
        "launchctl list | awk '$1 != \"0\" {print $3}' | head -20": "",
    }

    monkeypatch.setattr(inspector, 'exec', lambda cmd: fake_outputs.get(cmd, ""))

    result = inspector._inspect_macos()
    assert len(result['disk_info']) == 1
    assert result['disk_info'][0]['mount'] == '/'
    assert result['disk_info'][0]['usage_pct'] == 43.0


def test_macos_ignore_known_service_alerts(monkeypatch):
    server = _DummyServer('macos')
    inspector = Inspector(server)

    fake_outputs = {
        "top -l 2 -n 0 | grep 'CPU usage' | tail -1": "CPU usage: 7.0% user, 3.0% sys, 90.0% idle",
        "vm_stat": (
            "Mach Virtual Memory Statistics: (page size of 4096 bytes)\n"
            "Pages free: 100000.\n"
            "Pages active: 100000.\n"
            "Pages inactive: 100000.\n"
            "Pages wired down: 100000.\n"
            "Pages occupied by compressor: 100000.\n"
            "Pages speculative: 0.\n"
        ),
        "uptime": "20:00  up 1 day, 2 users, load averages: 1.00 0.80 0.60",
        "df -hP 2>/dev/null | tail -n +2": "/dev/disk3s5s1  460Gi  200Gi  260Gi  43% /\n",
        "lsof -nP -iTCP -sTCP:LISTEN 2>/dev/null | tail -n +2": "",
        "ps aux -arcpu | head -11 | tail -n +2": "",
        "launchctl list | awk '$1 != \"0\" {print $3}' | head -20": (
            "com.example.某某服务.agent\n"
            "com.company.real_failed_service\n"
        ),
    }

    monkeypatch.setattr(inspector, 'exec', lambda cmd: fake_outputs.get(cmd, ""))
    result = inspector._inspect_macos()

    assert len(result['services']) == 1
    assert result['services'][0]['name'] == 'com.company.real_failed_service'


def test_windows_winrm_candidates_include_common_ports():
    server = _DummyServer('windows')
    server.ip = '10.0.0.10'
    server.ssh_port = 3389
    inspector = Inspector(server)
    candidates = inspector._build_windows_winrm_candidates()
    endpoints = [c[0] for c in candidates]

    assert 'http://10.0.0.10:5985/wsman' in endpoints
    assert 'https://10.0.0.10:5986/wsman' in endpoints


def test_windows_connect_fallback_to_5985(monkeypatch):
    class _Resp:
        def __init__(self, code=0, out=b'OK', err=b''):
            self.status_code = code
            self.std_out = out
            self.std_err = err

    class _Session:
        def __init__(self, **kwargs):
            self.target = kwargs['target']

        def run_ps(self, _cmd):
            if ':5985/' in self.target:
                return _Resp(0, b'OK|Windows Server 2019')
            return _Resp(1, b'', b'bad endpoint')

    class _FakeWinRM:
        Session = _Session

    server = _DummyServer('windows')
    server.ip = '10.0.0.11'
    server.ssh_port = 3389  # 用户误填 RDP 端口
    server.username = 'Administrator'
    server.get_password = lambda: 'pass123'

    inspector = Inspector(server)
    monkeypatch.setattr(inspector_module, 'winrm', _FakeWinRM())
    monkeypatch.setattr(inspector, '_tcp_reachable', lambda host, port, timeout=1.5: True)

    inspector._connect_windows_winrm()
    assert inspector.use_winrm is True
    assert ':5985/' in inspector.winrm_endpoint


def test_windows_connect_failure_message_has_winrm_hint(monkeypatch):
    class _Resp:
        def __init__(self, code=1, out=b'', err=b'failed'):
            self.status_code = code
            self.std_out = out
            self.std_err = err

    class _Session:
        def __init__(self, **kwargs):
            self.target = kwargs['target']

        def run_ps(self, _cmd):
            return _Resp(1, b'', b'auth failed')

    class _FakeWinRM:
        Session = _Session

    server = _DummyServer('windows')
    server.ip = '10.0.0.12'
    server.ssh_port = 5985
    server.username = 'Administrator'
    server.get_password = lambda: 'badpass'

    inspector = Inspector(server)
    monkeypatch.setattr(inspector_module, 'winrm', _FakeWinRM())
    monkeypatch.setattr(inspector, '_tcp_reachable', lambda host, port, timeout=1.5: True)

    try:
        inspector._connect_windows_winrm()
        assert False, "expected RuntimeError"
    except RuntimeError as e:
        msg = str(e)
        assert 'WinRM' in msg
        assert '3389' in msg


def test_windows_cpu_and_process_cpu_are_clamped(monkeypatch):
    server = _DummyServer('windows')
    inspector = Inspector(server)

    def fake_exec(cmd, powershell=False):
        if "Get-Counter '\\Processor(_Total)\\% Processor Time'" in cmd:
            return "146512.7"
        if "Get-CimInstance Win32_Processor" in cmd:
            return "88"
        if "$os=Get-CimInstance Win32_OperatingSystem" in cmd:
            return "8192000 4096000"
        if "(Get-Date) - (gcim Win32_OperatingSystem).LastBootUpTime" in cmd:
            return "49"
        if "Get-PSDrive -PSProvider FileSystem" in cmd:
            return "\"Name\",\"Used\",\"Free\"\n\"C\",\"100\",\"100\""
        if "Get-Service | Where-Object" in cmd:
            return "\"Name\",\"Status\""
        if "$lp=(Get-CimInstance Win32_ComputerSystem).NumberOfLogicalProcessors" in cmd:
            return "\"Name\",\"Id\",\"CPU\",\"WorkingSetMB\"\n\"sqlservr\",\"1234\",\"146512.7\",\"512.5\""
        if "Get-NetTCPConnection -State Listen" in cmd:
            return "\"LocalAddress\",\"LocalPort\"\n\"0.0.0.0\",\"3389\""
        return ""

    monkeypatch.setattr(inspector, 'exec', fake_exec)
    result = inspector._inspect_windows()

    assert result['cpu_usage'] == 100.0
    assert len(result['top_processes']) == 1
    assert result['top_processes'][0]['cpu'] == '100.0'
