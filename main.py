import logging
import time
from typing import Any
from urllib.parse import urlencode
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy.orm import Session

from database import SessionLocal
from http_client import EventsApiClient

# Слой зависимостей
from repositories.event_repository import EventRepository
from repositories.registration_repository import RegistrationRepository
from scheduler import create_scheduler
from schemas import TicketRequest
from services.ticket_cancellation_usecase import TicketCancellationUseCase
from services.ticket_registration_usecase import TicketRegistrationUseCase
from settings import EVENTS_PROVIDER_BASE_URL
from sync_runner import run_sync

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

# --- ГЛОБАЛЬНЫЙ КЛИЕНТ (КРИТИЧНО ДЛЯ ТЕСТОВ) ---
# Создаём на уровне модуля, чтобы тесты могли делать patch.object(main.client, ...).
# Оборачиваем в try/except: если env не задан, модуль НЕ должен упасть —
# иначе uvicorn не стартует и nginx отдаёт 502/503 на все запросы.
client: EventsApiClient | None = None
try:
    if not EVENTS_PROVIDER_BASE_URL:
        logger.error("❌ EVENTS_PROVIDER_BASE_URL не установлен в переменных окруженияx!")
    else:
        client = EventsApiClient(base_url=EVENTS_PROVIDER_BASE_URL)
        logger.info("✅ Глобальный клиент EventsApiClient создан")
except Exception:
    logger.exception("💥 Не удалось создать EventsApiClient — проверь env на платформе")


# --- КЭШ МЕСТ ---
_seats_cache: dict[str, tuple[float, dict[str, Any]]] = {}
CACHE_TTL = 30

scheduler = create_scheduler()

app = FastAPI(title="EventAggregator LMS")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


import asyncio


@app.on_event("startup")
async def startup():
    logger.info("🚀 Приложение EventAggregator запущено.")

    async def _startup_sync():
        if SessionLocal is None:
            logger.warning("DATABASE_URL не задан — стартовая синхронизация пропущена")
            return
        with SessionLocal() as db:
            try:
                if await run_sync(db, source_name="startup-source"):
                    logger.info("✅ Стартовая синхронизация завершена.")
                else:
                    logger.warning("⚠️ Стартовая синхронизация частично не удалась.")
            except Exception:
                logger.exception("💥 Ошибка при стартовой синхронизации")

    # Запускаем в фоне — сервер не ждёт
    asyncio.create_task(_startup_sync())

    try:
        scheduler.start()
        logger.info("🕒 Планировщик запущен: интервал 24 часа.")
    except Exception as e:
        logger.error("Не удалось запустить планировщик: %s", e)


    # Фоновая задача: не блокируем подъём сервера
    asyncio.create_task(_startup_sync())

    try:
        scheduler.start()
        logger.info("🕒 Планировщик запущен: интервал 24 часа.")
    except Exception as e:
        logger.error("Не удалось запустить планировщик: %s", e)



# --- Health Check ---
@app.get("/api/health")
def health():
    return {"status": "ok"}


# --- Ручной запуск синхронизации ---
@app.post("/api/sync/trigger")
async def trigger_sync(db: Session = Depends(get_db)):
    try:
        success = await run_sync(db)
    except Exception:
        logger.exception("💥 Ошибка при запуске синхронизации")
        success = False
    if success:
        return {"status": "success", "message": "Синхронизация завершена"}
    return {"status": "failed", "message": "Синхронизация завершилась с ошибкой (см. логи)"}


# --- Список событий с пагинацией (контракт DRF: count/next/previous/results) ---
@app.get("/api/events")
def list_events(page: int = 1, per_page: int = 10, db: Session = Depends(get_db)):
    if page < 1:
        raise HTTPException(status_code=400, detail="page должна быть >= 1")
    if not (1 <= per_page <= 100):
        raise HTTPException(status_code=400, detail="per_page должна быть от 1 до 100")

    repo = EventRepository(db)
    total = repo.count_events()
    events = repo.get_events_page(offset=(page - 1) * per_page, limit=per_page)

    def _page_url(p: int):
        if p < 1 or (p - 1) * per_page >= total:
            return None
        return f"/api/events?{urlencode({'page': p, 'per_page': per_page})}"

    return {
        "count": total,
        "next": _page_url(page + 1),
        "previous": _page_url(page - 1),
        "results": [
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
            "seats_pattern": event.seats_pattern,  # реальное значение из синка
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


# --- Свободные места (с кэшем) ---
@app.get("/api/events/{event_id}/seats")
async def get_available_seats(event_id: UUID, db: Session = Depends(get_db)):
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
    if client is None:
        raise HTTPException(status_code=503, detail="Клиент провайдера не инициализирован: проверьте EVENTS_PROVIDER_* переменные")
    seats_data, error = await client.get_seats(event_id)



# --- Регистрация (через UseCase) ---
@app.post("/api/tickets", status_code=201)
async def register_ticket(ticket: TicketRequest, db: Session = Depends(get_db)):
    if client is None:
        raise HTTPException(
            status_code=503,
            detail="Клиент провайдера не инициализирован: проверьте EVENTS_PROVIDER_* переменные"
        )

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
            event_id=ticket.event_id,
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
    if client is None:
        raise HTTPException(
            status_code=503,
            detail="Клиент провайдера не инициализирован: проверьте EVENTS_PROVIDER_* переменные"
        )

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
