from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from app import db
from app.models.inspection import InspectionRecord
from app.models.server import Server
from app.models.alert import Alert

inspections_bp = Blueprint('inspections', __name__, url_prefix='/inspections')


@inspections_bp.route('/')
@login_required
def index():
    page = request.args.get('page', 1, type=int)
    server_id = request.args.get('server_id', 0, type=int)
    status = request.args.get('status', '')
    
    query = db.session.query(InspectionRecord).join(Server)
    if server_id:
        query = query.filter(InspectionRecord.server_id == server_id)
    if status:
        query = query.filter(InspectionRecord.status == status)
    
    records = query.order_by(InspectionRecord.inspected_at.desc()).paginate(
        page=page, per_page=20, error_out=False
    )
    servers = Server.query.order_by(Server.name).all()
    return render_template('inspections/index.html', records=records,
                           servers=servers, current_server=server_id, current_status=status)


@inspections_bp.route('/detail/<int:record_id>')
@login_required
def detail(record_id):
    record = InspectionRecord.query.get_or_404(record_id)
    return render_template('inspections/detail.html', record=record, server=record.server)


@inspections_bp.route('/server/<int:server_id>')
@login_required
def server_history(server_id):
    server = Server.query.get_or_404(server_id)
    page = request.args.get('page', 1, type=int)
    records = InspectionRecord.query.filter_by(server_id=server_id).order_by(
        InspectionRecord.inspected_at.desc()
    ).paginate(page=page, per_page=20, error_out=False)
    return render_template('inspections/history.html', server=server, records=records)


@inspections_bp.route('/delete/<int:record_id>', methods=['POST'])
@login_required
def delete(record_id):
    if not current_user.is_admin:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'message': '权限不足'}), 403
        flash('权限不足', 'danger')
        return redirect(url_for('inspections.index'))

    record = InspectionRecord.query.get_or_404(record_id)
    # 告警表通过 record_id 关联，先删告警再删巡检记录
    Alert.query.filter_by(record_id=record.id).delete()
    db.session.delete(record)
    db.session.commit()

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'success': True})

    flash('巡检记录已删除', 'success')
    return redirect(url_for('inspections.index'))
