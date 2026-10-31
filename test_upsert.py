from database import SessionLocal
# Подключаем фабрику сессий: это инструмент, чтобы открыть «окошко» к базе данных

from models import Event
# Нужен, чтобы код понимал, что такое Event (какие у него поля, как он связан с таблицей)

from crud import upsert_event, get_event_by_id
# Импортируем наши рабочие функции: upsert — это «создай или обнови», get_event_by_id — «найди по ID»

from datetime import datetime, timedelta, timezone
# datetime — чтобы задавать конкретные даты; 
# timedelta — чтобы прибавлять часы/дни к дате (например, +1 час); 
# timezone — чтобы ставить часовой пояс (обязательно для PostgreSQL)

from uuid import uuid4
# uuid4 генерирует случайный уникальный ID (вроде «550e8400-e29b…») — чтобы не было дублей


def main():
    # Создаём новую сессию — открываем соединение с базой специально для этого теста
    db = SessionLocal()
    try:
        # Генерируем уникальный ID для тестового события. 
        # Так мы точно знаем, что работаем с «чистой» записью, а не ломаем старые данные
        test_id = uuid4()

        # 1. Создаём событие через upsert
        # first_time — фиксированное время с часовым поясом UTC. 
        # tzinfo=timezone.utc обязателен: в базе даты с поясом, сравнивать без пояса нельзя
        first_time = datetime(2027, 1, 1, 12, 0, tzinfo=timezone.utc)
        
        ev1 = upsert_event(
            db=db,
            event_data={
                "id": test_id,
                "name": "Концерт (версия 1)",
                # Все даты передаём с tzinfo=timezone.utc — это защита от ошибки TypeError
                "event_time": datetime(2027, 5, 10, 19, 0, tzinfo=timezone.utc),
                "status": "published",
                "place_id": "p1",
                "place_name": "Зал А",
                "city": "Москва",
                "address": "ул. Пушкина",
                "registration_deadline": datetime(2027, 5, 9, 21, 0, tzinfo=timezone.utc),
                "number_of_visitors": 1000,
                "last_changed_at": first_time,  # время, по которому upsert решает: обновлять или нет
            },
        )
        # Выводим результат: если всё ок, увидим имя и время last_changed_at
        print("✅ Первая вставка:", ev1.name, "| last_changed_at:", ev1.last_changed_at)

        # 2. Пытаемся вставить то же самое с тем же временем — должно ничего не делать
        ev2 = upsert_event(
            db=db,
            event_data={
                "id": test_id,
                # Имя другое, но last_changed_at тот же — значит, upsert не должен перезаписывать
                "name": "Концерт (версия 1 — повтор)",
                "event_time": datetime(2027, 5, 10, 19, 0, tzinfo=timezone.utc),
                "status": "published",
                "place_id": "p1",
                "place_name": "Зал А",
                "city": "Москва",
                "address": "ул. Пушкина",
                "registration_deadline": datetime(2027, 5, 9, 21, 0, tzinfo=timezone.utc),
                "number_of_visitors": 1000,
                "last_changed_at": first_time,  # то же время — значит, обновлять не надо
            },
        )
        # Проверяем: если upsert сработал правильно, имя осталось старым (не поменялось на «повтор»)
        print("✅ Повтор с тем же last_changed_at: имя осталось старым?", ev2.name == "Концерт (версия 1)")

        # 3. Обновляем: новое время — должно обновить
        # new_time = first_time + 1 час. Теперь оно «новее», значит, upsert должен сделать UPDATE
        new_time = first_time + timedelta(hours=1)
        ev3 = upsert_event(
            db=db,
            event_data={
                "id": test_id,
                "name": "Концерт (версия 2 — обновлено)",
                "event_time": datetime(2027, 5, 10, 19, 0, tzinfo=timezone.utc),
                "status": "published",
                "place_id": "p1",
                "place_name": "Зал А",
                "city": "Москва",
                "address": "ул. Пушкина",
                "registration_deadline": datetime(2027, 5, 9, 21, 0, tzinfo=timezone.utc),
                "number_of_visitors": 1200,  # даже число посетителей меняем, чтобы видеть обновление
                "last_changed_at": new_time,   # время новее — это сигнал для upsert: «надо обновить»
            },
        )
        # Выводим, что получилось: имя должно быть новым, посетителей — 1200
        print("✅ Обновление по новому last_changed_at:", ev3.name, "| visitors:", ev3.number_of_visitors)

    finally:
        # Блок finally выполняется всегда: и если всё прошло хорошо, и если случилась ошибка.
        # Это страховка: сессия точно закроется, и база не останется «зависшей»
        db.close()


if __name__ == "__main__":
    # Эта строчка говорит: «запусти функцию main(), только если ты запустил этот файл напрямую».
    # Если кто-то импортирует этот файл в другой скрипт, main() не запустится автоматически
    main()
