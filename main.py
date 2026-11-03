import logging
import time
from typing import Any
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from database import SessionLocal, engine
from http_client import EventsApiClient
from models import Base

# Слой зависимостей
from repositories.event_repository import EventRepository
from repositories.registration_repository import RegistrationRepository
from scheduler import create_scheduler
from schemas import TicketRequest
from services.ticket_cancellation_usecase import TicketCancellationUseCase
from services.ticket_registration_usecase import TicketRegistrationUseCase
from settings import EVENTS_PROVIDER_BASE_URL
from sync_runner import run_sync

# --- ГЛОБАЛЬНЫЙ КЛИЕНТ (КРИТИЧНО ДЛЯ ТЕСТОВ) ---
# Мы создаем его здесь, чтобы тесты могли делать patch.object(main.client, ...)
if not EVENTS_PROVIDER_BASE_URL:
    raise RuntimeError("EVENTS_PROVIDER_BASE_URL не установлен в переменных окружения!")

client = EventsApiClient(base_url=EVENTS_PROVIDER_BASE_URL)

# --- КЭШ МЕСТ ---
# Ключ теперь всегда строка (str), чтобы избежать проблем с хешированием UUID в словарях
_seats_cache: dict[str, tuple[float, dict[str, Any]]] = {}
CACHE_TTL = 30

Base.metadata.create_all(bind=engine)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

# Инициализируем планировщик (создаём объект, но НЕ запускаем)
scheduler = create_scheduler()

app = FastAPI(title="EventAggregator LMS")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.on_event("startup")
async def startup():
    """
    Этот блок выполняется ТОЛЬКО при старте FastAPI-сервера (через uvicorn).
    В тестах он не запускается автоматически, если ты не используешь TestClient с live-server.
    Здесь можно делать лёгкие проверки, но тяжёлые задачи лучше не ставить.
    """
    logger.info("🚀 Приложение EventAggregator запущено.")


if __name__ == "__main__":
    # --- ЭТОТ БЛОК ВЫПОЛНЯЕТСЯ ТОЛЬКО ПРИ ЗАПУСКЕ СЕРВЕРА, НЕ В ТЕСТАХ ---

    # 1. Ручной запуск синхронизации при старте (один раз)
    logger.info("🔄 Запуск ручной синхронизации при старте сервера...")
    with SessionLocal() as db:
        try:
            success = run_sync(db, source_name="startup-source")
            if success:
                logger.info("✅ Ручная синхронизация при старте завершена.")
            else:
                logger.warning("⚠️ Ручная синхронизация при старте частично не удалась.")
        except Exception:
            logger.exception("💥 Ошибка при ручной синхронизации при старте")

    # 2. Запуск планировщика (фоновая задача каждые 24 часа)
    try:
        scheduler.start()
        logger.info("🕒 Планировщик запущен: интервал 24 часа.")
    except Exception as e:
        logger.error("Не удалось запустить планировщик: %s", e)
        # Важно: даже если планировщик не запустился, сервер может работать дальше,
        # просто не будет автоматической синхронизации.

    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)


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
def trigger_sync(db: Session = Depends(get_db)):
    success = run_sync(db)
    if success:
        return {"status": "success", "message": "Синхронизация завершена"}
    else:
        return {"status": "failed", "message": "Синхронизация завершилась с ошибкой (см. логи)"}

# --- Детали события ---
@app.get("/api/events/{event_id}")
def get_event_details(event_id: UUID, db: Session = Depends(get_db)):
    repo = EventRepository(db)
    event = repo.get_by_id(event_id)

    if not event:
        raise HTTPException(status_code=404, detail="Событие не найдено")

    place = None
    if event.place_id:
        place = {
            "id": str(event.place_id),
            "name": event.place_name,
            "city": event.city,
            "address": event.address,
            "seats_pattern": "A1-1000,B1-2000",
        }

    return {
        "id": str(event.id),
        "name": event.name,
        "place": place,
        "event_time": event.event_time.isoformat() if event.event_time else None,
        "registration_deadline": event.registration_deadline.isoformat()
            if event.registration_deadline else None,
        "status": event.status,
        "number_of_visitors": event.number_of_visitors,
    }

# --- Список событий с пагинацией ---
@app.get("/api/events")
def list_events(page: int = 1, per_page: int = 10, db: Session = Depends(get_db)):
    if page < 1:
        raise HTTPException(status_code=400, detail="page должна быть >= 1")
    if not (1 <= per_page <= 100):
        raise HTTPException(status_code=400, detail="per_page должна быть от 1 до 100")

    repo = EventRepository(db)
    total = repo.count_events()
    events = repo.get_events_page(offset=(page - 1) * per_page, limit=per_page)

    return {
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page,
        "items": [
            {
                "id": str(ev.id),
                "name": ev.name,
                "place_name": ev.place_name,
                "city": ev.city,
                "event_time": ev.event_time.isoformat() if ev.event_time else None,
                "registration_deadline": (
                    ev.registration_deadline.isoformat()
                    if ev.registration_deadline else None
                ),
                "status": ev.status,
            }
            for ev in events
        ],
    }


# --- Свободные места (с кэшем) ---
@app.get("/api/events/{event_id}/seats")
async def get_available_seats(event_id: UUID, db: Session = Depends(get_db)):   # ✅ async
    now = time.time()
    cache_key = str(event_id)

    if cache_key in _seats_cache:
        ts, cached_data = _seats_cache[cache_key]
        if now - ts < CACHE_TTL:
            logger.info(f"💾 Возвращаем данные из кэша для события {cache_key}")
            return cached_data

    repo = EventRepository(db)
    event = repo.get_by_id(event_id)

    if not event:
        raise HTTPException(status_code=404, detail="Событие не найдено в агрегаторе")

    if event.status != "published":
        raise HTTPException(
            status_code=403,
            detail=f"Регистрация возможна только для опубликованных событий. Статус: {event.status}"
        )

    logger.info(f"🌐 Запрос свободных мест у Events Provider для {cache_key}")
    seats_data, error = await client.get_seats(event_id)   # ✅ await добавлен

    if error:
        raise HTTPException(status_code=502, detail=f"Ошибка провайдера: {error}")

    _seats_cache[cache_key] = (time.time(), seats_data)
    return seats_data


# --- Регистрация (через UseCase) ---
@app.post("/api/tickets", status_code=201)
async def register_ticket(ticket: TicketRequest, db: Session = Depends(get_db)):
    event_repo = EventRepository(db)
    ticket_repo = RegistrationRepository(db)

    usecase = TicketRegistrationUseCase(
        event_repo=event_repo,
        ticket_repo=ticket_repo,
        client=client,
    )

    try:
        result = await usecase.do(
            first_name=ticket.first_name,
            last_name=ticket.last_name,
            email=ticket.email,
            event_id=ticket.event_id,  # Это уже UUID благодаря Pydantic
            seat=ticket.seat,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        msg = str(e)
        status_code = int(msg.split(":")[0]) if ":" in msg else 500
        detail = msg.split(":", 1)[1] if ":" in msg else msg
        raise HTTPException(status_code=status_code, detail=detail)


# --- Отмена регистрации (через UseCase) ---
@app.delete("/api/tickets/{ticket_id}")
def cancel_ticket(ticket_id: str, db: Session = Depends(get_db)):
    event_repo = EventRepository(db)
    ticket_repo = RegistrationRepository(db)

    usecase = TicketCancellationUseCase(
        event_repo=event_repo,
        ticket_repo=ticket_repo,
        client=client,
    )

    try:
        result = usecase.do(ticket_id=ticket_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        msg = str(e)
        if ":" in msg:
            status_code = int(msg.split(":")[0])
            detail = msg.split(":", 1)[1]
            raise HTTPException(status_code=status_code, detail=detail)
        raise HTTPException(status_code=500, detail=msg)
