"""
测试：告警管理模块（列表、确认告警、告警配置）
"""
import json
import pytest


def _create_server_and_alert(app, level='warning', acknowledged=False):
    """辅助：创建服务器和告警记录，返回 (server_id, alert_id)"""
    from app.models.server import Server
    from app.models.alert import Alert
    from app import db
    with app.app_context():
        s = Server(name='alert-srv', ip='10.1.1.1', os_type='linux', username='root')
        db.session.add(s)
        db.session.flush()
        a = Alert(
            server_id=s.id,
            level=level,
            metric='cpu',
            message='CPU 使用率过高',
            value=90.0,
            threshold=80.0,
            acknowledged=acknowledged,
        )
        db.session.add(a)
        db.session.commit()
        return s.id, a.id


class TestAlertList:
    def test_alert_list_page(self, admin_client):
        resp = admin_client.get('/alerts/')
        assert resp.status_code == 200

    def test_alert_list_with_level_filter(self, admin_client, app, db):
        _create_server_and_alert(app, level='critical')
        resp = admin_client.get('/alerts/?level=critical')
        assert resp.status_code == 200

    def test_alert_list_unacked_filter(self, admin_client, app, db):
        _create_server_and_alert(app, acknowledged=False)
        resp = admin_client.get('/alerts/?ack=0')
        assert resp.status_code == 200

    def test_alert_list_acked_filter(self, admin_client, app, db):
        _create_server_and_alert(app, acknowledged=True)
        resp = admin_client.get('/alerts/?ack=1')
        assert resp.status_code == 200


class TestAlertAcknowledge:
    def test_acknowledge_single_alert(self, admin_client, app, db):
        _, alert_id = _create_server_and_alert(app)
        resp = admin_client.post(f'/alerts/acknowledge/{alert_id}')
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data['success'] is True

        # 验证数据库中已标记为 acknowledged
        from app.models.alert import Alert
        with app.app_context():
            a = Alert.query.get(alert_id)
            assert a.acknowledged is True
            assert a.ack_by == 'admin'

    def test_acknowledge_nonexistent_alert(self, admin_client):
        resp = admin_client.post('/alerts/acknowledge/99999')
        assert resp.status_code == 404

    def test_acknowledge_all(self, admin_client, app, db):
        _create_server_and_alert(app, acknowledged=False)
        _create_server_and_alert(app, acknowledged=False)
        resp = admin_client.post('/alerts/acknowledge-all', follow_redirects=True)
        assert resp.status_code == 200
        assert '所有告警已确认'.encode() in resp.data


class TestAlertConfig:
    def test_alert_config_page_admin(self, admin_client):
        resp = admin_client.get('/alerts/config')
        assert resp.status_code == 200

    def test_alert_config_page_viewer_forbidden(self, viewer_client):
        resp = viewer_client.get('/alerts/config', follow_redirects=False)
        assert resp.status_code in (301, 302)

    def test_update_alert_config(self, admin_client, app, db):
        resp = admin_client.post(
            '/alerts/config',
            data={
                'cpu_warning': '75',
                'cpu_critical': '90',
                'mem_warning': '80',
                'mem_critical': '95',
                'disk_warning': '70',
                'disk_critical': '90',
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert '告警配置已保存'.encode() in resp.data

        # 验证值已更新
        from app.models.alert import AlertConfig
        with app.app_context():
            cfg = AlertConfig.get()
            assert cfg.cpu_warning == 75.0
            assert cfg.disk_warning == 70.0

    def test_update_daily_inspection_schedule(self, admin_client, app, db):
        resp = admin_client.post(
            '/alerts/config',
            data={
                'cpu_warning': '80',
                'cpu_critical': '95',
                'mem_warning': '85',
                'mem_critical': '95',
                'disk_warning': '80',
                'disk_critical': '95',
                'inspection_hour': '3',
                'inspection_minute': '30',
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200
        from app.models.system_setting import SystemSetting
        with app.app_context():
            setting = SystemSetting.get()
            assert setting.inspection_hour == 3
            assert setting.inspection_minute == 30
