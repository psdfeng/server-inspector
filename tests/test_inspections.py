"""
测试：巡检记录模块（列表、详情、历史记录）
"""
import json
import pytest


def _make_server_with_inspection(app, status='normal'):
    """辅助：创建服务器及巡检记录"""
    from app.models.server import Server
    from app.models.inspection import InspectionRecord
    from app import db
    with app.app_context():
        s = Server(name='insp-srv', ip='10.2.2.2', os_type='linux', username='root')
        db.session.add(s)
        db.session.flush()
        r = InspectionRecord(
            server_id=s.id,
            cpu_usage=55.0,
            mem_usage=70.0,
            disk_info=json.dumps([{'mount': '/', 'usage_pct': 60}]),
            status=status,
            triggered_by='manual',
        )
        db.session.add(r)
        db.session.commit()
        return s.id, r.id


class TestInspectionList:
    def test_list_page(self, admin_client):
        resp = admin_client.get('/inspections/')
        assert resp.status_code == 200

    def test_list_filter_by_server(self, admin_client, app, db):
        sid, _ = _make_server_with_inspection(app)
        resp = admin_client.get(f'/inspections/?server_id={sid}')
        assert resp.status_code == 200

    def test_list_filter_by_status(self, admin_client, app, db):
        _make_server_with_inspection(app, status='warning')
        resp = admin_client.get('/inspections/?status=warning')
        assert resp.status_code == 200

    def test_list_unauthenticated(self, client):
        resp = client.get('/inspections/', follow_redirects=True)
        assert resp.status_code == 200
        assert b'login' in resp.data or 'action="/auth/login"'.encode() in resp.data


class TestInspectionDetail:
    def test_detail_page(self, admin_client, app, db):
        _, rid = _make_server_with_inspection(app)
        resp = admin_client.get(f'/inspections/detail/{rid}')
        assert resp.status_code == 200

    def test_detail_nonexistent(self, admin_client):
        resp = admin_client.get('/inspections/detail/99999')
        assert resp.status_code == 404


class TestInspectionHistory:
    def test_server_history_page(self, admin_client, app, db):
        sid, _ = _make_server_with_inspection(app)
        resp = admin_client.get(f'/inspections/server/{sid}')
        assert resp.status_code == 200

    def test_server_history_nonexistent(self, admin_client):
        resp = admin_client.get('/inspections/server/99999')
        assert resp.status_code == 404


class TestInspectionDelete:
    def test_delete_inspection_admin(self, admin_client, app, db):
        sid, rid = _make_server_with_inspection(app)
        resp = admin_client.post(f'/inspections/delete/{rid}')
        assert resp.status_code in (200, 302)

        from app.models.inspection import InspectionRecord
        with app.app_context():
            assert InspectionRecord.query.get(rid) is None

    def test_delete_inspection_viewer_forbidden(self, viewer_client, app, db):
        _, rid = _make_server_with_inspection(app)
        resp = viewer_client.post(
            f'/inspections/delete/{rid}',
            headers={'X-Requested-With': 'XMLHttpRequest'}
        )
        assert resp.status_code == 403

    def test_delete_inspection_also_delete_alerts(self, admin_client, app, db):
        from app.models.alert import Alert
        from app import db as _db
        sid, rid = _make_server_with_inspection(app)
        with app.app_context():
            a = Alert(server_id=sid, record_id=rid, level='warning', metric='cpu', message='x')
            _db.session.add(a)
            _db.session.commit()
            aid = a.id

        resp = admin_client.post(f'/inspections/delete/{rid}')
        assert resp.status_code in (200, 302)
        with app.app_context():
            assert Alert.query.get(aid) is None
