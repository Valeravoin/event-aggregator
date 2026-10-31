from database import SessionLocal
from sync_crud import get_last_sync, update_last_sync
from datetime import datetime, timedelta, timezone

def main():
    db = SessionLocal()
    try:
        # 1. Проверка: база должна быть пустой
        first_check = get_last_sync(db)
        print("🕒 Первая проверка (база пуста):", first_check)
        if first_check is not None:
            print("⚠️ ВНИМАНИЕ: база не пустая! Удали строки из таблицы sync_metadata в pgAdmin.")
            # Можно даже сразу выйти, чтобы не путаться дальше
            return

        # 2. Готовим тестовое время: "час назад" в UTC
        test_time = datetime.now(timezone.utc) - timedelta(hours=1)

        # 3. Создаём запись
        log_entry = update_last_sync(
            db=db,
            new_time=test_time,          # это уйдёт в last_event_time
            source_name="test-api",
            events_processed=5
        )
        
        print("✅ Запись создана: source_name=", log_entry.source_name, "| events=", log_entry.events_processed)
        print("   last_event_time (то, что передали) =", log_entry.last_event_time)
        print("   last_sync_time (когда реально вставили) =", log_entry.last_sync_time)

        # 4. Получаем последнюю запись из БД
        second_check_time = get_last_sync(db)  # это вернёт last_sync_time из базы
        print("🕒 Вторая проверка (last_sync_time из БД):", second_check_time)

        # --- ПРАВИЛЬНЫЕ ПРОВЕРКИ ---
        
        # Проверка А: совпадает ли last_event_time в объекте с тем, что мы передали?
        diff_event = abs(log_entry.last_event_time - test_time).total_seconds()
        print(f"Разница между переданным test_time и last_event_time: {diff_event} сек")
        print("✅ last_event_time совпадает?", diff_event < 5)  # разница должна быть почти 0

        # Проверка Б: совпадает ли last_sync_time в БД с тем, что лежит в объекте?
        # (они должны быть почти одинаковыми, потому что это одно и то же поле)
        diff_sync = abs(second_check_time - log_entry.last_sync_time).total_seconds()
        print(f"Разница между last_sync_time из БД и объекта: {diff_sync} сек")
        print("✅ last_sync_time совпадает?", diff_sync < 5)

        # Если обе проверки True — значит, CRUD работает правильно!

    finally:
        db.close()

if __name__ == "__main__":
    main()
