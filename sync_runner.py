import logging
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from http_client import EventsApiClient
from models import Event, SyncMetadata

logger = logging.getLogger(__name__)


def _parse_dt(value) -> datetime | None:
    """ISO 8601 строку -> datetime (провайдер отдаёт даты строками с таймзоной)."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(value)
    except (ValueError, TypeError):
        logger.warning(f"⚠️ Не удалось разобрать дату: {value!r}")
        return None


def _parse_uuid(value) -> UUID | None:
    if value is None:
        return None
    if isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except (ValueError, TypeError):
        logger.warning(f"⚠️ Не удалось разобрать UUID: {value!r}")
        return None


def get_or_create_sync_record(db: Session, source_name: str) -> SyncMetadata:
    """Находит запись по source_name или создаёт новую."""
    stmt = select(SyncMetadata).where(SyncMetadata.source_name == source_name)
    record = db.execute(stmt).scalars().first()

    if not record:
        logger.info(f"🆕 Создаю запись синхронизации для источника: {source_name}")
        record = SyncMetadata(
            source_name=source_name,
            sync_status="idle",
            events_processed=0,
            last_event_time=None,
            last_sync_time=None,
        )
        db.add(record)
        db.commit()
        db.refresh(record)

    return record


async def run_sync(db: Session, source_name: str = "scheduled-source") -> bool:
    """
    Запускает синхронизацию. Теперь ASYNC — клиент асинхронный, вызов требует await.
    Инкрементальная логика: если у источника уже сохранён changed_at, запрашиваем
    только изменения; первый запуск — changed_at=2000-01-01 (все события).
    """
    logger.info(f"🚀 Начало синхронизации для источника: {source_name}")

    try:
        # 1. Запись о синхронизации + защита от повторного запуска
        sync_record = get_or_create_sync_record(db, source_name)

        if sync_record.sync_status == "running":
            logger.warning(f"⚠️ Синхронизация для {source_name} уже выполняется! Пропуск.")
            return False

        sync_record.sync_status = "running"
        sync_record.last_sync_time = datetime.now(UTC)
        db.commit()

        # 2. Клиент
        client = EventsApiClient()

        # 3. С какой даты синхронизируемся
        changed_at = "2000-01-01"
        if sync_record.last_event_time:
            changed_at = sync_record.last_event_time.strftime("%Y-%m-%d")
            logger.info(f"🔄 Инкрементальный синк с {changed_at}")
        else:
            logger.info("🔄 Первый запуск: запрашиваем все события")

        # 4. fetch_all_events — ASYNC, обязателен await!
        # При ошибке провайдера считаем синк проваленным (не глотаем!)
        events_data = await client.fetch_all_events(changed_at=changed_at)
        if not isinstance(events_data, list):
            logger.error("❌ API вернул некорректный формат данных (не список).")
            events_data = []

        processed_count = 0
        updated_count = 0
        max_changed_at: datetime | None = None

        for event_item in events_data:
            event_id = _parse_uuid(event_item.get("id"))
            if not event_id:
                logger.warning("Пропущено событие без ID")
                continue

            # place — вложенный объект провайдера
            place = event_item.get("place") or {}

            item_changed_at = _parse_dt(event_item.get("changed_at"))
            if item_changed_at and (max_changed_at is None or item_changed_at > max_changed_at):
                max_changed_at = item_changed_at

            stmt = select(Event).where(Event.id == event_id)
            existing_event = db.execute(stmt).scalars().first()

            fields = dict(
                name=event_item.get("name"),
                place_id=_parse_uuid(place.get("id")) or event_id,
                place_name=place.get("name"),
                city=place.get("city"),
                address=place.get("address"),
                seats_pattern=place.get("seats_pattern"),  # реальный паттерн, без хардкода
                event_time=_parse_dt(event_item.get("event_time")),
                registration_deadline=_parse_dt(event_item.get("registration_deadline")),
                status=event_item.get("status"),
                number_of_visitors=event_item.get("number_of_visitors", 0),
            )

            if existing_event:
                for key, value in fields.items():
                    setattr(existing_event, key, value)
                existing_event.last_changed_at = item_changed_at or datetime.now(UTC)
                updated_count += 1
            else:
                db.add(Event(id=event_id, last_changed_at=item_changed_at or datetime.now(UTC), **fields))
                processed_count += 1

        db.commit()

        # 5. Обновляем метаданные синка.
        # last_event_time храним как максимальный changed_at провайдера —
        # он используется для следующего инкрементального запроса.
        sync_record.events_processed = (sync_record.events_processed or 0) + processed_count + updated_count
        sync_record.last_sync_time = datetime.now(UTC)
        if max_changed_at:
            sync_record.last_event_time = max_changed_at
        sync_record.sync_status = "idle"
        db.commit()

        logger.info(
            f"✅ Синхронизация завершена. Новых: {processed_count}, Обновлено: {updated_count}"
        )
        return True

    except Exception:
        logger.exception("💥 Критическая ошибка при синхронизации")

        try:
            if "sync_record" in locals() and sync_record is not None:
                sync_record.sync_status = "failed"
                sync_record.last_sync_time = datetime.now(UTC)
                db.commit()
        except Exception:
            logger.exception("💥 Не удалось обновить статус синхронизации в БД")

        return False
