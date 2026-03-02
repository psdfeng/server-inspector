from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import logging

logger = logging.getLogger(__name__)
_scheduler = None


def init_scheduler(app):
    global _scheduler
    # 测试模式下跳过，防止后台线程干扰 pytest
    if app.config.get('TESTING'):
        logger.info("TESTING 模式，跳过定时任务启动")
        return
    if _scheduler and _scheduler.running:
        return

    _scheduler = BackgroundScheduler(timezone='Asia/Shanghai')

    hour = int(app.config.get('INSPECTION_HOUR', 2))
    minute = int(app.config.get('INSPECTION_MINUTE', 0))
    try:
        from app.models.system_setting import SystemSetting
        setting = SystemSetting.get()
        if setting:
            hour = int(setting.inspection_hour)
            minute = int(setting.inspection_minute)
    except Exception:
        # 配置表不存在或初始化过程中异常时，回退到应用配置
        pass

    _scheduler.add_job(
        func=_scheduled_inspection,
        trigger=CronTrigger(hour=hour, minute=minute),
        id='daily_inspection',
        name='每日自动巡检',
        replace_existing=True,
        args=[app],
    )
    _scheduler.start()
    logger.info(f"定时任务已启动，每日 {hour:02d}:{minute:02d} 执行自动巡检")


def _scheduled_inspection(app):
    with app.app_context():
        from app.services.inspector import run_all_inspections
        logger.info("开始执行定时自动巡检...")
        results = run_all_inspections(triggered_by='auto')
        logger.info(f"定时巡检完成，共巡检 {len(results)} 台服务器")


def get_scheduler():
    return _scheduler


def update_daily_schedule(app, hour: int, minute: int):
    """更新每日自动巡检任务时间并立即生效"""
    global _scheduler
    if app.config.get('TESTING'):
        return

    if _scheduler and _scheduler.running:
        _scheduler.reschedule_job('daily_inspection', trigger=CronTrigger(hour=hour, minute=minute))
        logger.info(f"定时任务已更新为每日 {hour:02d}:{minute:02d} 执行")
        return

    init_scheduler(app)


def get_next_run_time():
    if not _scheduler or not _scheduler.running:
        return None
    job = _scheduler.get_job('daily_inspection')
    return job.next_run_time if job else None
