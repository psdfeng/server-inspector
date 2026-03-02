from flask import Blueprint, render_template, redirect, url_for, flash, request, send_file, jsonify, current_app
from flask_login import login_required, current_user
from app import db
from app.models.server import Server
from app.models.inspection import InspectionRecord
from app.services.excel_import import generate_template, parse_excel
from app.utils.validators import is_valid_ip, is_valid_port
from io import BytesIO
import threading

servers_bp = Blueprint('servers', __name__, url_prefix='/servers')
ALLOWED_OS_TYPES = {'linux', 'windows', 'macos'}


def _default_port_for_os(os_type: str) -> int:
    return 5985 if os_type == 'windows' else 22


def _parse_connection_port(raw_port: str, os_type: str) -> int:
    if raw_port is None or str(raw_port).strip() == '':
        return _default_port_for_os(os_type)
    return int(raw_port)


def _validate_server_payload(name: str, ip: str, username: str, port: int, os_type: str, is_add: bool, password: str):
    if not name:
        return '服务器名称不能为空'
    if not ip:
        return 'IP地址不能为空'
    if not is_valid_ip(ip):
        return 'IP地址格式不正确'
    if not username:
        return '用户名不能为空'
    if not is_valid_port(port):
        return '连接端口必须在 1-65535 之间'
    if os_type == 'windows' and is_add and not password:
        return 'Windows 服务器请提供管理员账号密码（WinRM认证）'
    return ''


@servers_bp.route('/')
@login_required
def index():
    group = request.args.get('group', '')
    os_type = request.args.get('os_type', '')
    status = request.args.get('status', '')
    search = request.args.get('search', '')
    
    query = Server.query
    if group:
        query = query.filter_by(group=group)
    if os_type:
        query = query.filter_by(os_type=os_type)
    if search:
        query = query.filter(
            db.or_(Server.name.contains(search), Server.ip.contains(search))
        )
    
    servers = query.order_by(Server.group, Server.name).all()
    groups = db.session.query(Server.group).distinct().all()
    groups = [g[0] for g in groups if g[0]]
    
    # 过滤状态
    if status:
        servers = [s for s in servers if s.latest_inspection and s.latest_inspection.status == status]
    
    return render_template('servers/index.html', servers=servers, groups=groups,
                           current_group=group, current_os=os_type, current_status=status, search=search)


@servers_bp.route('/add', methods=['GET', 'POST'])
@login_required
def add():
    if not current_user.is_admin:
        flash('权限不足', 'danger')
        return redirect(url_for('servers.index'))
    
    if request.method == 'POST':
        os_type = request.form.get('os_type', 'linux').strip().lower()
        if os_type not in ALLOWED_OS_TYPES:
            flash('系统类型必须为 linux、windows 或 macos', 'danger')
            return render_template('servers/form.html', server=None, action='add')

        username = request.form.get('username', '').strip()
        if os_type == 'windows' and not username:
            username = 'Administrator'
        password = request.form.get('password', '')
        try:
            port = _parse_connection_port(request.form.get('ssh_port'), os_type)
        except Exception:
            flash('连接端口格式不正确', 'danger')
            return render_template('servers/form.html', server=None, action='add')
        err = _validate_server_payload(
            name=request.form.get('name', '').strip(),
            ip=request.form.get('ip', '').strip(),
            username=username,
            port=port,
            os_type=os_type,
            is_add=True,
            password=password,
        )
        if err:
            flash(err, 'danger')
            return render_template('servers/form.html', server=None, action='add')
        if Server.query.filter_by(ip=request.form.get('ip', '').strip()).first():
            flash('该 IP 已存在，请勿重复添加', 'danger')
            return render_template('servers/form.html', server=None, action='add')

        server = Server(
            name=request.form.get('name', '').strip(),
            ip=request.form.get('ip', '').strip(),
            os_type=os_type,
            ssh_port=port,
            username=username,
            group=request.form.get('group', '默认分组').strip() or '默认分组',
            description=request.form.get('description', '').strip(),
            enabled=bool(request.form.get('enabled')),
        )
        if password:
            server.set_password(password)
        db.session.add(server)
        db.session.commit()
        flash(f'服务器 {server.name} 添加成功', 'success')
        return redirect(url_for('servers.index'))
    
    return render_template('servers/form.html', server=None, action='add')


@servers_bp.route('/edit/<int:server_id>', methods=['GET', 'POST'])
@login_required
def edit(server_id):
    if not current_user.is_admin:
        flash('权限不足', 'danger')
        return redirect(url_for('servers.index'))
    
    server = Server.query.get_or_404(server_id)
    if request.method == 'POST':
        os_type = request.form.get('os_type', 'linux').strip().lower()
        if os_type not in ALLOWED_OS_TYPES:
            flash('系统类型必须为 linux、windows 或 macos', 'danger')
            return render_template('servers/form.html', server=server, action='edit')

        username = request.form.get('username', '').strip()
        if os_type == 'windows' and not username:
            username = 'Administrator'
        try:
            port = _parse_connection_port(request.form.get('ssh_port'), os_type)
        except Exception:
            flash('连接端口格式不正确', 'danger')
            return render_template('servers/form.html', server=server, action='edit')
        err = _validate_server_payload(
            name=request.form.get('name', '').strip(),
            ip=request.form.get('ip', '').strip(),
            username=username,
            port=port,
            os_type=os_type,
            is_add=False,
            password=request.form.get('password', ''),
        )
        if err:
            flash(err, 'danger')
            return render_template('servers/form.html', server=server, action='edit')
        duplicated = Server.query.filter(Server.ip == request.form.get('ip', '').strip(), Server.id != server.id).first()
        if duplicated:
            flash('该 IP 已被其他服务器使用', 'danger')
            return render_template('servers/form.html', server=server, action='edit')

        server.name = request.form.get('name', '').strip()
        server.ip = request.form.get('ip', '').strip()
        server.os_type = os_type
        server.ssh_port = port
        server.username = username
        server.group = request.form.get('group', '默认分组').strip() or '默认分组'
        server.description = request.form.get('description', '').strip()
        server.enabled = bool(request.form.get('enabled'))
        password = request.form.get('password', '')
        if password:
            server.set_password(password)
        db.session.commit()
        flash(f'服务器 {server.name} 更新成功', 'success')
        return redirect(url_for('servers.index'))
    
    return render_template('servers/form.html', server=server, action='edit')


@servers_bp.route('/delete/<int:server_id>', methods=['POST'])
@login_required
def delete(server_id):
    if not current_user.is_admin:
        return jsonify({'success': False, 'message': '权限不足'})
    server = Server.query.get_or_404(server_id)
    name = server.name
    db.session.delete(server)
    db.session.commit()
    flash(f'服务器 {name} 已删除', 'success')
    return jsonify({'success': True})


@servers_bp.route('/template')
@login_required
def download_template():
    """下载 Excel 导入模板"""
    data = generate_template()
    return send_file(
        BytesIO(data),
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name='服务器导入模板.xlsx'
    )


@servers_bp.route('/import', methods=['POST'])
@login_required
def import_excel():
    if not current_user.is_admin:
        flash('权限不足', 'danger')
        return redirect(url_for('servers.index'))
    
    file = request.files.get('file')
    if not file or not file.filename:
        flash('请选择文件', 'warning')
        return redirect(url_for('servers.index'))
    
    content = file.read()
    servers_data, errors = parse_excel(content)
    
    if errors:
        flash(f'文件解析错误: {"; ".join(errors[:5])}', 'danger')
        return redirect(url_for('servers.index'))
    
    added = 0
    skipped = 0
    for s in servers_data:
        existing = Server.query.filter_by(ip=s['ip']).first()
        if existing:
            skipped += 1
            continue
        server = Server(
            name=s['name'], ip=s['ip'], os_type=s['os_type'],
            ssh_port=s['ssh_port'], username=s['username'],
            group=s['group'], description=s['description'], enabled=True,
        )
        if s['password']:
            server.set_password(s['password'])
        db.session.add(server)
        added += 1
    
    db.session.commit()
    flash(f'导入完成：新增 {added} 台，跳过重复 {skipped} 台', 'success')
    return redirect(url_for('servers.index'))


@servers_bp.route('/inspect/<int:server_id>', methods=['POST'])
@login_required
def trigger_inspect(server_id):
    """手动触发单台服务器巡检"""
    server = Server.query.get_or_404(server_id)
    
    def do_inspect(app):
        with app.app_context():
            from app.services.inspector import run_inspection
            run_inspection(server_id, triggered_by='manual')
    
    app = current_app._get_current_object()
    t = threading.Thread(target=do_inspect, args=(app,))
    t.daemon = True
    t.start()
    
    flash(f'已触发对 {server.name} ({server.ip}) 的巡检，请稍后刷新查看结果', 'info')
    return redirect(url_for('servers.index'))


@servers_bp.route('/inspect-all', methods=['POST'])
@login_required
def trigger_inspect_all():
    """手动触发所有服务器巡检"""
    def do_inspect_all(app):
        with app.app_context():
            from app.services.inspector import run_all_inspections
            run_all_inspections(triggered_by='manual')
    
    app = current_app._get_current_object()
    t = threading.Thread(target=do_inspect_all, args=(app,))
    t.daemon = True
    t.start()
    
    flash('已触发全量服务器巡检，请稍后刷新查看结果', 'info')
    return redirect(url_for('servers.index'))
