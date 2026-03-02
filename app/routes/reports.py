from flask import Blueprint, render_template, request, send_file, flash, redirect, url_for, current_app
from flask_login import login_required
from app.models.server import Server
from app.models.inspection import InspectionRecord
from app import db
from sqlalchemy import func
from datetime import datetime
from io import BytesIO

reports_bp = Blueprint('reports', __name__, url_prefix='/reports')


def _get_report_data(record_id: int = 0):
    """获取最新巡检数据用于报告"""
    if record_id:
        record = InspectionRecord.query.get(record_id)
        if not record:
            return None
        s = record.server
        return [{
            'name': s.name, 'ip': s.ip, 'os_label': s.os_label, 'group': s.group,
            'status': record.status,
            'cpu_usage': round(record.cpu_usage, 1),
            'mem_usage': round(record.mem_usage, 1),
            'max_disk_usage': round(record.max_disk_usage, 1),
            'last_inspected': record.inspected_at.strftime('%Y-%m-%d %H:%M'),
        }]

    subq = db.session.query(
        InspectionRecord.server_id,
        func.max(InspectionRecord.inspected_at).label('max_at')
    ).group_by(InspectionRecord.server_id).subquery()

    latest_records = db.session.query(InspectionRecord).join(
        subq,
        db.and_(
            InspectionRecord.server_id == subq.c.server_id,
            InspectionRecord.inspected_at == subq.c.max_at,
        )
    ).all()

    record_map = {r.server_id: r for r in latest_records}
    servers = Server.query.filter_by(enabled=True).all()
    
    data = []
    for s in servers:
        r = record_map.get(s.id)
        data.append({
            'name': s.name, 'ip': s.ip, 'os_label': s.os_label, 'group': s.group,
            'status': r.status if r else 'unknown',
            'cpu_usage': round(r.cpu_usage, 1) if r else 'N/A',
            'mem_usage': round(r.mem_usage, 1) if r else 'N/A',
            'max_disk_usage': round(r.max_disk_usage, 1) if r else 'N/A',
            'last_inspected': r.inspected_at.strftime('%Y-%m-%d %H:%M') if r else '从未巡检',
        })
    return data


@reports_bp.route('/')
@login_required
def index():
    selected_record_id = request.args.get('record_id', 0, type=int)
    recent_records = db.session.query(InspectionRecord).join(Server).order_by(
        InspectionRecord.inspected_at.desc()
    ).limit(100).all()
    return render_template('reports/index.html', selected_record_id=selected_record_id, recent_records=recent_records)


@reports_bp.route('/export/html')
@login_required
def export_html():
    from app.services.report_gen import generate_html_report
    record_id = request.args.get('record_id', 0, type=int)
    data = _get_report_data(record_id)
    if data is None:
        flash('指定的巡检记录不存在，已切换为最新巡检数据导出', 'warning')
        return redirect(url_for('reports.index'))
    report_date = datetime.now().strftime('%Y-%m-%d')
    html = generate_html_report(data, report_date)
    buf = BytesIO(html.encode('utf-8'))
    suffix = f"_记录{record_id}" if record_id else ''
    return send_file(buf, mimetype='text/html; charset=utf-8',
                     as_attachment=True, download_name=f'巡检报告_{report_date}{suffix}.html')


@reports_bp.route('/export/word')
@login_required
def export_word():
    from app.services.report_gen import generate_word_report
    record_id = request.args.get('record_id', 0, type=int)
    data = _get_report_data(record_id)
    if data is None:
        flash('指定的巡检记录不存在，已切换为最新巡检数据导出', 'warning')
        return redirect(url_for('reports.index'))
    report_date = datetime.now().strftime('%Y-%m-%d')
    word_bytes = generate_word_report(data, report_date)
    suffix = f"_记录{record_id}" if record_id else ''
    return send_file(BytesIO(word_bytes),
                     mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                     as_attachment=True, download_name=f'巡检报告_{report_date}{suffix}.docx')


@reports_bp.route('/export/pdf')
@login_required
def export_pdf():
    from app.services.report_gen import generate_pdf_report
    record_id = request.args.get('record_id', 0, type=int)
    data = _get_report_data(record_id)
    if data is None:
        flash('指定的巡检记录不存在，已切换为最新巡检数据导出', 'warning')
        return redirect(url_for('reports.index'))
    report_date = datetime.now().strftime('%Y-%m-%d')
    fonts_dir = current_app.config['FONTS_FOLDER']
    pdf_bytes = generate_pdf_report(data, report_date, fonts_dir)
    suffix = f"_记录{record_id}" if record_id else ''
    return send_file(BytesIO(pdf_bytes), mimetype='application/pdf',
                     as_attachment=True, download_name=f'巡检报告_{report_date}{suffix}.pdf')
