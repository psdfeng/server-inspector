from flask import Blueprint, render_template
from flask_login import login_required
from app.models.server import Server
from app.models.inspection import InspectionRecord
from app.models.alert import Alert
from datetime import datetime, timedelta
from app import db
from sqlalchemy import func

dashboard_bp = Blueprint('dashboard', __name__)


@dashboard_bp.route('/')
@login_required
def index():
    # 服务器统计
    total_servers = Server.query.filter_by(enabled=True).count()
    
    # 最近一次巡检的各状态统计
    # 获取每台服务器最新巡检记录
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
    
    status_counts = {'normal': 0, 'warning': 0, 'critical': 0, 'offline': 0, 'unknown': 0}
    for r in latest_records:
        status_counts[r.status] = status_counts.get(r.status, 0) + 1
    never_inspected = total_servers - len(latest_records)
    status_counts['unknown'] += never_inspected
    
    # 未确认告警
    unack_alerts = Alert.query.filter_by(acknowledged=False).order_by(Alert.created_at.desc()).limit(3).all()
    unack_critical = Alert.query.filter_by(acknowledged=False, level='critical').count()
    unack_warning = Alert.query.filter_by(acknowledged=False, level='warning').count()
    
    # 近7日巡检趋势（按天统计各状态数量）
    seven_days_ago = datetime.now() - timedelta(days=7)
    trend_data = _get_trend_data(seven_days_ago)
    
    # 最近巡检记录
    recent_records = db.session.query(InspectionRecord).join(Server).order_by(
        InspectionRecord.inspected_at.desc()
    ).limit(3).all()
    
    return render_template('dashboard/index.html',
        total_servers=total_servers,
        status_counts=status_counts,
        unack_alerts=unack_alerts,
        unack_critical=unack_critical,
        unack_warning=unack_warning,
        trend_data=trend_data,
        recent_records=recent_records,
    )


def _get_trend_data(since):
    import json
    records = db.session.query(
        func.date(InspectionRecord.inspected_at).label('date'),
        InspectionRecord.status,
        func.count(InspectionRecord.id).label('count')
    ).filter(InspectionRecord.inspected_at >= since).group_by(
        func.date(InspectionRecord.inspected_at), InspectionRecord.status
    ).all()
    
    days = {}
    for r in records:
        d = str(r.date)
        if d not in days:
            days[d] = {'normal': 0, 'warning': 0, 'critical': 0, 'offline': 0}
        days[d][r.status] = r.count
    
    sorted_days = sorted(days.items())
    return {
        'labels': json.dumps([d for d, _ in sorted_days]),
        'normal': json.dumps([v.get('normal', 0) for _, v in sorted_days]),
        'warning': json.dumps([v.get('warning', 0) for _, v in sorted_days]),
        'critical': json.dumps([v.get('critical', 0) for _, v in sorted_days]),
        'offline': json.dumps([v.get('offline', 0) for _, v in sorted_days]),
    }
