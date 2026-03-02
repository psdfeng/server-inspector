"""
测试：服务器管理模块（列表、增删改、权限校验、Excel 导入）
"""
import json
import pytest


def _add_server(app, db_session, name='web01', ip='192.168.1.10'):
    """辅助：添加一台测试服务器并返回 id"""
    from app.models.server import Server
    from app import db as _db
    with app.app_context():
        s = Server(name=name, ip=ip, os_type='linux',
                   username='root', ssh_port=22, group='测试分组')
        _db.session.add(s)
        _db.session.commit()
        return s.id


class TestServerList:
    def test_server_list_page(self, admin_client):
        """服务器列表页应正常加载"""
        resp = admin_client.get('/servers/')
        assert resp.status_code == 200

    def test_server_list_unauthenticated(self, client):
        """未登录访问应重定向到登录页"""
        resp = client.get('/servers/', follow_redirects=True)
        assert b'login' in resp.data or 'action="/auth/login"'.encode() in resp.data

    def test_server_list_with_group_filter(self, admin_client, app, db):
        _add_server(app, db, name='srv1', ip='192.168.1.1')
        resp = admin_client.get('/servers/?group=测试分组')
        assert resp.status_code == 200

    def test_server_list_with_search(self, admin_client, app, db):
        _add_server(app, db, name='nginx-01', ip='10.0.0.1')
        resp = admin_client.get('/servers/?search=nginx')
        assert resp.status_code == 200
        assert b'nginx-01' in resp.data

    def test_server_list_with_macos_filter(self, admin_client, app, db):
        from app.models.server import Server
        from app import db as _db
        with app.app_context():
            _db.session.add(Server(name='mac-mini', ip='10.0.0.66', os_type='macos', username='ops'))
            _db.session.add(Server(name='linux-box', ip='10.0.0.67', os_type='linux', username='root'))
            _db.session.commit()
        resp = admin_client.get('/servers/?os_type=macos')
        assert resp.status_code == 200
        assert b'mac-mini' in resp.data
        assert b'linux-box' not in resp.data


class TestServerAdd:
    def test_add_server_get(self, admin_client):
        """GET 表单页应返回 200"""
        resp = admin_client.get('/servers/add')
        assert resp.status_code == 200

    def test_add_server_post_admin(self, admin_client, app, db):
        """管理员可以添加服务器"""
        resp = admin_client.post(
            '/servers/add',
            data={
                'name': 'db-server',
                'ip': '10.0.0.100',
                'os_type': 'linux',
                'ssh_port': '22',
                'username': 'root',
                'password': 'pass123',
                'group': '数据库',
                'description': '主数据库',
                'enabled': '1',
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert 'db-server'.encode() in resp.data

    def test_add_server_viewer_forbidden(self, viewer_client):
        """viewer 无权添加服务器"""
        resp = viewer_client.get('/servers/add', follow_redirects=False)
        assert resp.status_code in (301, 302)

    def test_add_server_post_admin_macos(self, admin_client, app, db):
        """管理员可以添加 macOS 服务器"""
        resp = admin_client.post(
            '/servers/add',
            data={
                'name': 'mac-build',
                'ip': '10.0.0.101',
                'os_type': 'macos',
                'ssh_port': '22',
                'username': 'builder',
                'password': 'pass123',
                'group': 'CI',
                'description': 'macOS 节点',
                'enabled': '1',
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert 'mac-build'.encode() in resp.data

    def test_add_server_post_admin_windows_default_admin_and_port(self, admin_client, app, db):
        """Windows 未填用户名和端口时，默认 Administrator + 5985"""
        from app.models.server import Server
        resp = admin_client.post(
            '/servers/add',
            data={
                'name': 'win-node',
                'ip': '10.0.0.102',
                'os_type': 'windows',
                'ssh_port': '',
                'username': '',
                'password': 'pass123',
                'group': 'Windows',
                'description': 'winrm',
                'enabled': '1',
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200
        with app.app_context():
            s = Server.query.filter_by(ip='10.0.0.102').first()
            assert s is not None
            assert s.username == 'Administrator'
            assert s.ssh_port == 5985

    def test_add_server_invalid_ip_rejected(self, admin_client):
        resp = admin_client.post(
            '/servers/add',
            data={
                'name': 'bad-ip',
                'ip': '300.1.1.1',
                'os_type': 'linux',
                'ssh_port': '22',
                'username': 'root',
                'password': 'pass123',
                'enabled': '1',
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert 'IP地址格式不正确'.encode() in resp.data

    def test_add_server_duplicate_ip_rejected(self, admin_client, app, db):
        _add_server(app, db, name='exist', ip='10.9.9.9')
        resp = admin_client.post(
            '/servers/add',
            data={
                'name': 'dup-ip',
                'ip': '10.9.9.9',
                'os_type': 'linux',
                'ssh_port': '22',
                'username': 'root',
                'password': 'pass123',
                'enabled': '1',
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert 'IP 已存在'.encode() in resp.data

    def test_add_windows_without_password_rejected(self, admin_client):
        resp = admin_client.post(
            '/servers/add',
            data={
                'name': 'win-no-pass',
                'ip': '10.0.0.210',
                'os_type': 'windows',
                'ssh_port': '5985',
                'username': 'Administrator',
                'password': '',
                'enabled': '1',
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert 'Windows 服务器请提供管理员账号密码'.encode() in resp.data


class TestServerEdit:
    def test_edit_server_admin(self, admin_client, app, db):
        """管理员可以编辑服务器"""
        sid = _add_server(app, db, name='old-name', ip='10.0.0.2')
        resp = admin_client.post(
            f'/servers/edit/{sid}',
            data={
                'name': 'new-name',
                'ip': '10.0.0.2',
                'os_type': 'linux',
                'ssh_port': '22',
                'username': 'root',
                'group': '测试',
                'enabled': '1',
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert 'new-name'.encode() in resp.data

    def test_edit_server_viewer_forbidden(self, viewer_client, app, db):
        """viewer 无权编辑服务器"""
        sid = _add_server(app, db, name='s', ip='10.0.0.3')
        resp = viewer_client.get(f'/servers/edit/{sid}', follow_redirects=False)
        assert resp.status_code in (301, 302)

    def test_edit_server_duplicate_ip_rejected(self, admin_client, app, db):
        sid1 = _add_server(app, db, name='s1', ip='10.0.0.31')
        sid2 = _add_server(app, db, name='s2', ip='10.0.0.32')
        resp = admin_client.post(
            f'/servers/edit/{sid2}',
            data={
                'name': 's2-new',
                'ip': '10.0.0.31',
                'os_type': 'linux',
                'ssh_port': '22',
                'username': 'root',
                'enabled': '1',
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert 'IP 已被其他服务器使用'.encode() in resp.data


class TestServerDelete:
    def test_delete_server_admin(self, admin_client, app, db):
        """管理员删除服务器返回 JSON success"""
        sid = _add_server(app, db, name='to-delete', ip='10.0.0.9')
        resp = admin_client.post(f'/servers/delete/{sid}')
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data['success'] is True

    def test_delete_server_viewer_forbidden(self, viewer_client, app, db):
        """viewer 删除服务器应返回权限不足"""
        sid = _add_server(app, db, name='protected', ip='10.0.0.8')
        resp = viewer_client.post(f'/servers/delete/{sid}')
        # 返回 JSON拒绝 or 重定向都总不应成功
        if resp.content_type and 'json' in resp.content_type:
            data = json.loads(resp.data)
            assert data['success'] is False
        else:
            # 重定向说明权限被拒到了
            assert resp.status_code in (301, 302, 200)

    def test_delete_nonexistent_server(self, admin_client):
        """删除不存在的服务器应返回 404"""
        resp = admin_client.post('/servers/delete/99999')
        assert resp.status_code == 404
