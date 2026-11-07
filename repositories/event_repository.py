from datetime import UTC, date, datetime

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models import Event, EventStatus


class EventRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, event_id) -> Event | None:
        stmt = select(Event).where(Event.id == event_id)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def list_events(
        self, page: int, page_size: int, date_from: date | None = None
    ) -> tuple[list[Event], int]:
        page = max(page, 1)
        page_size = min(max(page_size, 1), 100)
        offset = (page - 1) * page_size

        count_stmt = select(func.count()).select_from(Event)
        if date_from:
            count_stmt = count_stmt.where(
                Event.event_time
                >= datetime(date_from.year, date_from.month, date_from.day, tzinfo=UTC)
            )
        total = (await self.session.execute(count_stmt)).scalar() or 0

        status_priority = case(
            (Event.status == EventStatus.PUBLISHED.value, 0),
            (Event.status == EventStatus.REGISTRATION_CLOSED.value, 1),
            else_=2,
        )

        stmt = select(Event).order_by(
            status_priority,
            Event.event_time.asc().nulls_last(),
        )
        if date_from:
            stmt = stmt.where(
                Event.event_time
                >= datetime(date_from.year, date_from.month, date_from.day, tzinfo=UTC)
            )
        stmt = stmt.limit(page_size).offset(offset)
        results = (await self.session.execute(stmt)).scalars().all()

        return list(results), total
