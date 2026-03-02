"""
测试：认证模块（登录、登出、修改密码）
"""
import pytest


class TestLogin:
    def test_login_page_get(self, client):
        """GET /auth/login 应返回 200"""
        resp = client.get('/auth/login')
        assert resp.status_code == 200
        assert '登录'.encode() in resp.data

    def test_login_success(self, client):
        """正确账号密码登录后跳转 dashboard"""
        resp = client.post(
            '/auth/login',
            data={'username': 'admin', 'password': 'admin123'},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        # 登录成功后应进入 dashboard（不再有登录表单）
        assert 'action="/auth/login"'.encode() not in resp.data

    def test_login_wrong_password(self, client):
        """错误密码应返回错误提示"""
        resp = client.post(
            '/auth/login',
            data={'username': 'admin', 'password': 'wrongpwd'},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert '用户名或密码错误'.encode() in resp.data

    def test_login_nonexistent_user(self, client):
        """不存在的用户名应返回错误提示"""
        resp = client.post(
            '/auth/login',
            data={'username': 'nobody', 'password': 'anything'},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert '用户名或密码错误'.encode() in resp.data

    def test_protected_page_redirects_to_login(self, client):
        """未登录访问受保护页面应被重定向至登录页"""
        resp = client.get('/servers/', follow_redirects=False)
        assert resp.status_code in (301, 302)
        assert '/auth/login' in resp.headers['Location']


class TestLogout:
    def test_logout(self, admin_client):
        """登出后重定向到登录页"""
        resp = admin_client.get('/auth/logout', follow_redirects=True)
        assert resp.status_code == 200
        assert '已安全退出'.encode() in resp.data


class TestChangePassword:
    def test_change_password_page_get(self, admin_client):
        """GET /auth/change-password 应返回 200"""
        resp = admin_client.get('/auth/change-password')
        assert resp.status_code == 200

    def test_change_password_success(self, admin_client):
        """正确流程：旧密码正确、新密码一致 → 成功并登出"""
        resp = admin_client.post(
            '/auth/change-password',
            data={
                'old_password': 'admin123',
                'new_password': 'newpass456',
                'confirm_password': 'newpass456',
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert '密码修改成功'.encode() in resp.data

    def test_change_password_wrong_old(self, admin_client):
        """旧密码错误 → 失败"""
        resp = admin_client.post(
            '/auth/change-password',
            data={
                'old_password': 'wrongold',
                'new_password': 'newpass456',
                'confirm_password': 'newpass456',
            },
            follow_redirects=True,
        )
        assert '原密码错误'.encode() in resp.data

    def test_change_password_mismatch(self, admin_client):
        """两次密码不一致 → 失败"""
        resp = admin_client.post(
            '/auth/change-password',
            data={
                'old_password': 'admin123',
                'new_password': 'newpass456',
                'confirm_password': 'different',
            },
            follow_redirects=True,
        )
        assert '两次密码不一致'.encode() in resp.data

    def test_change_password_too_short(self, admin_client):
        """新密码少于 6 位 → 失败"""
        resp = admin_client.post(
            '/auth/change-password',
            data={
                'old_password': 'admin123',
                'new_password': '123',
                'confirm_password': '123',
            },
            follow_redirects=True,
        )
        assert '新密码至少6位'.encode() in resp.data
