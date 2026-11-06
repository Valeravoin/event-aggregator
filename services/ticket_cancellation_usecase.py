import logging

from exceptions import DomainError, ProviderError, TicketNotFoundError
from http_client import EventsApiClient
from models import TicketStatus
from repositories.event_repository import EventRepository
from repositories.registration_repository import RegistrationRepository

logger = logging.getLogger(__name__)


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
            # Несуществующий билет — это 404 Not Found, а не 400
            raise TicketNotFoundError()

        if reg.status == TicketStatus.CANCELLED.value:
            return {"success": True, "message": "Билет уже отменён", "ticket_id": ticket_id}

        event = self.event_repo.get_by_id(str(reg.event_id))
        if not event:
            # Это баг в данных, а не ошибка клиента — 500 с честным логом
            logger.exception("Внутренняя несогласованность: событие %s не найдено для билета %s", reg.event_id, ticket_id)
            raise DomainError("Внутренняя ошибка", status_code=500)

        # Провайдер знает только свой ID билета — внешний, полученный при регистрации
        provider_ticket_id = reg.external_ticket_id or ticket_id
        _, error = await self.client.unregister_ticket(
            event_id=str(event.id), ticket_id=provider_ticket_id
        )
        if error:
            logger.error("💥 Провайдер ответил ошибкой на отмену: %s", error)
            raise ProviderError(str(error))

        self.ticket_repo.update_status(reg, TicketStatus.CANCELLED.value)
        return {
            "success": True,
            "ticket_id": ticket_id,
            "message": "Отмена успешна",
        }
