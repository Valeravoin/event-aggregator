from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import Registration, TicketStatus


class RegistrationRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_ticket_id(self, ticket_id) -> Registration | None:
        stmt = select(Registration).where(Registration.ticket_id == ticket_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def create(
        self,
        event_id,
        email: str,
        first_name: str,
        last_name: str,
        seat: str,
        external_ticket_id: str | None = None,
        status: str = TicketStatus.ACTIVE.value,
    ) -> Registration:
        reg = Registration(
            ticket_id=uuid4(),
            event_id=event_id,
            email=email,
            first_name=first_name,
            last_name=last_name,
            seat=seat,
            external_ticket_id=external_ticket_id,
            status=status,
        )
        self.db.add(reg)
        await self.db.commit()
        await self.db.refresh(reg)
        return reg

    async def find_by_seat_and_event(self, event_id, seat: str) -> Registration | None:
        """Активная регистрация по паре (event_id, seat). Отменённые не мешают."""
        stmt = select(Registration).where(
            Registration.event_id == event_id,
            Registration.seat == seat,
            Registration.status == TicketStatus.ACTIVE.value,
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def update_status(self, registration: Registration, new_status: str):
        registration.status = new_status
        await self.db.commit()
        await self.db.refresh(registration)

    async def get_taken_seats(self, event_id: UUID) -> set[str]:
        """Места с активными регистрациями по событию."""
        stmt = select(Registration.seat).where(
            Registration.event_id == event_id,
            Registration.status == TicketStatus.ACTIVE.value,
            Registration.seat.isnot(None),
        )
        rows = (await self.db.execute(stmt)).all()
        return {row[0] for row in rows}
