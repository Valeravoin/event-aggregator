from http_client import EventsApiClient
from repositories.event_repository import EventRepository
from repositories.registration_repository import RegistrationRepository


class TicketCancellationUseCase:
    def __init__(
        self,
        event_repo: EventRepository,
        ticket_repo: RegistrationRepository,
        client: EventsApiClient,
    ):
        self.event_repo = event_repo
        self.ticket_repo = ticket_repo
        self.client = client

    async def do(self, ticket_id: str) -> dict:
        reg = self.ticket_repo.get_by_ticket_id(ticket_id)
        if not reg:
            raise ValueError("Билет не найден")
        if reg.status == "cancelled":
            return {"success": True, "message": "Билет уже отменён", "ticket_id": ticket_id}

        event = self.event_repo.get_by_id(str(reg.event_id))
        if not event:
            raise RuntimeError("Внутренняя несогласованность: событие не найдено для билета")

        _, error = await self.client.unregister_ticket(
            event_id=str(event.id), ticket_id=ticket_id
        )
        if error:
            raise RuntimeError(f"502:{error}")

        self.ticket_repo.update_status(reg, "cancelled")
        return {
            "success": True,
            "ticket_id": ticket_id,
            "message": "Отмена успешна",
        }
