import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from http_client import EventsApiClient
from repositories.event_repository import EventRepository
from repositories.sync_repository import SyncRepository
from settings import SYNC_SOURCE_NAME

logger = logging.getLogger(__name__)

FULL_SYNC_FROM = "2000-01-01T00:00:00+00:00"


def _parse_dt(value) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(value)
    except (ValueError, TypeError):
        logger.warning("⚠️ Не удалось разобрать дату: %r", value)
        return None


def _parse_uuid(value) -> UUID | None:
    if value is None:
        return None
    if isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except (ValueError, TypeError):
        logger.warning("⚠️ Не удалось разобрать UUID: %r", value)
        return None


def _get_changed_at(sync_record) -> str:
    """Дата для фильтра changed_at: инкремент от прошлого синка или полный обход."""
    last = sync_record.last_event_time
    if last:
        if last.tzinfo is None:
            last = last.replace(tzinfo=UTC)
        # Секунда перекрытия — чтобы не потерять события с тем же changed_at
        changed = last - timedelta(seconds=1)
        logger.info("🔁 Инкрементальный синк: забираю события с %s", changed.isoformat())
        return changed.isoformat()
    logger.info("🔁 Первый запуск — полный синк с 2000-01-01")
    return FULL_SYNC_FROM


def _build_fields(event_item: dict) -> dict:
    place = event_item.get("place") or {}
    return dict(
        name=event_item.get("name"),
        place_id=str(place.get("id")) if place.get("id") else None,
        place_name=place.get("name"),
        city=place.get("city"),
        address=place.get("address"),
        seats_pattern=place.get("seats_pattern"),
        event_time=_parse_dt(event_item.get("event_time")),
        registration_deadline=_parse_dt(event_item.get("registration_deadline")),
        status=event_item.get("status"),
        number_of_visitors=event_item.get("number_of_visitors", 0) or 0,
    )


async def run_sync(
    db: AsyncSession,
    client: EventsApiClient | None = None,
    source_name: str | None = None,
) -> bool:
    source = source_name or SYNC_SOURCE_NAME
    logger.info("🚀 Начало синхронизации для источника: %s", source)

    event_repo = EventRepository(db)
    sync_repo = SyncRepository(db)

    try:
        record = await sync_repo.get_or_create(source)
        acquired = await sync_repo.try_acquire(
            record, skip_locked=(db.bind.dialect.name == "postgresql")
        )
        if acquired is None:
            logger.warning("⚠️ Синхронизация для %s уже выполняется. Пропуск.", source)
            return False
        record = acquired

        # Единый клиент приложения; fallback — только если его не передали
        if client is None:
            client = EventsApiClient()

        # Инкрементальный синк: забираем только события, изменённые
        # после последнего успешного прогона. last_event_time обновляется
        # только после успешного commit — при падении ничего не теряем.
        events_data = await client.fetch_all_events(changed_at=_get_changed_at(record))
        if not isinstance(events_data, list):
            logger.error("❌ API вернул некорректный формат данных (не список).")
            events_data = []

        logger.info("📥 Получено событий от провайдера: %d", len(events_data))

        items: list[tuple[UUID, dict, datetime]] = []
        max_changed_at: datetime | None = None

        for event_item in events_data:
            event_id = _parse_uuid(event_item.get("id"))
            if not event_id:
                logger.warning("Пропущено событие без ID")
                continue

            item_changed_at = _parse_dt(event_item.get("changed_at"))
            if item_changed_at and (max_changed_at is None or item_changed_at > max_changed_at):
                max_changed_at = item_changed_at

            items.append(
                (event_id, _build_fields(event_item), item_changed_at or datetime.now(UTC))
            )

        created, updated = await event_repo.upsert_many(items)
        await sync_repo.mark_done(record, created, updated, max_changed_at)

        logger.info("✅ Синхронизация завершена. Новых: %d, Обновлено: %d", created, updated)
        return True

    except Exception:
        logger.exception("💥 Критическая ошибка при синхронизации")
        try:
            await sync_repo.mark_failed(record)
        except Exception:
            logger.exception("💥 Не удалось обновить статус синхронизации в БД")
        return False
