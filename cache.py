import time
from typing import Any


class SimpleCache:
    """
    Простой кэш в памяти.
    Хранит данные ограниченное время (TTL) и умеет отдавать их по ключу.
    Для продакшена тут ставят Redis, но для твоего проекта этого хватит.
    """

    def __init__(self, default_ttl_seconds: int = 60):
        self._data: dict[str, Any] = {}
        self._timestamps: dict[str, float] = {}
        self.default_ttl_seconds = default_ttl_seconds

    def get(self, key: str) -> Any | None:
        """Получить значение. Вернет None, если ключа нет или время истекло."""
        if key not in self._data:
            return None

        ts = self._timestamps.get(key, 0)
        # Если прошло больше времени, чем TTL — считаем данные устаревшими
        if time.time() - ts > self.default_ttl_seconds:
            self.delete(key)
            return None

        return self._data[key]

    def set(self, key: str, value: Any, ttl_seconds: int | None = None):
        """Сохранить значение с временем жизни."""
        self._data[key] = value
        self._timestamps[key] = time.time()

    def delete(self, key: str):
        """Удалить конкретный ключ."""
        self._data.pop(key, None)
        self._timestamps.pop(key, None)

    def clear(self):
        """Очистить весь кэш (полезно при рестарте)."""
        self._data.clear()
        self._timestamps.clear()

# Создаем глобальный экземпляр кэша, чтобы он жил всё время работы приложения
seats_cache = SimpleCache(default_ttl_seconds=60)
