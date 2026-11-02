import logging
import os
from typing import Any

import httpx
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

class EventsApiClient:
    def __init__(self, base_url: str | None = None):
        # 1. Получаем ключ
        self.api_key = os.getenv("EVENTS_PROVIDER_API_KEY")
        
        if not self.api_key:
            logger.error("❌ КЛЮЧ НЕ НАЙДЕН В ENV!")
            raise ValueError("EVENTS_PROVIDER_API_KEY не найден. Проверьте .env и load_dotenv() в main.py")
        else:
            logger.info(f"✅ КЛЮЧ ЗАГРУЖЕН. Длина: {len(self.api_key)} символов")

        # 2. Определяем base_url
        if base_url is None:
            # Если не передан — берём из .env, если нет — ставим дефолт
            self.base_url = os.getenv(
                "EVENTS_PROVIDER_BASE_URL",
                "https://events-provider.dev-2.python-labs.ru"
            )
        else:
            self.base_url = base_url

        self.base_url = self.base_url.rstrip("/")
        logger.info(f"📡 Используем base_url: {self.base_url}")

        # 3. Формируем заголовки
        headers = {
            "x-api-key": self.api_key,
            "Accept": "application/json"
        }

        logger.info("📡 Настройка HTTP-клиента:")
        logger.info(f"   URL: {self.base_url}")
        logger.info(f"   Headers keys: {list(headers.keys())}")
        logger.info(f"   ✅ Используется схема аутентификации: x-api-key (длина ключа: {len(self.api_key)})")


        # 4. Создаём клиент
        self.client = httpx.Client(
            base_url=self.base_url,
            headers=headers,
            follow_redirects=True,
            timeout=10.0
        )
        logger.debug("✅ HTTP клиент успешно инициализирован")

    def _make_request(self, method: str, endpoint: str, **kwargs) -> tuple[dict | None, str | None]:
        """Вспомогательный метод для всех запросов: GET/POST/DELETE и т.д."""
        try:
            response = self.client.request(method, endpoint, **kwargs)
            logger.info(f"📬 Ответ сервера: {response.status_code} {response.reason_phrase}")

            if response.status_code >= 400:
                logger.warning(f"⚠️ Запрос вернул ошибку: {response.status_code}. Тело: {response.text}")
                return None, f"HTTP {response.status_code}: {response.reason_phrase}"

            data = response.json()
            return data, None

        except httpx.RequestError as e:
            logger.exception("💥 Ошибка сети/запроса")
            return None, f"Network error: {e!s}"
        except Exception as e:
            logger.exception("💥 Неожиданная ошибка")
            return None, f"Unexpected error: {e!s}"

    def fetch_all_events(self) -> list[dict[str, Any]]:
        try:
            logger.info("🚀 Отправка запроса: GET /api/events/")
            data, error = self._make_request("GET", "/api/events/")

            if error:
                raise RuntimeError(error)

            # Нормализуем ответ: ищем results/events или возвращаем список
            if isinstance(data, dict):
                if "results" in data:
                    return data["results"]
                if "events" in data:
                    return data["events"]
                return []

            if isinstance(data, list):
                return data

            return []

        except Exception:
            logger.exception("💥 Не удалось получить события")
            raise

    def fetch_events_since(self, since_iso: str) -> list[dict[str, Any]]:
        """
        Получает события, созданные после указанной даты.
        
        :param since_iso: Дата в формате ISO 8601 (например, 2026-11-02T20:30:01.192334+03:00)
        :return: Список событий
        """
        logger.info(f"🚀 Отправка запроса: GET /api/events/?since={since_iso}")
        data, error = self._make_request("GET", "/api/events/", params={"since": since_iso})

        if error:
            raise RuntimeError(error)

        # Нормализация ответа — та же логика, что и в fetch_all_events
        if isinstance(data, dict):
            if "results" in data:
                return data["results"]
            if "events" in data:
                return data["events"]
            return []

        if isinstance(data, list):
            return data

        return []
    


    def get_seats(self, event_id: str) -> tuple[dict | None, str | None]:
        endpoint = f"/api/events/{event_id}/seats"
        return self._make_request("GET", endpoint)

    def register_ticket(
        self,
        event_id: str,
        seat: str,
        email: str,
        first_name: str,
        last_name: str
    ) -> tuple[dict | None, str | None]:
        endpoint = f"/api/events/{event_id}/register"
        payload = {
            "seat": seat,
            "email": email,
            "first_name": first_name,
            "last_name": last_name
        }
        return self._make_request("POST", endpoint, json=payload)

    def unregister_ticket(
        self,
        event_id: str,
        ticket_id: str
    ) -> tuple[dict | None, str | None]:
        endpoint = f"/api/events/{event_id}/unregister"
        payload = {"ticket_id": ticket_id}
        return self._make_request("DELETE", endpoint, json=payload)

    def close(self):
        """Закрывает клиент (вызывай при остановке приложения, если нужно)."""
        if self.client:
            self.client.close()
            logger.info("✅ HTTP клиент закрыт")
