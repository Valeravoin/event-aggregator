import logging
import time
from typing import Any
from uuid import UUID

from exceptions import DomainError, EventNotFoundError, ProviderError
from http_client import EventsApiClient
from models import EventStatus
from repositories.event_repository import EventRepository
from repositories.registration_repository import RegistrationRepository

logger = logging.getLogger(__name__)

CACHE_TTL = 60  # секунд

# Кэш на уровне модуля — живёт между запросами, как раньше
seats_cache: dict[str, tuple[float, dict]] = {}


class SeatsUseCase:
    def __init__(
        self,
        event_repo: EventRepository,
        ticket_repo: RegistrationRepository,
        client: EventsApiClient | None,
    ):
        self.event_repo = event_repo
        self.ticket_repo = ticket_repo
        self.client = client

    async def do(self, event_id: UUID) -> dict:
        cache_key = str(event_id)
        now = time.time()

        cached = seats_cache.get(cache_key)
        if cached is not None:
            ts, data = cached
            if now - ts < CACHE_TTL:
                logger.info("💾 Возвращаем данные из кэша для события %s", cache_key)
                return data

        event = self.event_repo.get_by_id(event_id)
        if not event:
            raise EventNotFoundError()
        if event.status != EventStatus.PUBLISHED.value:
            raise DomainError(
                f"Registration is only available for published events. Status: {event.status}",
                status_code=403,
            )
        if self.client is None:
            raise DomainError(
                "Provider client is not initialized: check EVENTS_PROVIDER_* env variables",
                status_code=503,
            )

        logger.info("🌐 Запрос свободных мест у Events Provider для %s", cache_key)
        seats_data, error = await self.client.get_seats(event_id)
        if error is not None:
            raise ProviderError(f"Seats provider is unavailable: {error}")

        taken = self.ticket_repo.get_taken_seats(event_id)
        available = [s for s in self._normalize(seats_data) if s not in taken]

        response = {"event_id": cache_key, "available_seats": available}
        seats_cache[cache_key] = (now, response)
        return response

    @staticmethod
    def _normalize(raw: Any) -> list[str]:
        """Нормализуем ответ провайдера в список мест."""
        if isinstance(raw, dict):
            raw = raw.get("available_seats", raw.get("seats", []))
        seats: list[str] = []
        if isinstance(raw, list):
            for s in raw:
                if isinstance(s, str):
                    seats.append(s)
                elif isinstance(s, dict):
                    seat_value = s.get("seat") or s.get("number") or s.get("id")
                    if seat_value is not None:
                        seats.append(str(seat_value))
        return seats
