from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from settings import DATABASE_URL

if DATABASE_URL:
    engine = create_async_engine(DATABASE_URL, echo=False)
    # expire_on_commit=False — чтобы после commit не было ленивой подгрузки
    # атрибутов: в async-режиме это невозможно без await
    SessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False)
else:
    # Базы нет — не роняем сервер, а просто не создаём подключение
    engine = None
    SessionLocal = None


async def get_db():
    if SessionLocal is None:
        raise RuntimeError(
            "База данных не настроена: не удалось собрать строку подключения. "
            "Укажи DATABASE_URL или переменные POSTGRES_* в окружении сервиса."
        )
    async with SessionLocal() as db:
        yield db
