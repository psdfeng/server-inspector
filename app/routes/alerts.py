from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, current_app
from flask_login import login_required, current_user
from app import db
from app.models.alert import Alert, AlertConfig
from app.models.system_setting import SystemSetting
from app.services.scheduler import update_daily_schedule, get_next_run_time
from datetime import datetime

alerts_bp = Blueprint('alerts', __name__, url_prefix='/alerts')


@alerts_bp.route('/')
@login_required
def index():
    level = request.args.get('level', '')
    ack = request.args.get('ack', '')
    page = request.args.get('page', 1, type=int)
    
    query = Alert.query
    if level:
        query = query.filter_by(level=level)
    if ack == '0':
        query = query.filter_by(acknowledged=False)
    elif ack == '1':
        query = query.filter_by(acknowledged=True)
    
    alerts = query.order_by(Alert.created_at.desc()).paginate(page=page, per_page=30, error_out=False)
    unack_count = Alert.query.filter_by(acknowledged=False).count()
    return render_template('alerts/index.html', alerts=alerts, unack_count=unack_count,
                           current_level=level, current_ack=ack)


@alerts_bp.route('/acknowledge/<int:alert_id>', methods=['POST'])
@login_required
def acknowledge(alert_id):
    alert = Alert.query.get_or_404(alert_id)
    alert.acknowledged = True
    alert.ack_by = current_user.username
    alert.ack_at = datetime.now()
    db.session.commit()
    return jsonify({'success': True})


@alerts_bp.route('/acknowledge-all', methods=['POST'])
@login_required
def acknowledge_all():
    Alert.query.filter_by(acknowledged=False).update({
        'acknowledged': True,
        'ack_by': current_user.username,
        'ack_at': datetime.now()
    })
    db.session.commit()
    flash('所有告警已确认', 'success')
    return redirect(url_for('alerts.index'))


@alerts_bp.route('/config', methods=['GET', 'POST'])
@login_required
def config():
    if not current_user.is_admin:
        flash('权限不足', 'danger')
        return redirect(url_for('alerts.index'))
    
    cfg = AlertConfig.get()
    schedule = SystemSetting.get()
    if request.method == 'POST':
        cfg.cpu_warning = float(request.form.get('cpu_warning', 80))
        cfg.cpu_critical = float(request.form.get('cpu_critical', 95))
        cfg.mem_warning = float(request.form.get('mem_warning', 85))
        cfg.mem_critical = float(request.form.get('mem_critical', 95))
        cfg.disk_warning = float(request.form.get('disk_warning', 80))
        cfg.disk_critical = float(request.form.get('disk_critical', 95))

        hour = int(request.form.get('inspection_hour', schedule.inspection_hour if schedule else 2))
        minute = int(request.form.get('inspection_minute', schedule.inspection_minute if schedule else 0))
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            flash('自动巡检时间不合法，请输入 00:00 - 23:59', 'danger')
            next_run = get_next_run_time()
            return render_template('alerts/config.html', config=cfg, schedule=schedule, next_run=next_run)

        if not schedule:
            schedule = SystemSetting()
            db.session.add(schedule)
        schedule.inspection_hour = hour
        schedule.inspection_minute = minute
        db.session.commit()
        update_daily_schedule(current_app._get_current_object(), hour, minute)
        flash('告警配置已保存', 'success')
        return redirect(url_for('alerts.config'))
    
    next_run = get_next_run_time()
    return render_template('alerts/config.html', config=cfg, schedule=schedule, next_run=next_run)
