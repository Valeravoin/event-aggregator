import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from http_client import EventsApiClient
from models import Event, SyncMetadata

logger = logging.getLogger(__name__)


def get_or_create_sync_record(db: Session, source_name: str) -> SyncMetadata:
    """Находит запись по source_name или создаёт новую."""
    stmt = select(SyncMetadata).where(SyncMetadata.source_name == source_name)
    result = db.execute(stmt)
    record = result.scalars().first()

    if not record:
        logger.info(f"🆕 Создаю запись синхронизации для источника: {source_name}")
        record = SyncMetadata(
            source_name=source_name,
            sync_status='idle',
            events_processed=0,
            last_event_time=None,
            last_sync_time=None
        )
        db.add(record)
        db.commit()
        db.refresh(record)

    return record


def run_sync(db: Session, source_name: str = "scheduled-source") -> bool:
    """
    Запускает синхронизацию с защитой от повторного запуска и обработкой ошибок API.
    Возвращает True при успешном завершении (даже если событий 0), False только при критических сбоях БД.
    """
    logger.info(f"🚀 Начало синхронизации для источника: {source_name}")

    try:
        # 1. Получаем или создаём запись о синхронизации
        sync_record = get_or_create_sync_record(db, source_name)

        # 2. Защита от повторного запуска
        if sync_record.sync_status == 'running':
            logger.warning(f"⚠️ Синхронизация для {source_name} уже выполняется! Пропуск.")
            return False

        # Помечаем как "в процессе"
        sync_record.sync_status = 'running'
        sync_record.last_sync_time = datetime.now(UTC)
        db.commit()

        # 3. Создаём клиент
        client = EventsApiClient()
        logger.debug("✅ HTTP клиент успешно инициализирован")

        # 4. Сразу запрашиваем полный список событий (без фильтра since)
        logger.info("🌐 Запрос полного списка событий у провайдера...")
        try:
            events_data = client.fetch_all_events()
            if not isinstance(events_data, list):
                logger.error("❌ API вернул некорректный формат данных (не список).")
                events_data = []
        except Exception:
            logger.exception("💥 Не удалось получить список событий. Продолжаем с пустым набором.")
            events_data = []  # Безопасное значение

        processed_count = 0
        updated_count = 0

        for event_item in events_data:
            event_id = event_item.get("id")
            if not event_id:
                logger.warning("Пропущено событие без ID")
                continue

            stmt = select(Event).where(Event.id == event_id)
            existing_event = db.execute(stmt).scalars().first()

            if existing_event:
                # Обновляем существующее событие
                existing_event.name = event_item.get("name")
                existing_event.place_name = event_item.get("place_name")
                existing_event.city = event_item.get("city")
                existing_event.address = event_item.get("address")
                existing_event.event_time = event_item.get("event_time")
                existing_event.registration_deadline = event_item.get("registration_deadline")
                existing_event.status = event_item.get("status")
                existing_event.number_of_visitors = event_item.get("number_of_visitors")
                existing_event.last_changed_at = datetime.now(UTC)
                updated_count += 1
            else:
                # Создаем новое событие
                new_event = Event(
                    id=event_item.get("id"),
                    name=event_item.get("name"),
                    place_id=event_item.get("place_id"),
                    place_name=event_item.get("place_name"),
                    city=event_item.get("city"),
                    address=event_item.get("address"),
                    event_time=event_item.get("event_time"),
                    registration_deadline=event_item.get("registration_deadline"),
                    status=event_item.get("status"),
                    number_of_visitors=event_item.get("number_of_visitors"),
                    last_changed_at=datetime.now(UTC)
                )
                db.add(new_event)
                processed_count += 1

        db.commit()

        # 5. Обновляем статистику в SyncMetadata
        latest_event_time = None
        if events_data:
            times = [e.get("event_time") for e in events_data if e.get("event_time")]
            if times:
                latest_event_time = max(times)

        sync_record.events_processed = processed_count + updated_count
        sync_record.last_sync_time = datetime.now(UTC)
        sync_record.last_event_time = latest_event_time
        sync_record.sync_status = 'idle'

        db.commit()

        logger.info(f"✅ Синхронизация завершена. Новые: {processed_count}, Обновлено: {updated_count}")
        return True

    except Exception:
        logger.exception("💥 Критическая ошибка при синхронизации (база данных или другое)")

        # Пытаемся сохранить статус ошибки в БД
        try:
            if 'sync_record' in locals() and sync_record is not None:
                sync_record.sync_status = 'failed'
                sync_record.last_sync_time = datetime.now(UTC)
                db.commit()
        except Exception:
            logger.exception("💥 Не удалось обновить статус синхронизации в БД")

        return False
