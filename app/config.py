import os
from datetime import timedelta

BASE_DIR = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'hospital-it-inspector-secret-key-2024'
    SQLALCHEMY_DATABASE_URI = 'sqlite:///' + os.path.join(BASE_DIR, 'data', 'inspector.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # 文件上传
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
    EXPORT_FOLDER = os.path.join(BASE_DIR, 'exports')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB
    
    # APScheduler
    SCHEDULER_API_ENABLED = True
    SCHEDULER_TIMEZONE = 'Asia/Shanghai'
    
    # 巡检默认时间（凌晨2点）
    INSPECTION_HOUR = 2
    INSPECTION_MINUTE = 0
    
    # 加密密钥（用于服务器密码加密存储）
    ENCRYPT_KEY = os.environ.get('ENCRYPT_KEY') or 'hospital-it-2024-enc-key-32chars!'
    
    # 静态资源
    STATIC_FOLDER = os.path.join(BASE_DIR, 'app', 'static')
    FONTS_FOLDER = os.path.join(BASE_DIR, 'app', 'static', 'fonts')
    
    # Session
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)
    
    # 告警默认阈值
    DEFAULT_CPU_WARNING = 80.0
    DEFAULT_CPU_CRITICAL = 95.0
    DEFAULT_MEM_WARNING = 85.0
    DEFAULT_MEM_CRITICAL = 95.0
    DEFAULT_DISK_WARNING = 80.0
    DEFAULT_DISK_CRITICAL = 95.0
