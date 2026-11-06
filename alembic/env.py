
from logging.config import fileConfig

# Твой движок из database.py
# Это важно: чтобы autogenerate видел твои модели (Event, SyncMetadata, Registration)
import models  # noqa: F401
from alembic import context
from database import engine
from models import Base

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Берём строку подключения из движка — alembic.ini больше не участвует
config.set_main_option("sqlalchemy.url", str(engine.url))

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Указываем метаданные, которые Alembic должен использовать для сравнения
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    # Используем тот же engine, что и приложение — без пересборки из конфига
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
