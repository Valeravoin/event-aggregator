from sqlalchemy import create_engine
# Подключаем функцию для создания соединения с базой данных

from models import Base
# Берём базовый класс из models.py — через него SQLAlchemy знает про все твои таблицы (Event, Registration и т.д.)

DATABASE_URL = "postgresql+psycopg2://postgres:secret@localhost:5432/event_aggregator"
# Строка подключения: кто, куда и к какой базе идёт (пользователь, пароль, сервер, порт, имя БД)

print("🔌 Подключаемся к базе...")
# Просто выводим сообщение в консоль, чтобы ты видел, на каком этапе скрипт

engine = create_engine(DATABASE_URL, echo=False)
# Создаём «движок» (engine) — это канал связи с PostgreSQL; echo=False отключает вывод всех SQL-команд в лог

print("🚀 Создаю таблицы...")
# Выводим сообщение, что сейчас начнётся проверка/создание таблиц

Base.metadata.create_all(bind=engine)
# Главная команда: смотрит на все модели из Base и создаёт таблицы в базе, если их ещё нет; если есть — ничего не ломает

print("✅ Таблицы успешно созданы или уже существуют!")
# Сообщаем, что этап прошёл успешно

print("📋 В базе теперь есть таблицы:", list(Base.metadata.tables.keys()))
# Показываем список таблиц, которые SQLAlchemy видит в этой схеме (чтобы ты убедился: sync_metadata, events, registrations на месте)
