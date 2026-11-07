from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from models import Registration, TicketStatus


class RegistrationRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_ticket_id(self, ticket_id) -> Registration | None:
        stmt = select(Registration).where(Registration.ticket_id == ticket_id)
        result = self.db.execute(stmt)
        return result.scalar_one_or_none()

    def create(
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
        self.db.commit()
        self.db.refresh(reg)
        return reg

    def find_by_seat_and_event(self, event_id, seat: str) -> Registration | None:
        """
        Ищет регистрацию по паре (event_id, seat).
        Возвращает объект Registration или None, если такой пары нет.
        """
        stmt = select(Registration).where(
            Registration.event_id == event_id,
            Registration.seat == seat,
        )
        result = self.db.execute(stmt)
        return result.scalar_one_or_none()

    def update_status(self, registration: Registration, new_status: str):
        registration.status = new_status
        self.db.commit()
        self.db.refresh(registration)

    def get_taken_seats(self, event_id: UUID) -> set[str]:
        """Места с активными регистрациями по событию."""
        rows = (
            self.db.query(Registration.seat)
            .filter(
                Registration.event_id == event_id,
                Registration.status == TicketStatus.ACTIVE.value,
                Registration.seat.isnot(None),
            )
            .all()
        )
        return {row[0] for row in rows}
