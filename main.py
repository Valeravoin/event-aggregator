from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy import select, text, func
from sqlalchemy.exc import SQLAlchemyError
from typing import Optional, List, Dict, Any
from contextlib import asynccontextmanager  # <--- ВАЖНО: этот импорт нужен для lifespan

from database import SessionLocal
from models import Event
from sync_runner import run_sync
# Импортируем функции из scheduler.py, который мы создали ранее
from scheduler import start_scheduler, stop_scheduler  

import logging
from datetime import datetime, timezone

# Настройка логов
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)


# --- ЭТОТ БЛОК ВСТАВИТЬ ПЕРЕД СОЗДАНИЕМ app = FastAPI(...) ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # При старте сервера (когда ты делаешь uvicorn main:app ...)
    logger.info("Запуск приложения: инициализация планировщика")
    start_scheduler()
    
    yield  # Пока сервер работает — планировщик тоже работает
    
    # При остановке сервера (Ctrl+C или перезагрузка)
    logger.info("Остановка приложения: остановка планировщика")
    stop_scheduler()
# --------------------------------------------------------------


app = FastAPI(title="EventAggregator LMS", lifespan=lifespan)  # <--- Передаем lifespan сюда


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# --- Health Check ---
@app.get("/api/health")
def health():
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
        return {"status": "ok"}
    except SQLAlchemyError as e:
        logger.error("Ошибка подключения к БД: %s", e)
        return {"status": "error", "detail": str(e)}


# --- Ручной запуск синхронизации ---
@app.post("/api/sync/trigger")
def trigger_sync():
    logger.info("Ручной запуск синхронизации")
    try:
        result = run_sync()
        return {
            "status": "triggered",
            "details": result,
        }
    except Exception as e:
        logger.exception("Ошибка при запуске синхронизации: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# --- Список событий (с пагинацией и фильтрацией) ---
@app.get("/api/events")
def get_events(
    page: int = 1,
    page_size: int = 20,
    date_from: Optional[str] = None,
    db: Any = Depends(get_db),
):
    if page < 1:
        page = 1
    if page_size < 1 or page_size > 100:
        page_size = 20

    offset = (page - 1) * page_size

    # --- ЗАПРОС 1: Подсчёт общего количества (БЕЗ сортировки!) ---
    count_stmt = select(func.count()).select_from(Event)
    
    if date_from:
        try:
            dt = datetime.strptime(date_from, "%Y-%m-%d")
            dt = dt.replace(tzinfo=timezone.utc)
            count_stmt = count_stmt.where(Event.event_time >= dt)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail="Неверный формат date_from. Используйте YYYY-MM-DD"
            )

    total = db.execute(count_stmt).scalar() or 0


    # --- ЗАПРОС 2: Выборка данных (С сортировкой и пагинацией) ---
    stmt = select(Event).order_by(Event.event_time.desc())

    if date_from:
        # Фильтр можно продублировать, это безопасно
        stmt = stmt.where(Event.event_time >= dt)

    stmt = stmt.limit(page_size).offset(offset)
    results = db.execute(stmt).scalars().all()


    def format_event(ev: Event) -> Dict[str, Any]:
        place = None
        if ev.place_id:
            place = {
                "id": str(ev.place_id) if ev.place_id else None,
                "name": ev.place_name,
                "city": ev.city,
                "address": ev.address,
            }

        return {
            "id": str(ev.id) if ev.id else None,
            "name": ev.name,
            "place": place,
            "event_time": ev.event_time.isoformat() if ev.event_time else None,
            "registration_deadline": ev.registration_deadline.isoformat()
                if ev.registration_deadline else None,
            "status": ev.status,
            "number_of_visitors": ev.number_of_visitors,
        }

    items = [format_event(ev) for ev in results]

    base_url = "http://localhost:8000"
    next_page = None
    if (offset + page_size) < total:
        next_page = f"{base_url}/api/events?page={page + 1}&page_size={page_size}"
        if date_from:
            next_page += f"&date_from={date_from}"

    previous_page = None
    if page > 1:
        previous_page = f"{base_url}/api/events?page={page - 1}&page_size={page_size}"
        if date_from:
            previous_page += f"&date_from={date_from}"

    return {
        "count": total,
        "next": next_page,
        "previous": previous_page,
        "results": items,
    }
