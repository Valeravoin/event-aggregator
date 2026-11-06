import os
from urllib.parse import quote_plus

from dotenv import load_dotenv

# Единственная точка загрузки .env во всём приложении.
# Все остальные модули получают конфигурацию только через импорт settings.
load_dotenv()


def _build_database_url() -> str | None:
    """Собирает строку подключения к БД.

    Приоритет: DATABASE_URL из окружения -> POSTGRES_CONNECTION_STRING
    (строка от платформы LMS) -> отдельные переменные POSTGRES_*.
    Если настроить базу не удалось — возвращает None.
    """
    url = os.getenv("DATABASE_URL", "")

    # Пустая или локальная строка может быть перекрыта платформенной
    if not url or "localhost" in url:
        conn = os.getenv("POSTGRES_CONNECTION_STRING", "")
        if conn:
            # SQLAlchemy 2.x требует postgresql+psycopg2://, платформа даёт postgres://
            return conn.replace("postgres://", "postgresql+psycopg2://", 1)

        user = os.getenv("POSTGRES_USERNAME", "")
        host = os.getenv("POSTGRES_HOST", "")
        name = os.getenv("POSTGRES_DATABASE_NAME", "")
        if host and name:
            pwd = quote_plus(os.getenv("POSTGRES_PASSWORD", ""))
            port = os.getenv("POSTGRES_PORT", "5432")
            return f"postgresql+psycopg2://{user}:{pwd}@{host}:{port}/{name}"

    return url or None


DATABASE_URL = _build_database_url()

EVENTS_PROVIDER_BASE_URL = os.getenv(
    "EVENTS_PROVIDER_BASE_URL",
    "http://student-system-events-provider-web.student-system-events-provider.svc:8000",
)
EVENTS_PROVIDER_API_KEY = os.getenv("EVENTS_PROVIDER_API_KEY", "")
