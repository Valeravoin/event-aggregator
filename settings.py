import os
from urllib.parse import quote_plus

from dotenv import load_dotenv

load_dotenv()


def _build_database_url() -> str:
    # Локально используем DATABASE_URL из .env, если он задан
    url = os.getenv("DATABASE_URL")
    if url:
        return url

    # На платформе LMS база описывается переменными POSTGRES_*
    user = os.getenv("POSTGRES_USERNAME", "postgres")
    password = quote_plus(os.getenv("POSTGRES_PASSWORD", "secret"))
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    name = os.getenv("POSTGRES_DATABASE_NAME", "event_aggregator")
    return f"postgresql://{user}:{password}@{host}:{port}/{name}"


DATABASE_URL = _build_database_url()

EVENTS_PROVIDER_BASE_URL = os.getenv(
    "EVENTS_PROVIDER_BASE_URL",
    "http://student-system-events-provider-web.student-system-events-provider.svc:8000",
)
EVENTS_PROVIDER_API_KEY = os.getenv("EVENTS_PROVIDER_API_KEY", "")
