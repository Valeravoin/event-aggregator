import os
import sqlalchemy as sa


os.environ.setdefault("DISABLE_STARTUP_SYNC", "1")

# 1) Переменные окружения — ДО импортов приложения
TEST_DB_PATH = "test_event_aggregator.db"
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///./{TEST_DB_PATH}"
os.environ.setdefault("EVENTS_PROVIDER_API_KEY", "test-key")
os.environ.setdefault("EVENTS_PROVIDER_BASE_URL", "https://provider.example.com")

# Удаляем старый файл тестовой базы
if os.path.exists(TEST_DB_PATH):
    os.remove(TEST_DB_PATH)

# 2) Перезаряжаем движок с NullPool до импорта main.
# AsyncSession привязана к event loop, а TestClient живёт в своём потоке со
# своим loop. NullPool гарантирует, что соединения не переиспользуются
# между loop'ами — иначе получим «database is locked» и «attached to
# a different loop».
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

import database

database.engine = create_async_engine(os.environ["DATABASE_URL"], poolclass=NullPool)
database.SessionLocal = async_sessionmaker(bind=database.engine, expire_on_commit=False)

# 3) Только теперь импортируем приложение
import uuid
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient

from main import app
from models import Base, Event


@pytest_asyncio.fixture
async def db():
    """Async-сессия к той самой SQLite-базе, на которую смотрит приложение."""
    async with database.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with database.SessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
            async with database.engine.begin() as conn:
                await conn.run_sync(Base.metadata.drop_all)
                # alembic_version не входит в Base.metadata — сносим вручную,
                # иначе следующая миграция посчитает себя применённой и не
                # пересоздаст таблицы
                await conn.execute(sa.text("DROP TABLE IF EXISTS alembic_version"))



@pytest.fixture
def client():
    """TestClient. Override get_db не нужен: database смотрит на тестовую SQLite."""
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


@pytest_asyncio.fixture
async def valid_event(db) -> Event:
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
    await db.commit()
    await db.refresh(new_event)
    return new_event
