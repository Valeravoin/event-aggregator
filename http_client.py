import logging
from typing import Any
from uuid import UUID

import httpx

from settings import EVENTS_PROVIDER_API_KEY, EVENTS_PROVIDER_BASE_URL

logger = logging.getLogger(__name__)


class EventsPaginator:
    """Итератор по страницам провайдера (паттерн Iterator).

    Реальная загрузка асинхронная — используйте ``async for page in paginator:``.
    Синхронный протокол (__iter__/__next__) отдаёт страницы, уже попавшие
    в буфер, — удобно для постобработки и юнит-тестов.
    """

    def __init__(
        self,
        client: "EventsApiClient",
        endpoint: str,
        params: dict[str, Any] | None = None,
    ):
        self._client = client
        self._first_endpoint = endpoint
        self._params = params or {}
        self._next_endpoint: str | None = endpoint
        self._buffer: list[list[dict[str, Any]]] = []
        self._position = 0

    # --- синхронный протокол: поверх уже загруженных страниц ---
    def __iter__(self) -> "EventsPaginator":
        self._position = 0
        return self

    def __next__(self) -> list[dict[str, Any]]:
        if self._position < len(self._buffer):
            page = self._buffer[self._position]
            self._position += 1
            return page
        raise StopIteration

    # --- асинхронный протокол: реальная загрузка с провайдера ---
    def __aiter__(self) -> "EventsPaginator":
        return self

    async def __anext__(self) -> list[dict[str, Any]]:
        if self._position >= len(self._buffer):
            if self._next_endpoint is None:
                raise StopAsyncIteration
            page = await self._fetch_page()
            self._buffer.append(page)
        page = self._buffer[self._position]
        self._position += 1
        return page

    async def _fetch_page(self) -> list[dict[str, Any]]:
        data, error = await self._client._make_request(
            "GET", self._next_endpoint, params=self._params or None
        )
        # Параметры (например, changed_at) нужны только на первом запросе:
        # дальше query уже зашит в next-URL от провайдера.
        self._params = {}

        if error:
            raise RuntimeError(error)

        if isinstance(data, dict):
            results = data.get("results") or []
            next_url = data.get("next")
        else:
            logger.warning("📄 Провайдер вернул несловарный ответ: %r", data)
            results, next_url = [], None

        # next приходит полным URL — отрезаем base_url, оставляем path+query
        if next_url and next_url.startswith(self._client.base_url):
            next_url = next_url[len(self._client.base_url):]
        self._next_endpoint = next_url
        return results


class EventsApiClient:
    def __init__(self, base_url: str | None = None):
        self.api_key = EVENTS_PROVIDER_API_KEY
        if not self.api_key:
            logger.error("❌ EVENTS_PROVIDER_API_KEY не задан")
            raise ValueError(
                "EVENTS_PROVIDER_API_KEY отсутствует. "
                "Проверьте .env локально и переменные окружения на LMS."
            )

        # base_url: приоритет — аргумент (тесты), потом settings
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
        logger.info("📡 EventsApiClient инициализирован. URL: %s", self.base_url)

    async def _make_request(
        self, method: str, endpoint: str, **kwargs
    ) -> tuple[dict | None, str | None]:
        try:
            response = await self.client.request(method, endpoint, **kwargs)
            if response.status_code >= 400:
                logger.warning(
                    "⚠️ HTTP %d на %s. Тело: %s",
                    response.status_code, endpoint, response.text[:200],
                )
                return None, f"HTTP {response.status_code}: {response.reason_phrase}"
            return response.json(), None
        except httpx.RequestError as e:
            logger.exception("💥 Сетевая ошибка")
            return None, f"Network error: {e!s}"
        except Exception as e:
            logger.exception("💥 Неожиданная ошибка")
            return None, f"Unexpected error: {e!s}"

    # --- Синхронизация: все события через итератор страниц ---
    async def fetch_all_events(self, changed_at: str = "2000-01-01") -> list[dict[str, Any]]:
        """Собирает события со всех страниц провайдера в единый список."""
        all_events: list[dict[str, Any]] = []
        paginator = EventsPaginator(self, "/api/events/", params={"changed_at": changed_at})

        async for page in paginator:
            all_events.extend(page)
            logger.info(
                "📄 Получено событий на странице: %d (всего накоплено %d)",
                len(page), len(all_events),
            )

        logger.info("✅ Всего получено %d событий с провайдера", len(all_events))
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
