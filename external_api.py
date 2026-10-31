# external_api.py

from datetime import datetime, timedelta, timezone  # ✅ Добавил timezone
from uuid import uuid4

def fetch_events_since(last_sync_time):
    """
    Имитирует запрос к внешнему API.
    
    ВАЖНО: все даты здесь теперь с часовым поясом (UTC), чтобы не было конфликтов
    при сравнении с last_event_time из базы (где DateTime(timezone=True)).
    """

    events = []

    # Helper для создания дат в UTC — чтобы не писать tzinfo каждый раз
    def utc_dt(*args, **kwargs):
        return datetime(*args, tzinfo=timezone.utc, **kwargs)

    # Если это первый запуск (нет времени последней синхронизации) — отдаём тестовые события
    if last_sync_time is None:
        # ✅ Теперь base_time — aware (с поясом)
        base_time = utc_dt(2027, 1, 1, 12, 0)
        
        events.append({
            "id": str(uuid4()),
            "name": "Концерт: Классика в парке",
            "event_time": base_time + timedelta(days=10),
            "status": "published",
            "place_id": "p-101",
            "place_name": "Летний театр",
            "city": "Москва",
            "address": "ул. Парковая, 1",
            "registration_deadline": base_time + timedelta(days=9, hours=18),
            "number_of_visitors": 500,
            # ✅ last_changed_at тоже aware
            "last_changed_at": base_time,
        })
        events.append({
            "id": str(uuid4()),
            "name": "Фестиваль уличной еды",
            "event_time": base_time + timedelta(days=20),
            "status": "published",
            "place_id": "p-202",
            "place_name": "Городская площадь",
            "city": "Санкт-Петербург",
            "address": "пр. Невский, 10",
            "registration_deadline": base_time + timedelta(days=19, hours=12),
            "number_of_visitors": 3000,
            "last_changed_at": base_time + timedelta(hours=1),
        })
        events.append({
            "id": str(uuid4()),
            "name": "Лекция: Будущее городов",
            "event_time": base_time + timedelta(days=30),
            "status": "draft",
            "place_id": "p-303",
            "place_name": "Лекторий А",
            "city": "Казань",
            "address": "ул. Баумана, 5",
            "registration_deadline": base_time + timedelta(days=29, hours=23),
            "number_of_visitors": 150,
            "last_changed_at": base_time + timedelta(hours=2),
        })

    else:
        # Повторный запуск: отдаём только новые/изменённые события,
        # у которых last_changed_at > last_sync_time
        
        # ⚠️ Важно: last_sync_time приходит из базы — он уже aware (с поясом).
        # Поэтому new_event_time тоже должен быть aware.
        new_event_time = last_sync_time + timedelta(minutes=5)
        
        events.append({
            "id": str(uuid4()),
            "name": "Новое событие после синхронизации",
            "event_time": new_event_time + timedelta(days=1),
            "status": "published",
            "place_id": "p-999",
            "place_name": "Новая площадка",
            "city": "Екатеринбург",
            "address": "ул. Центральная, 1",
            "registration_deadline": new_event_time,
            "number_of_visitors": 700,
            # ✅ last_changed_at строго больше last_sync_time
            "last_changed_at": new_event_time,
        })

    return events
