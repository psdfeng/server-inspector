import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from sqlalchemy import text
from app.config import Config

db = SQLAlchemy()
login_manager = LoginManager()
login_manager.login_view = 'auth.login'
login_manager.login_message = '请先登录'
login_manager.login_message_category = 'warning'


def create_app(config_class=Config):
    app = Flask(__name__, 
                template_folder='templates',
                static_folder='static')
    app.config.from_object(config_class)

    # 确保必要目录存在
    os.makedirs(app.config['EXPORT_FOLDER'], exist_ok=True)
    os.makedirs(os.path.join(os.path.dirname(os.path.dirname(__file__)), 'uploads'), exist_ok=True)
    os.makedirs(os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data'), exist_ok=True)

    db.init_app(app)
    login_manager.init_app(app)

    # 注册蓝图
    from app.routes.auth import auth_bp
    from app.routes.dashboard import dashboard_bp
    from app.routes.servers import servers_bp
    from app.routes.inspections import inspections_bp
    from app.routes.alerts import alerts_bp
    from app.routes.reports import reports_bp
    from app.routes.users import users_bp
    from app.routes.system import system_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(servers_bp)
    app.register_blueprint(inspections_bp)
    app.register_blueprint(alerts_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(users_bp)
    app.register_blueprint(system_bp)

    with app.app_context():
        db.create_all()
        _ensure_runtime_indexes()
        _init_default_data()
        
        # 启动定时任务
        from app.services.scheduler import init_scheduler
        init_scheduler(app)

    @app.context_processor
    def inject_nav_badges():
        from app.models.alert import Alert
        try:
            count = Alert.query.filter_by(acknowledged=False, level='critical').count()
        except Exception:
            count = 0
        return {'unack_critical_count': count}

    return app


def _init_default_data():
    """初始化默认数据（admin用户、默认告警配置）"""
    from flask import current_app
    from app.models.user import User
    from app.models.alert import AlertConfig
    from app.models.system_setting import SystemSetting
    
    # 创建默认管理员
    if not User.query.filter_by(username='admin').first():
        admin = User(username='admin', role='admin', display_name='系统管理员')
        admin.set_password('admin123')
        db.session.add(admin)
    
    # 创建默认告警配置
    if not AlertConfig.query.first():
        config = AlertConfig()
        db.session.add(config)

    # 创建系统配置（每日自动巡检时间）
    if not SystemSetting.query.first():
        setting = SystemSetting(
            inspection_hour=int(current_app.config.get('INSPECTION_HOUR', 2)),
            inspection_minute=int(current_app.config.get('INSPECTION_MINUTE', 0)),
        )
        db.session.add(setting)
    
    db.session.commit()


def _ensure_runtime_indexes():
    """为高频查询创建索引（兼容已有数据库）。"""
    stmts = [
        "CREATE INDEX IF NOT EXISTS idx_inspection_server_time ON inspection_records (server_id, inspected_at)",
        "CREATE INDEX IF NOT EXISTS idx_alerts_ack_level_created ON alerts (acknowledged, level, created_at)",
        "CREATE INDEX IF NOT EXISTS idx_alerts_ack_created ON alerts (acknowledged, created_at)",
        "CREATE INDEX IF NOT EXISTS idx_servers_ip ON servers (ip)",
    ]
    with db.engine.begin() as conn:
        for stmt in stmts:
            conn.execute(text(stmt))
