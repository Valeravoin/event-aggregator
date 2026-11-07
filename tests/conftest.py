import os

os.environ.setdefault("DISABLE_STARTUP_SYNC", "1")

# 1) КРИТИЧНО: ставим переменные окружения ДО импортов приложения.
#    - DATABASE_URL нужен до импорта database.py — весь движок уйдёт на SQLite.
#    - EVENTS_PROVIDER_* нужен до создания EventsApiClient — иначе клиент
#      не инициализируется и API отдаёт 503 вместо того, чтобы дойти до мока.
TEST_DB_PATH = "test_event_aggregator.db"
os.environ["DATABASE_URL"] = f"sqlite:///./{TEST_DB_PATH}"
os.environ.setdefault("EVENTS_PROVIDER_API_KEY", "test-key")
os.environ.setdefault("EVENTS_PROVIDER_BASE_URL", "https://provider.example.com")

# Удаляем старый файл тестовой базы, чтобы не мешали данные от прошлых запусков
if os.path.exists(TEST_DB_PATH):
    os.remove(TEST_DB_PATH)

# 2) Только теперь импортируем приложение — оно создаст engine на SQLite
import uuid
from collections.abc import Generator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from database import SessionLocal, engine, get_db
from main import app
from models import Base, Event


@pytest.fixture(scope="function")
def db() -> Generator[Session, None, None]:
    """Сессия к той самой SQLite-базе, на которую смотрит всё приложение."""
    Base.metadata.create_all(bind=engine)
    db_session = SessionLocal()
    try:
        yield db_session
    finally:
        db_session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def client(db: Session) -> Generator[TestClient, None, None]:
    """TestClient. Подмену зависимостей оставляем для надёжности — БД теперь и так общая."""

    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app, raise_server_exceptions=False) as c:
        yield c

    app.dependency_overrides.clear()


@pytest.fixture
def valid_event(db: Session) -> Event:
    """Реальное событие в тестовой БД."""
    now_utc = datetime.now(UTC)
    new_event = Event(
        id=uuid.uuid4(),
        name="Test Conference 2026",
        place_id=str(uuid.uuid4()),
        place_name="Hall A",
        city="Moscow",
        address="Test St. 1",
        event_time=now_utc + timedelta(days=30),
        registration_deadline=now_utc + timedelta(days=10),
        status="published",
        number_of_visitors=50,
        last_changed_at=now_utc,
    )
    db.add(new_event)
    db.commit()
    db.refresh(new_event)
    return new_event
