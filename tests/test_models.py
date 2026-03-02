"""
测试：数据模型单元测试（不涉及 HTTP 请求）
"""
import json
import pytest


class TestUserModel:
    def test_set_and_check_password(self, db, app):
        from app.models.user import User
        with app.app_context():
            u = User(username='testuser', role='viewer', display_name='Test')
            u.set_password('mypassword')
            assert u.check_password('mypassword') is True
            assert u.check_password('wrong') is False

    def test_is_admin_property(self, db, app):
        from app.models.user import User
        with app.app_context():
            admin = User(username='a', role='admin', display_name='A')
            admin.set_password('x')
            viewer = User(username='b', role='viewer', display_name='B')
            viewer.set_password('x')
            assert admin.is_admin is True
            assert viewer.is_admin is False

    def test_to_dict_fields(self, db, app):
        from app.models.user import User
        from app import db as _db
        with app.app_context():
            u = User(username='dictuser', role='admin', display_name='Dict')
            u.set_password('123456')
            _db.session.add(u)
            _db.session.commit()
            d = u.to_dict()
            assert d['username'] == 'dictuser'
            assert d['role'] == 'admin'
            assert d['role_label'] == '管理员'
            assert 'created_at' in d


class TestServerModel:
    def test_password_encrypt_decrypt(self, db, app):
        from app.models.server import Server
        from app import db as _db
        with app.app_context():
            s = Server(name='srv', ip='1.2.3.4', os_type='linux',
                       username='root', ssh_port=22)
            s.set_password('secret123')
            _db.session.add(s)
            _db.session.commit()
            # 密文不应等于明文
            assert s.password_encrypted != 'secret123'
            assert s.get_password() == 'secret123'

    def test_empty_password(self, db, app):
        from app.models.server import Server
        from app import db as _db
        with app.app_context():
            s = Server(name='s2', ip='2.3.4.5', os_type='windows',
                       username='Administrator', ssh_port=22)
            _db.session.add(s)
            _db.session.commit()
            assert s.get_password() == ''

    def test_os_label_property(self, db, app):
        from app.models.server import Server
        with app.app_context():
            linux = Server(name='l', ip='1.1.1.1', os_type='linux', username='root')
            windows = Server(name='w', ip='2.2.2.2', os_type='windows', username='admin')
            macos = Server(name='m', ip='3.3.3.3', os_type='macos', username='admin')
            assert linux.os_label == 'Linux'
            assert windows.os_label == 'Windows'
            assert macos.os_label == 'macOS'
            assert '🐧' in linux.os_icon
            assert '🪟' in windows.os_icon
            assert '🍎' in macos.os_icon

    def test_to_dict(self, db, app):
        from app.models.server import Server
        from app import db as _db
        with app.app_context():
            s = Server(name='web01', ip='10.0.0.1', os_type='linux',
                       username='root', ssh_port=22, group='核心')
            _db.session.add(s)
            _db.session.commit()
            d = s.to_dict()
            assert d['name'] == 'web01'
            assert d['os_label'] == 'Linux'
            assert d['status'] == 'unknown'


class TestInspectionRecordModel:
    def test_disk_list_parsing(self, db, app):
        from app.models.inspection import InspectionRecord
        from app.models.server import Server
        from app import db as _db
        with app.app_context():
            s = Server(name='s', ip='3.3.3.3', os_type='linux', username='root')
            _db.session.add(s)
            _db.session.flush()
            disks = [{'mount': '/', 'usage_pct': 60}, {'mount': '/data', 'usage_pct': 85}]
            r = InspectionRecord(server_id=s.id, disk_info=json.dumps(disks), status='warning')
            _db.session.add(r)
            _db.session.commit()
            assert len(r.disk_list) == 2
            assert r.max_disk_usage == 85

    def test_max_disk_usage_empty(self, db, app):
        from app.models.inspection import InspectionRecord
        from app.models.server import Server
        from app import db as _db
        with app.app_context():
            s = Server(name='s2', ip='4.4.4.4', os_type='linux', username='root')
            _db.session.add(s)
            _db.session.flush()
            r = InspectionRecord(server_id=s.id, disk_info='[]', status='normal')
            _db.session.add(r)
            _db.session.commit()
            assert r.max_disk_usage == 0

    def test_invalid_json_graceful(self, db, app):
        from app.models.inspection import InspectionRecord
        from app.models.server import Server
        from app import db as _db
        with app.app_context():
            s = Server(name='s3', ip='5.5.5.5', os_type='linux', username='root')
            _db.session.add(s)
            _db.session.flush()
            r = InspectionRecord(server_id=s.id, disk_info='invalid json', status='unknown')
            _db.session.add(r)
            _db.session.commit()
            assert r.disk_list == []

    def test_status_labels(self, db, app):
        from app.models.inspection import InspectionRecord
        with app.app_context():
            for status, label, color in [
                ('normal', '正常', 'success'),
                ('warning', '警告', 'warning'),
                ('critical', '严重', 'danger'),
                ('offline', '离线', 'secondary'),
                ('unknown', '未知', 'secondary'),
            ]:
                r = InspectionRecord(status=status)
                assert r.status_label == label
                assert r.status_color == color


class TestAlertModel:
    def test_level_labels(self, db, app):
        from app.models.alert import Alert
        with app.app_context():
            warn = Alert(level='warning', server_id=1, message='test')
            crit = Alert(level='critical', server_id=1, message='test')
            assert warn.level_label == '警告'
            assert warn.level_color == 'warning'
            assert crit.level_label == '严重'
            assert crit.level_color == 'danger'

    def test_metric_labels(self, db, app):
        from app.models.alert import Alert
        with app.app_context():
            for metric, expected in [
                ('cpu', 'CPU使用率'), ('memory', '内存使用率'),
                ('disk', '磁盘使用率'), ('offline', '主机离线'), ('service', '服务异常'),
            ]:
                a = Alert(level='warning', server_id=1, metric=metric, message='x')
                assert a.metric_label == expected

    def test_alert_config_get(self, db, app):
        from app.models.alert import AlertConfig
        with app.app_context():
            cfg = AlertConfig.get()
            assert cfg is not None
            assert cfg.cpu_warning == 80.0
            assert cfg.cpu_critical == 95.0
