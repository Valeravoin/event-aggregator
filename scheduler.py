# scheduler.py
from apscheduler.schedulers.background import BackgroundScheduler
from sync_runner import run_sync
import logging

logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler()

def sync_job():
    """Функция, которую будет запускать планировщик"""
    try:
        result = run_sync(source_name="real-api")
        logger.info(f"Фоновая синхронизация завершена. Результат: {result}")
    except Exception as e:
        logger.error(f"Ошибка в фоновой синхронизации: {e}", exc_info=True)

def start_scheduler():
    # minutes=1 — для теста запускаем каждую минуту. 
    # Когда убедишься, что всё работает, поменяй на hours=24 (раз в сутки)
    scheduler.add_job(
        sync_job,
        trigger='interval',
        hours=24,
        id='sync_job',
        replace_existing=True,
        max_instances=1     # Важно: только один запуск за раз
    )
    logger.info("Планировщик запущен: синхронизация будет выполняться каждые 24 часа")
    scheduler.start()

def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown()
        logger.info("Планировщик остановлен")
