import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from database import SessionLocal
from sync_runner import run_sync

logger = logging.getLogger(__name__)


async def _run_sync_once() -> bool:
    if SessionLocal is None:
        logger.warning("DATABASE_URL не задан — плановая синхронизация пропущена")
        return False
    async with SessionLocal() as db:
        success = await run_sync(db, source_name="scheduled-source")
    if success:
        logger.info("✅ Синхронизация завершена успешно")
    else:
        logger.error("❌ Синхронизация завершилась с ошибкой (частично или полностью)")
    return success


def create_scheduler():
    scheduler = AsyncIOScheduler()

    async def sync_job():
        logger.info("⏰ Запуск запланированной синхронизации (по расписанию)...")
        try:
            await _run_sync_once()
        except Exception:
            logger.exception("💥 Критическая ошибка во время синхронизации")

    # Планировщик: каждые 24 часа
    scheduler.add_job(
        sync_job,
        trigger="interval",
        hours=24,
        id="sync_job",
        replace_existing=True,
        max_instances=1,
    )

    logger.info("🕒 Планировщик настроен: интервал 24 часа, max_instances=1")
    return scheduler
