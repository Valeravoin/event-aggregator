# http_client.py
import logging
import os
from typing import Any
from uuid import UUID

import httpx
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

class EventsApiClient:
    def __init__(self, base_url: str | None = None):
        self.api_key = os.getenv("EVENTS_PROVIDER_API_KEY")
        if not self.api_key:
            logger.error("❌ EVENTS_PROVIDER_API_KEY не найден в .env")
            raise ValueError("EVENTS_PROVIDER_API_KEY отсутствует. Проверьте .env")

        # base_url: приоритет — аргумент, потом .env, потом дефолт
        if base_url is None:
            self.base_url = os.getenv(
                "EVENTS_PROVIDER_BASE_URL",
                "https://events-provider.dev-2.python-labs.ru"
            )
        else:
            self.base_url = base_url

        self.base_url = self.base_url.rstrip("/")

        headers = {
            "x-api-key": self.api_key,
            "Accept": "application/json"
        }

        # ВАЖНО: используем AsyncClient для совместимости с FastAPI
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            headers=headers,
            follow_redirects=True,
            timeout=10.0
        )
        logger.info(f"📡 EventsApiClient инициализирован. URL: {self.base_url}")

    async def _make_request(self, method: str, endpoint: str, **kwargs) -> tuple[dict | None, str | None]:
        try:
            response = await self.client.request(method, endpoint, **kwargs)
            if response.status_code >= 400:
                logger.warning(f"⚠️ HTTP {response.status_code} на {endpoint}. Тело: {response.text[:200]}")
                return None, f"HTTP {response.status_code}: {response.reason_phrase}"
            return response.json(), None
        except httpx.RequestError as e:
            logger.exception("💥 Сетевая ошибка")
            return None, f"Network error: {e!s}"
        except Exception as e:
            logger.exception("💥 Неожиданная ошибка")
            return None, f"Unexpected error: {e!s}"

    # --- Методы под реальный API провайдера ---
    # Теперь event_id — UUID, как в FastAPI и Pydantic
    async def get_seats(self, event_id: UUID) -> tuple[dict | None, str | None]:
        endpoint = f"/api/events/{event_id!s}/seats"
        return await self._make_request("GET", endpoint)

    # Упрощённая сигнатура: только то, что реально нужно для регистрации
    async def register_ticket(
        self,
        event_id: UUID,
        seat: str,
        email: str,
        first_name: str,
        last_name: str
    ) -> tuple[dict | None, str | None]:
        endpoint = f"/api/events/{event_id!s}/register"
        payload = {
            "seat": seat,
            "email": email,
            "first_name": first_name,
            "last_name": last_name
        }
        return await self._make_request("POST", endpoint, json=payload)

    async def unregister_ticket(
        self,
        event_id: UUID,
        ticket_id: str
    ) -> tuple[dict | None, str | None]:
        endpoint = f"/api/events/{event_id!s}/unregister"
        payload = {"ticket_id": ticket_id}
        return await self._make_request("DELETE", endpoint, json=payload)

    async def fetch_all_events(self) -> list[dict[str, Any]]:
        data, error = await self._make_request("GET", "/api/events/")
        if error:
            raise RuntimeError(error)
        if isinstance(data, dict):
            return data.get("results", data.get("events", []))
        return data if isinstance(data, list) else []

    async def close(self):
        if self.client:
            await self.client.aclose()
            logger.info("✅ HTTP клиент закрыт")
