from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from app.models.user import User
from datetime import datetime

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        remember = bool(request.form.get('remember'))
        
        user = User.query.filter_by(username=username).first()
        if user and user.is_active and user.check_password(password):
            user.last_login = datetime.now()
            from app import db
            db.session.commit()
            login_user(user, remember=remember)
            next_page = request.args.get('next')
            return redirect(next_page or url_for('dashboard.index'))
        flash('用户名或密码错误', 'danger')
    
    return render_template('auth/login.html')


@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('已安全退出', 'info')
    return redirect(url_for('auth.login'))


@auth_bp.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    if request.method == 'POST':
        old = request.form.get('old_password', '')
        new = request.form.get('new_password', '')
        confirm = request.form.get('confirm_password', '')
        
        if not current_user.check_password(old):
            flash('原密码错误', 'danger')
        elif len(new) < 6:
            flash('新密码至少6位', 'danger')
        elif new != confirm:
            flash('两次密码不一致', 'danger')
        else:
            current_user.set_password(new)
            from app import db
            db.session.commit()
            flash('密码修改成功，请重新登录', 'success')
            return redirect(url_for('auth.logout'))
    
    return render_template('auth/change_password.html')
