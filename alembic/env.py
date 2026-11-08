import os
from logging.config import fileConfig

from dotenv import load_dotenv
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import context

# Подключаем Base из твоего проекта
from models import Base

load_dotenv()  # подхватываем .env так же, как это делает settings.py


config = context.config
fileConfig(config.config_file_name)

# Получаем DATABASE_URL из env (как в settings.py)
target_metadata = Base.metadata

def run_migrations_offline() -> None:
    """Запускает миграции без подключения к БД (редко используется)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()

def get_database_url() -> str:
    """Строка подключения — из переменной окружения, как в settings.py."""
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "DATABASE_URL не задан. Экспортируй переменную окружения "
            "или добавь её в .env перед запуском alembic."
        )
    return url


async def run_migrations_online() -> None:
    """Запускает миграции с реальным подключением к БД (наш случай)."""
    connectable = create_async_engine(
        get_database_url(),
        echo=False,
        poolclass=pool.NullPool,
    )


    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)


def do_run_migrations(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
    )
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    import asyncio
    asyncio.run(run_migrations_online())
