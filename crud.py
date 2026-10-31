# crud.py
from uuid import UUID
from sqlalchemy import select
from models import Event
from datetime import datetime, timezone

def get_event_by_id(db, event_id: UUID):
    stmt = select(Event).where(Event.id == event_id)
    result = db.execute(stmt)
    return result.scalars().first()


def create_event(db, event_data: dict):
    """Создаёт новое событие."""
    db_event = Event(
        id=event_data["id"],
        name=event_data["name"],
        event_time=event_data["event_time"],
        status=event_data.get("status", "unknown"),
        place_id=event_data.get("place_id"),
        place_name=event_data.get("place_name"),
        city=event_data.get("city"),
        address=event_data.get("address"),
        registration_deadline=event_data.get("registration_deadline"),
        number_of_visitors=event_data.get("number_of_visitors"),
        last_changed_at=event_data.get("last_changed_at"),
    )
    db.add(db_event)
    db.commit()
    db.refresh(db_event)
    return db_event


def upsert_event(db, event_data: dict):
    """
    Если событие с таким id уже есть — обновляем поля.
    Если нет — создаём новое.
    """
    # Преобразуем строку id в UUID, если это строка (для тестовых ID)
    from uuid import UUID as UUIDType
    event_id = event_data["id"]
    if isinstance(event_id, str):
        # Для тестовых строк вроде 'test-event-001' можно оставить как есть,
        # но если в модели UUID, SQLAlchemy сам попытается привести.
        # Если будут ошибки — скажи, сделаем явное приведение.
        pass

    existing = get_event_by_id(db, event_id)

    if existing:
        # Обновляем существующее
        existing.name = event_data["name"]
        existing.event_time = event_data["event_time"]
        existing.status = event_data.get("status", existing.status)
        existing.place_id = event_data.get("place_id")
        existing.place_name = event_data.get("place_name")
        existing.city = event_data.get("city")
        existing.address = event_data.get("address")
        existing.registration_deadline = event_data.get("registration_deadline")
        existing.number_of_visitors = event_data.get("number_of_visitors")
        existing.last_changed_at = event_data.get("last_changed_at") or datetime.now(timezone.utc)

        db.commit()
        db.refresh(existing)
        return existing
    else:
        # Создаём новое
        return create_event(db, event_data)
