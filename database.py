import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Загружаем переменные из .env. Если файла нет — переменные не появятся,
# а приложение всё равно стартует: падать будем только при обращении к базе.
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "")

if DATABASE_URL:
    engine = create_engine(DATABASE_URL, echo=False)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
else:
    # На платформе .env нет (он в .dockerignore) — не роняем старт,
    # а просто не создаём подключение. Любой запрос к базе ответит ошибкой.
    engine = None
    SessionLocal = None


def get_db():
    if SessionLocal is None:
        raise RuntimeError(
            "База данных не настроена: переменная DATABASE_URL не задана. "
            "Укажи её в переменных окружения сервиса."
        )
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
