from app import db
from datetime import datetime


class SystemSetting(db.Model):
    __tablename__ = 'system_settings'

    id = db.Column(db.Integer, primary_key=True)
    inspection_hour = db.Column(db.Integer, default=2)
    inspection_minute = db.Column(db.Integer, default=0)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    @classmethod
    def get(cls):
        return cls.query.first()
