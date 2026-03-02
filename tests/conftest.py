"""
pytest 全局配置与 fixtures
- 使用内存 SQLite，完全隔离，不影响生产数据库
- 提供已登录的 admin_client 和 viewer_client fixture
"""
import pytest
from app import create_app, db as _db
from app.config import Config


class TestConfig(Config):
    """测试专用配置：内存数据库、关闭调度器、CSRF 豁免"""
    TESTING = True
    WTF_CSRF_ENABLED = False
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    # 禁用 APScheduler，防止测试时启动定时任务
    SCHEDULER_API_ENABLED = False
    # 关闭调度器初始化
    _SKIP_SCHEDULER = True


@pytest.fixture(scope='function')
def app():
    """每个测试函数创建独立的 Flask app 实例，防止 session/cookie 跨测试泄露"""
    _app = create_app(TestConfig)
    ctx = _app.app_context()
    ctx.push()
    yield _app
    ctx.pop()


@pytest.fixture(scope='function')
def db(app):
    """每个测试函数前重建所有数据库表，确保数据隔离"""
    with app.app_context():
        _db.drop_all()
        _db.create_all()
        _init_test_data()
    yield _db
    with app.app_context():
        _db.session.remove()


def _init_test_data():
    """初始化测试所需的基础数据（admin 用户、viewer 用户、告警配置）"""
    from app.models.user import User
    from app.models.alert import AlertConfig

    # 管理员
    admin = User(username='admin', role='admin', display_name='管理员')
    admin.set_password('admin123')
    _db.session.add(admin)

    # 普通查看者
    viewer = User(username='viewer', role='viewer', display_name='查看者')
    viewer.set_password('viewer123')
    _db.session.add(viewer)

    # 默认告警配置
    config = AlertConfig()
    _db.session.add(config)

    _db.session.commit()


@pytest.fixture(scope='function')
def client(app, db):
    """未登录的测试客户端"""
    return app.test_client()


@pytest.fixture(scope='function')
def admin_client(app, db):
    """以 admin 身份登录的测试客户端"""
    c = app.test_client()
    c.post('/auth/login', data={'username': 'admin', 'password': 'admin123'}, follow_redirects=True)
    return c


@pytest.fixture(scope='function')
def viewer_client(app, db):
    """以 viewer 身份登录的测试客户端"""
    c = app.test_client()
    c.post('/auth/login', data={'username': 'viewer', 'password': 'viewer123'}, follow_redirects=True)
    return c
