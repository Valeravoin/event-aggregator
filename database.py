import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Загружаем переменные из .env (работает локально)
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "")

# Если DATABASE_URL пустой или указывает на localhost (как сейчас на LMS),
# берём настоящую строку подключения от платформы
if not DATABASE_URL or "localhost" in DATABASE_URL:
    conn = os.getenv("POSTGRES_CONNECTION_STRING", "")
    if conn:
        # SQLAlchemy 2.x требует postgresql+psycopg2://, а платформа даёт postgres://
        conn = conn.replace("postgres://", "postgresql+psycopg2://", 1)
        DATABASE_URL = conn
    else:
        # Если CONNECTION_STRING нет — собираем URL из отдельных переменных
        user = os.getenv("POSTGRES_USERNAME", "")
        pwd = os.getenv("POSTGRES_PASSWORD", "")
        host = os.getenv("POSTGRES_HOST", "")
        port = os.getenv("POSTGRES_PORT", "5432")
        name = os.getenv("POSTGRES_DATABASE_NAME", "")

        if host and name:
            DATABASE_URL = f"postgresql+psycopg2://{user}:{pwd}@{host}:{port}/{name}"

if DATABASE_URL:
    engine = create_engine(DATABASE_URL, echo=False)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
else:
    # Если базы всё ещё нет — не роняем сервер, а просто не создаём подключение
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
