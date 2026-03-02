"""
测试：报告导出模块（HTML / Word / PDF）
"""
import pytest


class TestReportIndex:
    def test_report_index_page(self, admin_client):
        resp = admin_client.get('/reports/')
        assert resp.status_code == 200

    def test_report_unauthenticated(self, client):
        # 未登录访问需要登录后再跳转
        resp = client.get('/reports/', follow_redirects=True)
        assert resp.status_code == 200
        # 应该到达登录页（未登录）
        assert 'action="/auth/login"'.encode() in resp.data or b'login' in resp.data


class TestReportExport:
    def _add_server_with_inspection(self, app):
        """辅助：确保至少有一台服务器和巡检记录"""
        import json
        from app.models.server import Server
        from app.models.inspection import InspectionRecord
        from app import db
        with app.app_context():
            s = Server(name='report-srv', ip='10.3.3.3',
                       os_type='linux', username='root', enabled=True)
            db.session.add(s)
            db.session.flush()
            r = InspectionRecord(
                server_id=s.id, cpu_usage=30.0, mem_usage=50.0,
                disk_info=json.dumps([{'mount': '/', 'usage_pct': 40}]),
                status='normal',
            )
            db.session.add(r)
            db.session.commit()
            return r.id

    def test_export_html(self, admin_client, app, db):
        """HTML 报告导出：状态码 200，MIME 类型正确"""
        self._add_server_with_inspection(app)
        resp = admin_client.get('/reports/export/html')
        assert resp.status_code == 200
        assert 'text/html' in resp.content_type

    def test_export_word(self, admin_client, app, db):
        """Word 报告导出：状态码 200，MIME 类型正确"""
        self._add_server_with_inspection(app)
        resp = admin_client.get('/reports/export/word')
        assert resp.status_code == 200
        assert 'officedocument.wordprocessingml' in resp.content_type

    def test_export_pdf(self, admin_client, app, db):
        """PDF 报告导出：状态码 200，MIME 类型正确"""
        self._add_server_with_inspection(app)
        resp = admin_client.get('/reports/export/pdf')
        assert resp.status_code == 200
        assert 'application/pdf' in resp.content_type

    def test_export_html_empty_data(self, admin_client, db):
        """没有服务器数据时，HTML 报告仍然可以正常导出"""
        resp = admin_client.get('/reports/export/html')
        assert resp.status_code == 200

    def test_export_html_with_specific_record(self, admin_client, app, db):
        rid = self._add_server_with_inspection(app)
        resp = admin_client.get(f'/reports/export/html?record_id={rid}')
        assert resp.status_code == 200
        assert 'text/html' in resp.content_type

    def test_export_with_invalid_record(self, admin_client):
        resp = admin_client.get('/reports/export/html?record_id=99999', follow_redirects=True)
        assert resp.status_code == 200
        assert '巡检记录不存在'.encode() in resp.data
