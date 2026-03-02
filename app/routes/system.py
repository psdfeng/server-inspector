from flask import Blueprint, jsonify
from app.models.system_setting import SystemSetting
from app.models.server import Server
from app.models.alert import Alert

system_bp = Blueprint('system', __name__)


@system_bp.route('/healthz')
def healthz():
    setting = SystemSetting.get()
    return jsonify({
        'status': 'ok',
        'servers_enabled': Server.query.filter_by(enabled=True).count(),
        'alerts_unack': Alert.query.filter_by(acknowledged=False).count(),
        'schedule': {
            'hour': setting.inspection_hour if setting else None,
            'minute': setting.inspection_minute if setting else None,
        }
    })
