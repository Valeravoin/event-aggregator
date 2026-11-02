from fastapi import FastAPI, Depends, HTTPException, status
from sqlalchemy import select, text, func
from sqlalchemy.exc import SQLAlchemyError
from typing import Optional, List, Dict, Any
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import logging
import uuid

# --- Импорты проекта ---
from database import SessionLocal, engine
from models import Base, Event, Registration, SyncMetadata
from sync_runner import run_sync
from scheduler import create_scheduler
from http_client import EventsApiClient # нужен для вызовов к провайдеру
from settings import EVENTS_PROVIDER_BASE_URL
import time
from schemas import TicketRequest 



_seats_cache = {}  # {event_id: (timestamp, data)}
CACHE_TTL = 30      # секунд

client = EventsApiClient(base_url=EVENTS_PROVIDER_BASE_URL)

# ЭТА СТРОКА СОЗДАСТ ТАБЛИЦЫ, ЕСЛИ ИХ НЕТ (MVP подход)
Base.metadata.create_all(bind=engine)

# Настройка логов
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)


# Инициализация планировщика (один раз при старте процесса)
scheduler = create_scheduler()
scheduler.start()
logger.info("🔧 Планировщик запущен. Следующая синхронизация через 24 часа (или по расписанию).")

app = FastAPI(title="EventAggregator LMS")

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
def trigger_sync(db: Session = Depends(get_db)):
    success = run_sync(db)
    if success:
        return {"status": "success", "message": "Синхронизация завершена"}
    else:
        return {"status": "failed", "message": "Синхронизация завершилась с ошибкой (см. логи)"}

# --- Детали события (GET /api/events/{event_id}) ---
@app.get("/api/events/{event_id}")
def get_event_details(event_id: str, db: Session = Depends(get_db)):
    stmt = select(Event).where(Event.id == event_id)
    result = db.execute(stmt)
    event = result.scalars().first()

    if not event:
        raise HTTPException(status_code=404, detail="Событие не найдено")

    place = None
    if event.place_id:
        place = {
            "id": str(event.place_id),
            "name": event.place_name,
            "city": event.city,
            "address": event.address,
            "seats_pattern": "A1-1000,B1-2000",  # заглушка по ТЗ
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

# --- Свободные места (GET /api/events/{event_id}/seats) ---
@app.get("/api/events/{event_id}/seats")
def get_available_seats(event_id: str, db: Session = Depends(get_db)):
    now = time.time()
    
    # Проверка кэша
    if event_id in _seats_cache:
        ts, cached_data = _seats_cache[event_id]
        if now - ts < CACHE_TTL:
            logger.info(f"💾 Возвращаем данные из кэша для события {event_id}")
            return cached_data

    # Дальше твой существующий код проверки события и статуса...
    stmt = select(Event).where(Event.id == event_id)
    event = db.execute(stmt).scalars().first()
    if not event:
        raise HTTPException(status_code=404, detail="Событие не найдено в агрегаторе")
    if event.status != "published":
        raise HTTPException(
            status_code=403, 
            detail="Регистрация возможна только для опубликованных событий. Статус: " + event.status
        )

    logger.info(f"🌐 Запрос свободных мест у Events Provider для {event_id}")
    seats_data, error = client.get_seats(event_id)

    if error:
        logger.warning(f"Ошибка интеграции с провайдером: {error}")
        raise HTTPException(status_code=502, detail=f"Не удалось получить места от провайдера: {error}")

    response_payload = {
        "event_id": event_id,
        "available_seats": seats_data.get("available_seats", []),
        "source": "external-provider",
        "cached": False
    }

    # Сохраняем в кэш
    _seats_cache[event_id] = (now, response_payload)
    return response_payload


# --- Регистрация (POST /api/tickets) ---
@app.post("/api/tickets", status_code=201)
def register_ticket(
    ticket: TicketRequest,          # <-- ГЛАВНОЕ ИЗМЕНЕНИЕ: принимаем JSON-объект целиком
    db: Session = Depends(get_db)
):
    # 1. Проверка существования события
    event_stmt = select(Event).where(Event.id == ticket.event_id)
    event = db.execute(event_stmt).scalars().first()
    
    if not event:
        raise HTTPException(status_code=404, detail="Событие не найдено")
    
    # 2. Проверка статуса (только published)
    if event.status != "published":
        raise HTTPException(
            status_code=403, 
            detail=f"Нельзя регистрироваться на неопубликованное событие. Статус: {event.status}"
        )
    
    # 3. Проверка дедлайна регистрации
    if event.registration_deadline:
        now_utc = datetime.now(timezone.utc)
        if now_utc > event.registration_deadline:
            raise HTTPException(status_code=403, detail="Срок регистрации истек")

    logger.info(f"🎫 Попытка регистрации места {ticket.seat} для события {ticket.event_id}...")

    # 4. Вызов внешнего провайдера через твой HTTP-клиент
    result, error = client.register_ticket(
        event_id=ticket.event_id, 
        seat=ticket.seat, 
        email=ticket.email,
        first_name=ticket.first_name,
        last_name=ticket.last_name
    )

    # 5. Обработка ошибок от провайдера
    if error:
        # Если место занято или уже зарегистрировано — 409 Conflict, иначе 400
        status_code = 409 if ("already" in error.lower() or "taken" in error.lower()) else 400
        raise HTTPException(status_code=status_code, detail=error)

    # Генерируем ticket_id, если провайдер его не вернул
    ticket_id = result.get("ticket_id") or uuid.uuid4()

    # 6. Сохраняем регистрацию в свою БД
    new_reg = Registration(
        ticket_id=ticket_id,
        event_id=event.id,
        email=ticket.email,
        first_name=ticket.first_name,
        last_name=ticket.last_name,
        seat=ticket.seat,
        status="active"
    )
    
    db.add(new_reg)
    try:
        db.commit()
        db.refresh(new_reg)
    except Exception as e:
        db.rollback()
        logger.error(f"Ошибка сохранения регистрации в БД: {e}")
        raise HTTPException(status_code=500, detail="Не удалось сохранить регистрацию в базе данных")

    logger.info(f"✅ Регистрация успешно сохранена в БД: {ticket_id}")
    
    return {
        "ticket_id": str(ticket_id),
        "status": "registered",
        "message": "Регистрация успешна",
        "seat": ticket.seat
    }

# --- Отмена регистрации (DELETE /api/tickets/{ticket_id}) ---
@app.delete("/api/tickets/{ticket_id}")
def cancel_ticket(ticket_id: str, db: Session = Depends(get_db)):
    stmt = select(Registration).where(Registration.ticket_id == ticket_id)
    reg = db.execute(stmt).scalars().first()
    
    if not reg:
        raise HTTPException(status_code=404, detail="Билет не найден")
    
    if reg.status == "cancelled":
        return {"success": True, "message": "Билет уже отменен"}
    
    event_stmt = select(Event).where(Event.id == reg.event_id)
    event = db.execute(event_stmt).scalars().first()
    if not event:
         raise HTTPException(status_code=404, detail="Связанное событие не найдено в БД")

    logger.info(f"🔄 Отмена билета {ticket_id} у провайдера...")
    _, error = client.unregister_ticket(event_id=reg.event_id, ticket_id=ticket_id)

    if error:
        logger.warning(f"Провайдер вернул ошибку при отмене: {error}")
        raise HTTPException(status_code=502, detail=f"Не удалось отменить регистрацию у провайдера: {error}")

    reg.status = "cancelled"
    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Ошибка обновления статуса в БД: {e}")
        raise HTTPException(status_code=500, detail="Не удалось обновить статус в базе данных")
    
    return {
        "success": True, 
        "ticket_id": ticket_id, 
        "message": "Отмена успешна"
    }

# --- Список событий (с пагинацией и фильтрацией) ---
@app.get("/api/events")
def get_events(
    page: int = 1,
    page_size: int = 20,
    date_from: Optional[str] = None,
    db: Session = Depends(get_db),
):
    if page < 1:
        page = 1
    if page_size < 1 or page_size > 100:
        page_size = 20

    offset = (page - 1) * page_size

    count_stmt = select(func.count()).select_from(Event)
    dt = None
    
    if date_from:
        try:
            dt = datetime.strptime(date_from, "%Y-%m-%d")
            dt = dt.replace(tzinfo=timezone.utc)
            count_stmt = count_stmt.where(Event.event_time >= dt)
        except ValueError:
            raise HTTPException(status_code=400, detail="Неверный формат date_from. Используйте YYYY-MM-DD")

    total = db.execute(count_stmt).scalar() or 0

    stmt = select(Event).order_by(Event.event_time.desc())
    if dt:
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
            "registration_deadline": ev.registration_deadline.isoformat() if ev.registration_deadline else None,
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

@app.get("/debug/stats")
def get_stats(db: Session = Depends(get_db)):
    total_events_stmt = select(func.count()).select_from(Event)
    total_sync_stmt = select(func.count()).select_from(SyncMetadata)
    
    total_events = db.execute(total_events_stmt).scalar() or 0
    total_sync = db.execute(total_sync_stmt).scalar() or 0
    
    return {
        "total_events": total_events,
        "total_sync_records": total_sync,
        "message": "Данные синхронизированы успешно!"
    }
