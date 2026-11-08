import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from database import SessionLocal
from http_client import EventsApiClient
from sync_runner import run_sync

logger = logging.getLogger(__name__)


def create_scheduler(client: EventsApiClient | None):
    scheduler = AsyncIOScheduler()

    async def _run_sync_once() -> bool:
        if SessionLocal is None:
            logger.warning("DATABASE_URL не задан — плановая синхронизация пропущена")
            return False
        try:
            async with SessionLocal() as db:
                return await run_sync(db, client=client)
        except Exception:
            logger.exception("💥 Критическая ошибка во время синхронизации")
            return False

    async def sync_job():
        logger.info("⏰ Запуск запланированной синхронизации (по расписанию)...")
        success = await _run_sync_once()
        if success:
            logger.info("✅ Плановая синхронизация завершена успешно")
        else:
            logger.error("❌ Плановая синхронизация завершилась с ошибкой")

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
