# sync_crud.py
from sqlalchemy import select
from datetime import datetime, timezone
from database import SessionLocal
from models import SyncMetadata

def get_last_sync(db, source_name: str = "real-api"):
    """
    Возвращает время последней успешной синхронизации для указанного источника.
    Если записи нет — возвращает None.
    """
    stmt = select(SyncMetadata).where(SyncMetadata.source_name == source_name)
    result = db.execute(stmt)
    row = result.scalars().first()

    if row:
        return row.last_sync_time
    return None


def update_last_sync(
    db,
    new_time: datetime,
    source_name: str = "real-api",
    events_processed: int = 0,
    sync_status: str = "success",
):
    """
    Обновляет или создаёт запись о последней синхронизации для конкретного источника.
    Работает строго с полями, которые есть в текущей модели SyncMetadata.
    """
    # Ищем существующую запись по source_name
    stmt = select(SyncMetadata).where(SyncMetadata.source_name == source_name)
    result = db.execute(stmt)
    record = result.scalars().first()

    now_utc = datetime.now(timezone.utc)

    if record:
        # Обновляем существующую
        record.last_sync_time = new_time
        record.events_processed = events_processed
        record.sync_status = sync_status
        record.last_event_time = new_time
        record.last_changed_at = now_utc
    else:
        # Создаём новую
        new_record = SyncMetadata(
            source_name=source_name,
            last_sync_time=new_time,
            events_processed=events_processed,
            sync_status=sync_status,
            last_event_time=new_time,
            last_changed_at=now_utc,
        )
        db.add(new_record)

    db.commit()
    db.refresh(record or new_record)
    return (record or new_record).last_sync_time
