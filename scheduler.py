# scheduler.py
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy.orm import Session
from database import get_db
from sync_runner import run_sync

logger = logging.getLogger(__name__)

def create_scheduler():
    scheduler = BackgroundScheduler()

    def sync_job():
        """Задача для планировщика: всегда создаёт новую сессию"""
        logger.info("⏰ Запуск запланированной синхронизации (по расписанию)...")
        db: Session = next(get_db())
        try:
            success = run_sync(db, source_name="scheduled-source")
            if success:
                logger.info("✅ Запланированная синхронизация завершена успешно")
            else:
                logger.error("❌ Запланированная синхронизация завершилась с ошибкой")
        except Exception as e:
            logger.exception("💥 Критическая ошибка в планировщике: %s", e)
        finally:
            db.close()  # Обязательно закрываем!

    # 1. РУЧНОЙ ЗАПУСК ПРИ СТАРТЕ (чтобы не ждать 24 часа для теста)
    logger.info("🚀 Ручной запуск синхронизации при старте сервера...")
    initial_db: Session = next(get_db())
    try:
        run_sync(initial_db, source_name="scheduled-source")
        logger.info("✅ Ручная синхронизация при старте завершена.")
    except Exception as e:
        logger.exception("💥 Ошибка при ручной синхронизации: %s", e)
    finally:
        initial_db.close()

    # 2. ПЛАНИРОВЩИК: каждые 24 часа
    scheduler.add_job(
        sync_job,
        trigger='interval',
        hours=24,
        id='sync_job',
        replace_existing=True  # Защита от дублей при перезапуске
    )

    return scheduler
