# http_client.py
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone, timedelta  # <-- обязательно добавь timedelta
import httpx
import logging

logger = logging.getLogger(__name__)

class EventsApiClient:
    def __init__(
        self,
        base_url: str,
        api_key: Optional[str] = None,
        timeout: float = 10.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.headers = {}
        if api_key:
            self.headers["Authorization"] = f"Bearer {api_key}"

        self.client = httpx.Client(
            headers=self.headers,
            timeout=timeout,
            follow_redirects=True,
        )

    def fetch_events_since(self, last_sync_time: Optional[datetime]) -> List[Dict[str, Any]]:
        from datetime import datetime, timezone, timedelta
        import uuid
        
        now = datetime.now(timezone.utc)
        
        # Используем тот же UUID, что и в прошлый раз, чтобы сработал UPDATE
        fixed_uuid_1 = "2b0e4f8a-ab87-4364-8716-322651846a02"  # Это ID события «Фестиваль науки» из твоей базы
        
        return [
            {
                "id": fixed_uuid_1,
                # Вот тут мы меняем название — это и есть тест обновления
                "name": "Фестиваль науки [ОБНОВЛЕНО: добавлена программа]",
                "event_time": (now + timedelta(days=1)).replace(hour=18, minute=0, second=0),
                "status": "confirmed",
                "place_id": "place-msk-1",
                "place_name": "Школа №1",
                "city": "Москва",
                "address": "ул. Ленина, 1",
                "registration_deadline": (now + timedelta(hours=5)),
                "number_of_visitors": 180,  # Даже число посетителей поменяем
                "last_changed_at": now,
            },
            # Второе событие оставим как новое, чтобы проверить, что оно тоже вставится
            {
                "id": str(uuid.uuid4()),
                "name": "Лекция про FastAPI",
                "event_time": (now + timedelta(days=2)).replace(hour=19, minute=30, second=0),
                "status": "draft",
                "place_id": "place-spb-3",
                "place_name": "Технопарк",
                "city": "Санкт-Петербург",
                "address": "пр. Науки, 10",
                "registration_deadline": None,
                "number_of_visitors": None,
                "last_changed_at": now,
            }
        ]



        # ---------------------------------------------------------
        # НИЖЕ — РЕАЛЬНЫЙ КОД (закомментирован, чтобы не мешал тесту)
        # endpoint = "/api/events"
        # params = {}
        #
        # if last_sync_time is None:
        #     params["since"] = datetime(2000, 1, 1, tzinfo=timezone.utc).isoformat()
        # else:
        #     params["since"] = last_sync_time.isoformat()
        #
        # try:
        #     url = f"{self.base_url}{endpoint}"
        #     logger.info("Запрос событий: %s?%s", url, params)
        #     response = self.client.get(url, params=params)
        #     response.raise_for_status()
        #
        #     data = response.json()
        #     if not isinstance(data, list):
        #         raise ValueError("API вернул не список событий")
        #
        #     events = []
        #     for item in data:
        #         event_time = self._parse_datetime(item.get("event_time"))
        #         last_changed_at = self._parse_datetime(item.get("last_changed_at"))
        #         registration_deadline = self._parse_datetime(item.get("registration_deadline"))
        #
        #         events.append({
        #             "id": item.get("id"),
        #             "name": item.get("name"),
        #             "event_time": event_time,
        #             "status": item.get("status", "unknown"),
        #             "place_id": item.get("place_id"),
        #             "place_name": item.get("place_name"),
        #             "city": item.get("city"),
        #             "address": item.get("address"),
        #             "registration_deadline": registration_deadline,
        #             "number_of_visitors": item.get("number_of_visitors"),
        #             "last_changed_at": last_changed_at,
        #         })
        #
        #     logger.info("Получено событий: %d", len(events))
        #     return events
        #
        # except httpx.RequestError as e:
        #     logger.error("Ошибка сети при запросе к API: %s", e)
        #     raise RuntimeError(f"Ошибка запроса к API: {e}") from e
        # except httpx.HTTPStatusError as e:
        #     logger.error("HTTP-ошибка от API: %d", e.response.status_code)
        #     raise RuntimeError(f"HTTP-ошибка от API: {e.response.status_code}") from e
        # except ValueError as e:
        #     logger.error("Неверный формат ответа от API: %s", e)
        #     raise RuntimeError(f"Неверный формат ответа от API: {e}") from e


    @staticmethod
    def _parse_datetime(value: Any) -> Optional[datetime]:
        """Превращает строку ISO или datetime в aware datetime (UTC)."""
        if value is None:
            return None

        if isinstance(value, datetime):
            if value.tzinfo is None:
                return value.replace(tzinfo=timezone.utc)
            return value

        if isinstance(value, str):
            try:
                # Заменяем Z на +00:00 для совместимости
                dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    return dt.replace(tzinfo=timezone.utc)
                return dt
            except ValueError:
                logger.warning("Не удалось распарсить дату: %s", value)
                return None

        return None

    def close(self):
        self.client.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
