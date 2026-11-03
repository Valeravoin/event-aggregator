# scheduler.py
import asyncio
import logging

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy.orm import Session

from database import get_db
from sync_runner import run_sync

logger = logging.getLogger(__name__)


def _run_sync_once():
    """
    Вспомогательная функция: запускает асинхронный синк из синхронного контекста.
    run_sync теперь async, поэтому внутри синхронной джобы используем asyncio.run().
    """
    db: Session = next(get_db())
    try:
        success = asyncio.run(run_sync(db, source_name="scheduled-source"))
        if success:
            logger.info("✅ Синхронизация завершена успешно")
        else:
            logger.error("❌ Синхронизация завершилась с ошибкой (частично или полностью)")
        return success
    except Exception:
        logger.exception("💥 Критическая ошибка во время синхронизации")
        return False
    finally:
        db.close()


def create_scheduler():
    scheduler = BackgroundScheduler()

    def sync_job():
        """Задача планировщика: всегда создаёт новую сессию и изолированную транзакцию."""
        logger.info("⏰ Запуск запланированной синхронизации (по расписанию)...")
        _run_sync_once()

    # Ручной запуск при старте убран отсюда — стартовая синхронизация
    # выполняется в startup() в main.py. Здесь только расписание.

    # Планировщик: каждые 24 часа
    scheduler.add_job(
        sync_job,
        trigger="interval",
        hours=24,
        id="sync_job",
        replace_existing=True,  # Защита от дублей при перезапуске
        max_instances=1,        # Только один экземпляр задачи одновременно
    )

    logger.info("🕒 Планировщик настроен: интервал 24 часа, max_instances=1")
    return scheduler
