from app import db
from datetime import datetime
import base64
import os
from cryptography.fernet import Fernet
import hashlib


def _get_fernet():
    from flask import current_app
    key = current_app.config['ENCRYPT_KEY'].encode()
    # 使用 SHA256 生成标准 32 字节 Fernet key
    hashed = hashlib.sha256(key).digest()
    fernet_key = base64.urlsafe_b64encode(hashed)
    return Fernet(fernet_key)


def encrypt_password(password):
    if not password:
        return ''
    f = _get_fernet()
    return f.encrypt(password.encode()).decode()


def decrypt_password(encrypted):
    if not encrypted:
        return ''
    try:
        f = _get_fernet()
        return f.decrypt(encrypted.encode()).decode()
    except Exception:
        return ''


class Server(db.Model):
    __tablename__ = 'servers'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), nullable=False)
    ip = db.Column(db.String(64), nullable=False)
    os_type = db.Column(db.String(16), nullable=False, default='linux')  # linux / windows / macos
    ssh_port = db.Column(db.Integer, default=22)  # Linux/macOS: SSH端口, Windows: WinRM端口
    username = db.Column(db.String(64), nullable=False)
    password_encrypted = db.Column(db.Text, default='')
    group = db.Column(db.String(64), default='默认分组')
    description = db.Column(db.String(256), default='')
    enabled = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    
    # 关联
    inspections = db.relationship('InspectionRecord', backref='server', lazy='dynamic',
                                   cascade='all, delete-orphan')
    alerts = db.relationship('Alert', backref='server', lazy='dynamic',
                              cascade='all, delete-orphan')

    def set_password(self, password):
        if password:
            self.password_encrypted = encrypt_password(password)

    def get_password(self):
        return decrypt_password(self.password_encrypted)

    @property
    def os_label(self):
        return {'linux': 'Linux', 'windows': 'Windows', 'macos': 'macOS'}.get(self.os_type, self.os_type)

    @property
    def os_icon(self):
        return {'linux': '🐧', 'windows': '🪟', 'macos': '🍎'}.get(self.os_type, '🖥️')

    @property
    def latest_inspection(self):
        return self.inspections.order_by(InspectionRecord.inspected_at.desc()).first()

    @property
    def unack_alerts_count(self):
        from app.models.alert import Alert
        return Alert.query.filter_by(server_id=self.id, acknowledged=False).count()

    def to_dict(self):
        latest = self.latest_inspection
        return {
            'id': self.id,
            'name': self.name,
            'ip': self.ip,
            'os_type': self.os_type,
            'os_label': self.os_label,
            'ssh_port': self.ssh_port,
            'username': self.username,
            'group': self.group,
            'description': self.description,
            'enabled': self.enabled,
            'status': latest.status if latest else 'unknown',
            'last_inspected': latest.inspected_at.strftime('%Y-%m-%d %H:%M') if latest else '从未巡检',
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M') if self.created_at else '',
        }


# 避免循环导入，在这里导入
from app.models.inspection import InspectionRecord
