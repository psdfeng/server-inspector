"""
测试：用户管理模块（列表、增删改、权限校验）
"""
import json
import pytest


class TestUserList:
    def test_admin_can_view_users(self, admin_client):
        resp = admin_client.get('/users/')
        assert resp.status_code == 200
        assert 'admin'.encode() in resp.data

    def test_viewer_cannot_view_users(self, viewer_client):
        """viewer 访问用户管理页面应被重定向"""
        resp = viewer_client.get('/users/', follow_redirects=False)
        assert resp.status_code in (301, 302)


class TestUserAdd:
    def test_admin_add_user_page(self, admin_client):
        resp = admin_client.get('/users/add')
        assert resp.status_code == 200

    def test_admin_add_user_success(self, admin_client):
        resp = admin_client.post(
            '/users/add',
            data={
                'username': 'newuser',
                'display_name': '新用户',
                'role': 'viewer',
                'password': 'pass123',
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert 'newuser'.encode() in resp.data

    def test_add_duplicate_username(self, admin_client):
        """重复用户名应提示错误"""
        admin_client.post('/users/add', data={
            'username': 'dup', 'display_name': '', 'role': 'viewer', 'password': 'pass123'
        })
        resp = admin_client.post(
            '/users/add',
            data={'username': 'dup', 'display_name': '', 'role': 'viewer', 'password': 'pass123'},
            follow_redirects=True,
        )
        assert '该用户名已存在'.encode() in resp.data

    def test_add_user_short_password(self, admin_client):
        """密码少于 6 位应提示错误"""
        resp = admin_client.post(
            '/users/add',
            data={'username': 'shortpwd', 'display_name': '', 'role': 'viewer', 'password': 'abc'},
            follow_redirects=True,
        )
        assert '密码至少6位'.encode() in resp.data

    def test_add_user_empty_username(self, admin_client):
        """用户名为空应提示错误"""
        resp = admin_client.post(
            '/users/add',
            data={'username': '', 'display_name': '', 'role': 'viewer', 'password': 'pass123'},
            follow_redirects=True,
        )
        assert '用户名和密码不能为空'.encode() in resp.data

    def test_viewer_cannot_add_user(self, viewer_client):
        resp = viewer_client.get('/users/add', follow_redirects=False)
        assert resp.status_code in (301, 302)


class TestUserEdit:
    def _create_user(self, admin_client, app):
        from app.models.user import User
        from app import db
        with app.app_context():
            u = User(username='editme', role='viewer', display_name='Edit Me')
            u.set_password('pass123')
            db.session.add(u)
            db.session.commit()
            return u.id

    def test_admin_edit_user(self, admin_client, app, db):
        uid = self._create_user(admin_client, app)
        resp = admin_client.post(
            f'/users/edit/{uid}',
            data={
                'display_name': 'Edited Name',
                'role': 'admin',
                'is_active': '1',
                'password': '',
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert 'editme'.encode() in resp.data


class TestUserDelete:
    def _create_user(self, app):
        from app.models.user import User
        from app import db
        with app.app_context():
            u = User(username='deleteme', role='viewer', display_name='Del')
            u.set_password('pass123')
            db.session.add(u)
            db.session.commit()
            return u.id

    def test_delete_user_success(self, admin_client, app, db):
        uid = self._create_user(app)
        resp = admin_client.post(f'/users/delete/{uid}')
        data = json.loads(resp.data)
        assert data['success'] is True

    def test_cannot_delete_admin(self, admin_client, app, db):
        from app.models.user import User
        # 在 app 上下文内获取 admin 的 ID
        admin_id = User.query.filter_by(username='admin').first().id
        resp = admin_client.post(f'/users/delete/{admin_id}')
        data = json.loads(resp.data)
        assert data['success'] is False
        assert 'admin' in data['message']
