from app import db
from datetime import datetime


class Alert(db.Model):
    __tablename__ = 'alerts'
    
    id = db.Column(db.Integer, primary_key=True)
    server_id = db.Column(db.Integer, db.ForeignKey('servers.id'), nullable=False, index=True)
    record_id = db.Column(db.Integer, db.ForeignKey('inspection_records.id'), nullable=True)
    level = db.Column(db.String(16), nullable=False)  # warning / critical
    metric = db.Column(db.String(32), default='')     # cpu / memory / disk / offline / service
    message = db.Column(db.String(512), nullable=False)
    value = db.Column(db.Float, default=0.0)          # 触发告警的值
    threshold = db.Column(db.Float, default=0.0)      # 阈值
    acknowledged = db.Column(db.Boolean, default=False)
    ack_by = db.Column(db.String(64), default='')
    ack_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.now, index=True)

    @property
    def level_label(self):
        return '严重' if self.level == 'critical' else '警告'

    @property
    def level_color(self):
        return 'danger' if self.level == 'critical' else 'warning'

    @property
    def metric_label(self):
        labels = {
            'cpu': 'CPU使用率',
            'memory': '内存使用率',
            'disk': '磁盘使用率',
            'offline': '主机离线',
            'service': '服务异常',
        }
        return labels.get(self.metric, self.metric)

    def to_dict(self):
        return {
            'id': self.id,
            'server_id': self.server_id,
            'server_name': self.server.name if self.server else '',
            'server_ip': self.server.ip if self.server else '',
            'record_id': self.record_id,
            'level': self.level,
            'level_label': self.level_label,
            'level_color': self.level_color,
            'metric': self.metric,
            'metric_label': self.metric_label,
            'message': self.message,
            'value': self.value,
            'threshold': self.threshold,
            'acknowledged': self.acknowledged,
            'ack_by': self.ack_by,
            'ack_at': self.ack_at.strftime('%Y-%m-%d %H:%M') if self.ack_at else '',
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M') if self.created_at else '',
        }


class AlertConfig(db.Model):
    __tablename__ = 'alert_config'
    
    id = db.Column(db.Integer, primary_key=True)
    cpu_warning = db.Column(db.Float, default=80.0)
    cpu_critical = db.Column(db.Float, default=95.0)
    mem_warning = db.Column(db.Float, default=85.0)
    mem_critical = db.Column(db.Float, default=95.0)
    disk_warning = db.Column(db.Float, default=80.0)
    disk_critical = db.Column(db.Float, default=95.0)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    @classmethod
    def get(cls):
        return cls.query.first()
