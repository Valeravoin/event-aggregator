from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from settings import DATABASE_URL

if DATABASE_URL:
    engine = create_engine(DATABASE_URL, echo=False)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
else:
    # Базы нет — не роняем сервер, а просто не создаём подключение
    engine = None
    SessionLocal = None


def get_db():
    if SessionLocal is None:
        raise RuntimeError(
            "База данных не настроена: не удалось собрать строку подключения. "
            "Укажи DATABASE_URL или переменные POSTGRES_* в окружении сервиса."
        )
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
