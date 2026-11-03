import logging
from typing import Any
from uuid import UUID

import httpx

from settings import EVENTS_PROVIDER_BASE_URL, EVENTS_PROVIDER_API_KEY

logger = logging.getLogger(__name__)


class EventsApiClient:
    def __init__(self, base_url: str | None = None):
        self.api_key = EVENTS_PROVIDER_API_KEY
        if not self.api_key:
            logger.error("❌ EVENTS_PROVIDER_API_KEY не задан")
            raise ValueError(
                "EVENTS_PROVIDER_API_KEY отсутствует. "
                "Проверьте .env локально и переменные окружения на LMS."
            )

        # base_url: приоритет — аргумент (тесты), потом settings (дефолт — внутренний хостнейм кластера)
        url = base_url if base_url is not None else EVENTS_PROVIDER_BASE_URL
        self.base_url = url.rstrip("/")

        headers = {
            "x-api-key": self.api_key,
            "Accept": "application/json",
        }

        # ВАЖНО: AsyncClient для совместимости с FastAPI
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            headers=headers,
            follow_redirects=True,
            timeout=30.0,
        )
        logger.info(f"📡 EventsApiClient инициализирован. URL: {self.base_url}")

    async def _make_request(self, method: str, endpoint: str, **kwargs) -> tuple[dict | None, str | None]:
        try:
            response = await self.client.request(method, endpoint, **kwargs)
            if response.status_code >= 400:
                logger.warning(
                    f"⚠️ HTTP {response.status_code} на {endpoint}. Тело: {response.text[:200]}"
                )
                return None, f"HTTP {response.status_code}: {response.reason_phrase}"
            return response.json(), None
        except httpx.RequestError as e:
            logger.exception("💥 Сетевая ошибка")
            return None, f"Network error: {e!s}"
        except Exception as e:
            logger.exception("💥 Неожиданная ошибка")
            return None, f"Unexpected error: {e!s}"

    # --- Синхронизация: все события через курсорную пагинацию ---
    async def fetch_all_events(self, changed_at: str = "2000-01-01") -> list[dict[str, Any]]:
        """
        Обходит ВСЕ страницы провайдера, переходя по ссылкам в поле next,
        пока next не станет null. Возвращает единый список событий.
        """
        all_events: list[dict[str, Any]] = []
        # Trailing slash обязателен: /api/events/ с параметром changed_at
        endpoint = f"/api/events/?changed_at={changed_at}"

        page = 1
        while endpoint:
            data, error = await self._make_request("GET", endpoint)
            if error:
                raise RuntimeError(error)

            results = data.get("results", []) if isinstance(data, dict) else []
            all_events.extend(results)
            logger.info(
                f"📄 Страница {page}: получено {len(results)} событий "
                f"(всего накоплено {len(all_events)})"
            )

            next_url = data.get("next") if isinstance(data, dict) else None
            if not next_url:
                break

            # next приходит полным URL — отрезаем base_url и работаем с path+query
            if next_url.startswith(self.base_url):
                next_url = next_url[len(self.base_url):]
            endpoint = next_url
            page += 1

        logger.info(f"✅ Всего получено {len(all_events)} событий с провайдера")
        return all_events

    # --- Свободные места ---
    # ВАЖНО: trailing slash — иначе провайдер вернёт 301
    async def get_seats(self, event_id: UUID) -> tuple[dict | None, str | None]:
        endpoint = f"/api/events/{event_id!s}/seats/"
        return await self._make_request("GET", endpoint)

    # --- Регистрация ---
    # Успех — 201 Created
    async def register_ticket(
        self,
        event_id: UUID,
        seat: str,
        email: str,
        first_name: str,
        last_name: str,
    ) -> tuple[dict | None, str | None]:
        endpoint = f"/api/events/{event_id!s}/register/"
        payload = {
            "seat": seat,
            "email": email,
            "first_name": first_name,
            "last_name": last_name,
        }
        return await self._make_request("POST", endpoint, json=payload)

    # --- Отмена регистрации ---
    async def unregister_ticket(
        self,
        event_id: UUID,
        ticket_id: str,
    ) -> tuple[dict | None, str | None]:
        endpoint = f"/api/events/{event_id!s}/unregister/"
        payload = {"ticket_id": ticket_id}
        return await self._make_request("DELETE", endpoint, json=payload)

    async def close(self):
        if self.client:
            await self.client.aclose()
            logger.info("✅ HTTP клиент закрыт")
