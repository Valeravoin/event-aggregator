from exceptions import DomainError, EventNotFoundError, NoAvailableSeatsError, ProviderError
from models import EventStatus


class TicketRegistrationUseCase:
    def __init__(self, event_repo, ticket_repo, client):
        self.event_repo = event_repo
        self.ticket_repo = ticket_repo
        self.client = client

    async def do(self, first_name, last_name, email, event_id, seat):
        event = self.event_repo.get_by_id(event_id)
        if not event:
            raise EventNotFoundError()

        if event.status != EventStatus.PUBLISHED.value:
            raise DomainError(
                f"Registration unavailable: event status is {event.status}", status_code=400,
            )

        existing = self.ticket_repo.find_by_seat_and_event(event_id, seat)
        if existing:
            raise NoAvailableSeatsError("Seat is already taken")

        try:
            result, error = await self.client.register_ticket(
                event_id=event_id,
                seat=seat,
                email=email,
                first_name=first_name,
                last_name=last_name,
            )
        except Exception as e:
            raise ProviderError(f"Provider error: {e}")

        if error:
            raise ProviderError(str(error))

        ticket = self.ticket_repo.create(
            first_name=first_name,
            last_name=last_name,
            email=email,
            event_id=event_id,
            seat=seat,
            external_ticket_id=result.get("ticket_id"),
        )
        return {
            "ticket_id": str(ticket.ticket_id),
            "external_ticket_id": result.get("ticket_id"),
            "seat": seat,
            "status": "registered",
        }
