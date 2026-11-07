import asyncio
import logging
from urllib.parse import urlencode
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from database import SessionLocal, engine, get_db
from exceptions import DomainError
from http_client import EventsApiClient
from models import Base
from repositories.event_repository import EventRepository
from repositories.registration_repository import RegistrationRepository
from scheduler import create_scheduler
from schemas import TicketRequest
from services.seats_usecase import SeatsUseCase
from services.ticket_cancellation_usecase import TicketCancellationUseCase
from services.ticket_registration_usecase import TicketRegistrationUseCase
from settings import EVENTS_PROVIDER_BASE_URL
from sync_runner import run_sync

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

# --- ГЛОБАЛЬНЫЙ КЛИЕНТ ---
# Создаём на уровне модуля, чтобы тесты могли делать patch.object(main.client, ...).
# Если env не задан — модуль не падает, иначе uvicorn не стартует и nginx отдаёт 502/503.
client: EventsApiClient | None = None
try:
    if not EVENTS_PROVIDER_BASE_URL:
        logger.error("❌ EVENTS_PROVIDER_BASE_URL не установлен в переменных окружения!")
    else:
        client = EventsApiClient(base_url=EVENTS_PROVIDER_BASE_URL)
        logger.info("✅ Глобальный клиент EventsApiClient создан")
except Exception:
    logger.exception("💥 Не удалось создать EventsApiClient — проверь env на платформе")


scheduler = create_scheduler()

app = FastAPI(title="EventAggregator LMS")


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=400,
        content={
            "detail": [
                {"loc": e.get("loc"), "msg": e.get("msg")}
                for e in exc.errors()
            ]
        },
    )
# get_db берём из database.py — там есть защита от не настроенной базы


@app.on_event("startup")
async def startup():
    logger.info("🚀 Приложение EventAggregator запущено.")

    # 1. Создаём таблицы, если их нет (страховка для платформы без миграций)
    if engine is None:
        logger.warning("База не настроена — таблицы не создаются")
    else:
        try:
            Base.metadata.create_all(bind=engine)
            logger.info("Таблицы проверены/созданы")
        except Exception as e:
            logger.error("Не удалось создать таблицы: %s", e)

    # 2. Стартовая синхронизация в фоне — сервер не ждёт
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

    asyncio.create_task(_startup_sync())

    # 3. Планировщик — ровно один раз
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


# --- Список событий с пагинацией (контракт: count/next/previous/results) ---
@app.get("/api/events")
def get_events(
    page: int = 1,
    page_size: int = 10,
    per_page: int | None = None,
    date_from: str | None = None,
    db: Session = Depends(get_db),
):
    # Тестовый контракт использует page_size, старый клиент — per_page
    size = per_page if per_page is not None else page_size
    if page < 1:
        page = 1
    if size < 1:
        size = 10

    repo = EventRepository(db)
    try:
        events, total = repo.list_events(page, size, date_from)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    def _page_url(p: int):
        if p < 1 or (p - 1) * size >= total:
            return None
        return f"/api/events?{urlencode({'page': p, 'page_size': size, **({'date_from': date_from} if date_from else {})})}"

    return {
        "count": total,
        "next": _page_url(page + 1),
        "previous": _page_url(page - 1),
        "results": [
            {
                "id": str(ev.id),
                "name": ev.name,
                "place": {
                    "id": str(ev.place_id) if ev.place_id else None,
                    "name": ev.place_name,
                    "city": ev.city,
                    "address": ev.address,
                    "seats_pattern": ev.seats_pattern,
                },
                "event_time": (
                    ev.event_time.isoformat() if ev.event_time else None
                ),
                "registration_deadline": (
                    ev.registration_deadline.isoformat()
                    if ev.registration_deadline else None
                ),
                "status": ev.status,
                "number_of_visitors": ev.number_of_visitors,
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
            "seats_pattern": event.seats_pattern,
        }

    return {
        "id": str(event.id),
        "name": event.name,
        "place": place,
        "event_time": event.event_time.isoformat() if event.event_time else None,
        "registration_deadline": (
            event.registration_deadline.isoformat()
            if event.registration_deadline else None
        ),
        "status": event.status,
        "number_of_visitors": event.number_of_visitors,
    }


# --- Свободные места (с кэшем) ---
@app.get("/api/events/{event_id}/seats")
async def get_available_seats(event_id: UUID, db: Session = Depends(get_db)):
    usecase = SeatsUseCase(
        event_repo=EventRepository(db),
        ticket_repo=RegistrationRepository(db),
        client=client,
    )
    try:
        return await usecase.do(event_id)
    except DomainError as e:
        raise HTTPException(status_code=e.status_code, detail=e.args[0])
    except Exception:
        logger.exception("💥 Неожиданная ошибка при получении мест")
        raise HTTPException(status_code=500, detail="Internal Server Error")



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
    except DomainError as e:
        raise HTTPException(status_code=e.status_code, detail=e.args[0])
    except Exception:
        logger.exception("💥 Неожиданная ошибка при регистрации")
        raise HTTPException(status_code=500, detail="Internal Server Error")





# --- Отмена регистрации (через UseCase) ---
@app.delete("/api/tickets/{ticket_id}")
async def cancel_ticket(ticket_id: str, db: Session = Depends(get_db)):
    if client is None:
        raise HTTPException(
            status_code=503,
            detail="Provider client is not initialized: check EVENTS_PROVIDER_* env variables"
        )

    event_repo = EventRepository(db)
    ticket_repo = RegistrationRepository(db)

    usecase = TicketCancellationUseCase(
        event_repo=event_repo,
        ticket_repo=ticket_repo,
        client=client,
    )

    try:
        result = await usecase.do(ticket_id=ticket_id)
        return result
    except DomainError as e:
        raise HTTPException(status_code=e.status_code, detail=e.args[0])
    except Exception:
        logger.exception("💥 Неожиданная ошибка при отмене тикета")
        raise HTTPException(status_code=500, detail="Internal Server Error")
