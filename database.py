import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

# Загружаем переменные из .env. Если файла нет — переменные не появятся,
# и дальше сработает проверка на отсутствие DATABASE_URL.
load_dotenv()

from models import Base  

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError(
        "Не найдена переменная DATABASE_URL в файле .env. "
        "Создай файл .env в корне проекта и добавь туда строку: "
        "DATABASE_URL=postgresql+psycopg2://postgres:secret@localhost:5432/event_aggregator"
    )

engine = create_engine(DATABASE_URL, echo=False)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

