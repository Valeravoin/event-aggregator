# sync_runner.py
from database import SessionLocal
from crud import upsert_event
from sync_crud import get_last_sync, update_last_sync
from http_client import EventsApiClient
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)

def run_sync(source_name: str = "real-api"):
    db = SessionLocal()
    try:
        # 1. Получаем время последней синхронизации
        last_time = get_last_sync(db, source_name=source_name)
        logger.info("Последняя синхронизация: %s", last_time)

        # 2. Инициализируем клиент и запрашиваем события
        with EventsApiClient(
            base_url="https://api.example.com",
            api_key=None,
        ) as client:
            new_events = client.fetch_events_since(last_time)
            logger.info("Получено новых событий: %d", len(new_events))

        # 3. Обрабатываем каждое событие
        processed_count = 0
        error_count = 0

        for ev in new_events:
            try:
                upsert_event(db, ev)
                processed_count += 1
                logger.debug("Обработано: %s (id=%s)", ev.get("name"), ev.get("id"))
            except Exception as e:
                error_count += 1
                # ВАЖНО: откатываем только эту конкретную вставку, чтобы не ломать весь скрипт
                db.rollback() 
                logger.error("Ошибка при обработке события %s: %s", ev.get("id", "unknown"), e)

        logger.info("Итого: успешно=%d, ошибок=%d", processed_count, error_count)

        # 4. Обновляем метаданные синхронизации
        if processed_count > 0 or error_count > 0:
            valid_events = [ev for ev in new_events if ev.get("last_changed_at")]
            if valid_events:
                latest_event_time = max(ev["last_changed_at"] for ev in valid_events)
            else:
                latest_event_time = datetime.now(timezone.utc)

            sync_status = "success" if error_count == 0 else "partial"

            # Перед обновлением метаданных тоже делаем rollback, если были ошибки, 
            # чтобы начать чистую транзакцию для update_last_sync
            db.rollback()

            update_last_sync(
                db=db,
                new_time=latest_event_time,
                source_name=source_name,
                events_processed=processed_count,
                sync_status=sync_status,
            )
            logger.info("Курсор и счётчик обновлены: status=%s, processed=%d", sync_status, processed_count)
        else:
            logger.info("Новых событий нет — курсор не обновляем")

        return {
            "source": source_name,
            "processed": processed_count,
            "errors": error_count,
            "status": "success" if error_count == 0 and processed_count > 0 else ("success" if processed_count == 0 and error_count == 0 else "partial"),
        }

    except Exception as e:
        logger.exception("Критическая ошибка синхронизации: %s", e)
        db.rollback()  # Гарантированный откат при любой критической ошибке
        raise
    finally:
        db.close()
