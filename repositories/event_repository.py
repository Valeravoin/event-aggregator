# repositories/event_repository.py
from datetime import UTC, datetime

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from models import Event, EventStatus


class EventRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_by_id(self, event_id: str) -> Event | None:
        stmt = select(Event).where(Event.id == event_id)
        result = self.session.execute(stmt)
        return result.scalars().first()

    def list_events(self, page: int, page_size: int, date_from_str: str | None) -> tuple[list[Event], int]:
        page = max(page, 1)
        if page_size < 1 or page_size > 100:
            page_size = 20

        offset = (page - 1) * page_size

        dt = None
        if date_from_str:
            try:
                dt = datetime.strptime(date_from_str, "%Y-%m-%d").replace(tzinfo=UTC)
            except ValueError:
                raise ValueError("Неверный формат date_from. Используйте YYYY-MM-DD")

        # Сначала считаем общее количество
        count_stmt = select(func.count()).select_from(Event)
        if dt:
            count_stmt = count_stmt.where(Event.event_time >= dt)
        total = self.session.execute(count_stmt).scalar() or 0


        status_priority = case(
            (Event.status == EventStatus.PUBLISHED.value, 0),
            (Event.status == EventStatus.REGISTRATION_CLOSED.value, 1),
            else_=2,
        )

        stmt = select(Event).order_by(
            status_priority,
            Event.event_time.asc().nulls_last(),
        )
        if dt:
            stmt = stmt.where(Event.event_time >= dt)
        stmt = stmt.limit(page_size).offset(offset)
        results = self.session.execute(stmt).scalars().all()

        return results, total

    def count_all(self) -> int:
        stmt = select(func.count()).select_from(Event)
        return self.session.execute(stmt).scalar() or 0

    def get_events_page(self, offset: int, limit: int) -> list[Event]:
        """Возвращает страницу событий: published первыми, затем по времени."""
        status_priority = case(
            (Event.status == EventStatus.PUBLISHED.value, 0),
            (Event.status == EventStatus.REGISTRATION_CLOSED.value, 1),
            else_=2,
        )

        stmt = (
            select(Event)
            .order_by(
                status_priority,
                Event.event_time.asc().nulls_last(),
            )
            .offset(offset)
            .limit(limit)
        )
        result = self.session.execute(stmt)
        return list(result.scalars().all())

    def count_events(self) -> int:
        """Общее количество событий в базе."""
        stmt = select(func.count(Event.id))
        return self.session.execute(stmt).scalar() or 0
