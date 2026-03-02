from app import db
from datetime import datetime
import json


class InspectionRecord(db.Model):
    __tablename__ = 'inspection_records'
    
    id = db.Column(db.Integer, primary_key=True)
    server_id = db.Column(db.Integer, db.ForeignKey('servers.id'), nullable=False, index=True)
    inspected_at = db.Column(db.DateTime, default=datetime.now, index=True)
    
    # 基础指标
    cpu_usage = db.Column(db.Float, default=0.0)       # CPU使用率%
    mem_total = db.Column(db.Float, default=0.0)       # 内存总量 MB
    mem_used = db.Column(db.Float, default=0.0)        # 已用内存 MB
    mem_usage = db.Column(db.Float, default=0.0)       # 内存使用率%
    load_avg = db.Column(db.String(64), default='')    # 负载均衡 1/5/15
    uptime = db.Column(db.String(128), default='')     # 运行时长
    
    # JSON 字段
    disk_info = db.Column(db.Text, default='[]')        # 磁盘信息 JSON
    open_ports = db.Column(db.Text, default='[]')       # 监听端口 JSON
    top_processes = db.Column(db.Text, default='[]')    # Top进程 JSON
    services = db.Column(db.Text, default='[]')         # 服务状态 JSON
    
    # 状态
    status = db.Column(db.String(16), default='unknown')  # normal/warning/critical/offline/unknown
    error_message = db.Column(db.Text, default='')
    duration = db.Column(db.Float, default=0.0)  # 巡检耗时秒
    
    triggered_by = db.Column(db.String(16), default='auto')  # auto / manual

    @property
    def disk_list(self):
        try:
            return json.loads(self.disk_info) if self.disk_info else []
        except Exception:
            return []

    @property
    def ports_list(self):
        try:
            return json.loads(self.open_ports) if self.open_ports else []
        except Exception:
            return []

    @property
    def processes_list(self):
        try:
            return json.loads(self.top_processes) if self.top_processes else []
        except Exception:
            return []

    @property
    def services_list(self):
        try:
            return json.loads(self.services) if self.services else []
        except Exception:
            return []

    @property
    def status_label(self):
        labels = {
            'normal': '正常',
            'warning': '警告',
            'critical': '严重',
            'offline': '离线',
            'unknown': '未知',
        }
        return labels.get(self.status, '未知')

    @property
    def status_color(self):
        colors = {
            'normal': 'success',
            'warning': 'warning',
            'critical': 'danger',
            'offline': 'secondary',
            'unknown': 'secondary',
        }
        return colors.get(self.status, 'secondary')

    @property
    def max_disk_usage(self):
        """获取最大磁盘使用率"""
        disks = self.disk_list
        if not disks:
            return 0
        return max(d.get('usage_pct', 0) for d in disks)

    def to_dict(self):
        return {
            'id': self.id,
            'server_id': self.server_id,
            'inspected_at': self.inspected_at.strftime('%Y-%m-%d %H:%M:%S') if self.inspected_at else '',
            'cpu_usage': round(self.cpu_usage, 1),
            'mem_total': round(self.mem_total, 0),
            'mem_used': round(self.mem_used, 0),
            'mem_usage': round(self.mem_usage, 1),
            'load_avg': self.load_avg,
            'uptime': self.uptime,
            'disk_info': self.disk_list,
            'open_ports': self.ports_list,
            'top_processes': self.processes_list,
            'services': self.services_list,
            'status': self.status,
            'status_label': self.status_label,
            'status_color': self.status_color,
            'error_message': self.error_message,
            'duration': round(self.duration, 2),
            'triggered_by': self.triggered_by,
            'max_disk_usage': self.max_disk_usage,
        }
