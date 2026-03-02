from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from app import db
from app.models.user import User

users_bp = Blueprint('users', __name__, url_prefix='/users')


def admin_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            flash('需要管理员权限', 'danger')
            return redirect(url_for('dashboard.index'))
        return f(*args, **kwargs)
    return decorated


@users_bp.route('/')
@login_required
@admin_required
def index():
    users = User.query.order_by(User.created_at).all()
    return render_template('users/index.html', users=users)


@users_bp.route('/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        display_name = request.form.get('display_name', '').strip()
        role = request.form.get('role', 'viewer')
        password = request.form.get('password', '')
        
        if not username or not password:
            flash('用户名和密码不能为空', 'danger')
            return render_template('users/form.html', user=None, action='add')
        
        if User.query.filter_by(username=username).first():
            flash('该用户名已存在', 'danger')
            return render_template('users/form.html', user=None, action='add')
        
        if len(password) < 6:
            flash('密码至少6位', 'danger')
            return render_template('users/form.html', user=None, action='add')
        
        user = User(username=username, display_name=display_name, role=role)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        flash(f'用户 {username} 创建成功', 'success')
        return redirect(url_for('users.index'))
    
    return render_template('users/form.html', user=None, action='add')


@users_bp.route('/edit/<int:user_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit(user_id):
    user = User.query.get_or_404(user_id)
    if request.method == 'POST':
        user.display_name = request.form.get('display_name', '').strip()
        user.role = request.form.get('role', 'viewer')
        user.is_active = bool(request.form.get('is_active'))
        password = request.form.get('password', '')
        if password:
            if len(password) < 6:
                flash('密码至少6位', 'danger')
                return render_template('users/form.html', user=user, action='edit')
            user.set_password(password)
        db.session.commit()
        flash(f'用户 {user.username} 更新成功', 'success')
        return redirect(url_for('users.index'))
    return render_template('users/form.html', user=user, action='edit')


@users_bp.route('/delete/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def delete(user_id):
    user = User.query.get_or_404(user_id)
    if user.username == 'admin':
        return jsonify({'success': False, 'message': '不能删除 admin 账户'})
    if user.id == current_user.id:
        return jsonify({'success': False, 'message': '不能删除当前登录账户'})
    db.session.delete(user)
    db.session.commit()
    return jsonify({'success': True})
