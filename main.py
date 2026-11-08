import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import date
from urllib.parse import urlencode
from uuid import UUID

from alembic.config import Config
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.ext.asyncio import AsyncSession

from alembic import command
from database import SessionLocal, engine, get_db
from exceptions import (
    DomainError,
    EventNotFoundError,
    EventNotPublishedError,
    InternalConsistencyError,
    NoAvailableSeatsError,
    ProviderError,
    ProviderUnavailableError,
    TicketNotFoundError,
)
from http_client import EventsApiClient
from repositories.event_repository import EventRepository
from repositories.registration_repository import RegistrationRepository
from scheduler import create_scheduler
from schemas import EventOut, EventsPage, PlaceOut, TicketRequest
from services.seats_usecase import SeatsUseCase, seats_cache
from services.ticket_cancellation_usecase import TicketCancellationUseCase
from services.ticket_registration_usecase import TicketRegistrationUseCase
from settings import DISABLE_STARTUP_SYNC, EVENTS_PROVIDER_BASE_URL
from sync_runner import run_sync

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

# Сопоставление доменных исключений с HTTP-кодами — только здесь, в presentation
DOMAIN_TO_HTTP: dict[type[DomainError], int] = {
    EventNotFoundError: 404,
    TicketNotFoundError: 404,
    EventNotPublishedError: 403,
    NoAvailableSeatsError: 409,
    ProviderError: 502,
    ProviderUnavailableError: 503,
    InternalConsistencyError: 500,
}

def _raise_domain_error(exc: DomainError):
    status = DOMAIN_TO_HTTP.get(type(exc), 400)
    raise HTTPException(status_code=status, detail=str(exc))

# --- Миграции Alembic вместо create_all ---
# Схема БД управляется только миграциями. Если таблицы уже созданы
# (первый деплой после перехода с create_all, или тесты на SQLite) —
# помечаем head-миграцию как применённую, иначе применяем миграции.


def _tables_already_exist(conn) -> bool:
    insp = sa_inspect(conn)
    return insp.has_table("events") and insp.has_table("registrations")


async def _apply_migrations() -> None:
    if engine is None:
        logger.warning("База не настроена — миграции не применяются")
        return

    alembic_cfg = Config("alembic.ini")

    async with engine.connect() as conn:
        already_created = await conn.run_sync(_tables_already_exist)

    if already_created:
        logger.info("🧷 Схема уже существует — помечаю head-миграцию как применённую")
        try:
            await asyncio.to_thread(command.stamp, alembic_cfg, "head")
        except Exception:
            # stamp не критичен: схема и так консистентна с моделями
            logger.exception("Не удалось проставить alembic stamp — продолжаем")
    else:
        logger.info("🛠 Применяю миграции Alembic")
        # to_thread: env.py внутри делает asyncio.run — в рабочем потоке нет
        # запущенного цикла, конфликтов с event loop FastAPI не будет
        await asyncio.to_thread(command.upgrade, alembic_cfg, "head")



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

scheduler = create_scheduler(client)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 Приложение EventAggregator запущено.")

    # 1. Создаём таблицы, если их нет (страховка для платформы без миграций)
        # 1. Создаём таблицы, если их нет (страховка для платформы без миграций)
    if engine is None:
        logger.warning("База не настроена — таблицы не создаются")
    else:
            # 1. Схема БД через Alembic (stamp для существующей, upgrade для чистой)
        try:
            await _apply_migrations()
            logger.info("✅ Схема БД в актуальном состоянии (Alembic)")
        except Exception:
            logger.exception("Не удалось применить миграции")
            raise





        # 2. Стартовая синхронизация в фоне — сервер не ждёт

    async def _startup_sync():
        if SessionLocal is None:
            logger.warning("DATABASE_URL не задан — стартовая синхронизация пропущена")
            return
        async with SessionLocal() as db:
            try:
                if await run_sync(db, client=client):
                    logger.info("✅ Стартовая синхронизация завершена.")

                else:
                    logger.warning("⚠️ Стартовая синхронизация частично не удалась.")
            except Exception:
                logger.exception("💥 Ошибка при стартовой синхронизации")

    if DISABLE_STARTUP_SYNC:
        logger.info("⏭️ Стартовая синхронизация отключена (DISABLE_STARTUP_SYNC)")
    else:
        asyncio.create_task(_startup_sync())

    # 3. Планировщик — ровно один раз
    try:
        scheduler.start()
        logger.info("🕒 Планировщик запущен: интервал 24 часа.")
    except Exception as e:
        logger.error("Не удалось запустить планировщик: %s", e)

    yield

    # --- Shutdown ---
    try:
        scheduler.shutdown(wait=False)
    except Exception:
        logger.exception("Ошибка при остановке планировщика")
    if client is not None:
        try:
            await client.close()
            logger.info("✅ HTTP-клиент провайдера закрыт")
        except Exception:
            logger.exception("Ошибка при закрытии HTTP-клиента")

    if engine is not None:
        await engine.dispose()


app = FastAPI(title="EventAggregator LMS", lifespan=lifespan)


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=400,
        content={"detail": [{"loc": e.get("loc"), "msg": e.get("msg")} for e in exc.errors()]},
    )


# --- Health Check ---
@app.get("/api/health")
async def health():
    return {"status": "ok"}


# --- Ручной запуск синхронизации ---
@app.post("/api/sync/trigger")
async def trigger_sync(db: AsyncSession = Depends(get_db)):
    try:
        success = await run_sync(db, client=client)
    except Exception:
        logger.exception("💥 Ошибка при запуске синхронизации")
        success = False
    if success:
        return {"status": "success", "message": "Синхронизация завершена"}
    return {"status": "failed", "message": "Синхронизация завершилась с ошибкой (см. логи)"}


@app.get("/api/events", response_model=EventsPage)
async def get_events(
    page: int = 1,
    page_size: int = 10,
    per_page: int | None = None,
    date_from: date | None = None,
    db: AsyncSession = Depends(get_db),
):
    # Тестовый контракт использует page_size, старый клиент — per_page
    size = per_page if per_page is not None else page_size
    if page < 1:
        page = 1
    if size < 1:
        size = 10
    size = min(size, 100)  # тот же лимит, что и в репозитории — ссылки не врут

    repo = EventRepository(db)
    events, total = await repo.list_events(page, size, date_from)

    def _page_url(p: int) -> str | None:
        if p < 1 or (p - 1) * size >= total:
            return None
        query = {"page": p, "page_size": size}
        if date_from:
            query["date_from"] = date_from.isoformat()
        return f"/api/events?{urlencode(query)}"

    return EventsPage(
        count=total,
        next=_page_url(page + 1),
        previous=_page_url(page - 1),
        results=[
            EventOut(
                id=str(ev.id),
                name=ev.name,
                place=PlaceOut(
                    id=str(ev.place_id) if ev.place_id else None,
                    name=ev.place_name,
                    city=ev.city,
                    address=ev.address,
                    seats_pattern=ev.seats_pattern,
                ) if ev.place_id else None,
                event_time=ev.event_time,
                registration_deadline=ev.registration_deadline,
                status=ev.status,
                number_of_visitors=ev.number_of_visitors,
            )
            for ev in events
        ],
    )



# --- Детали события ---
@app.get("/api/events/{event_id}", response_model=EventOut)
async def get_event_details(event_id: UUID, db: AsyncSession = Depends(get_db)):
    repo = EventRepository(db)
    event = await repo.get_by_id(event_id)

    if not event:
        raise HTTPException(status_code=404, detail="Событие не найдено")

    return EventOut(
        id=str(event.id),
        name=event.name,
        place=PlaceOut(
            id=str(event.place_id),
            name=event.place_name,
            city=event.city,
            address=event.address,
            seats_pattern=event.seats_pattern,
        ) if event.place_id else None,
        event_time=event.event_time,
        registration_deadline=event.registration_deadline,
        status=event.status,
        number_of_visitors=event.number_of_visitors,
    )



# --- Свободные места (с кэшем) ---
@app.get("/api/events/{event_id}/seats")
async def get_available_seats(event_id: UUID, db: AsyncSession = Depends(get_db)):
    usecase = SeatsUseCase(
        event_repo=EventRepository(db),
        ticket_repo=RegistrationRepository(db),
        client=client,
    )
    try:
        return await usecase.do(event_id)
    except DomainError as e:
        _raise_domain_error(e)

    except Exception:
        logger.exception("💥 Неожиданная ошибка при получении мест")
        raise HTTPException(status_code=500, detail="Internal Server Error")


# --- Регистрация (через UseCase) ---
@app.post("/api/tickets", status_code=201)
async def register_ticket(ticket: TicketRequest, db: AsyncSession = Depends(get_db)):
    if client is None:
        raise HTTPException(
            status_code=503,
            detail="Клиент провайдера не инициализирован: проверьте EVENTS_PROVIDER_* переменные",
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
        seats_cache.pop(str(result["event_id"]), None)
        return result

    except DomainError as e:
        _raise_domain_error(e)
    except Exception:
        logger.exception("💥 Неожиданная ошибка при регистрации")
        raise HTTPException(status_code=500, detail="Internal Server Error")


# --- Отмена регистрации (через UseCase) ---
@app.delete("/api/tickets/{ticket_id}")
async def cancel_ticket(ticket_id: UUID, db: AsyncSession = Depends(get_db)):
    if client is None:
        raise HTTPException(
            status_code=503,
            detail="Provider client is not initialized: check EVENTS_PROVIDER_* env variables",
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
        seats_cache.pop(str(result["event_id"]), None)
        return result
    except DomainError as e:
        _raise_domain_error(e)
    except Exception:
        logger.exception("💥 Неожиданная ошибка при отмене тикета")
        raise HTTPException(status_code=500, detail="Internal Server Error")
