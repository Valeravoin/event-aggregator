from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import SyncMetadata, SyncStatus

# Если 'running' висит дольше — прошлый запуск умер, перехватываем управление
STALE_RUNNING_TIMEOUT = timedelta(minutes=10)


class SyncRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_or_create(self, source_name: str) -> SyncMetadata:
        stmt = select(SyncMetadata).where(SyncMetadata.source_name == source_name)
        record = (await self.db.execute(stmt)).scalars().first()
        if record is None:
            record = SyncMetadata(
                source_name=source_name,
                sync_status=SyncStatus.IDLE.value,
                events_processed=0,
                last_event_time=None,
                last_sync_time=None,
            )
            self.db.add(record)
            await self.db.commit()
            await self.db.refresh(record)
        return record

    async def try_acquire(
        self, record: SyncMetadata, skip_locked: bool
    ) -> SyncMetadata | None:
        """Захватывает право на синк. Возвращает обновлённую запись или None,
        если синк уже выполняется (в т.ч. держится другой репликой)."""
        if skip_locked:
            # Postgres: блокируем строку метаданных. Второй воркер не ждёт,
            # а получает None — гонок нет. Заодно перекрывает случай, когда
            # другой экземпляр сервиса сейчас держит транзакцию.
            stmt = (
                select(SyncMetadata)
                .where(SyncMetadata.source_name == record.source_name)
                .with_for_update(skip_locked=True)
            )
            acquired = (await self.db.execute(stmt)).scalars().first()
            if acquired is None:
                return None
            record = acquired
        else:
            # SQLite (тесты) не умеет FOR UPDATE — защита по статусу
            if record.sync_status == SyncStatus.RUNNING.value:
                return None

        # Восстановление после залипшего 'running': если статус висит дольше
        # STALE_RUNNING_TIMEOUT, прошлый запуск умер — перехватываем управление
        if record.sync_status == SyncStatus.RUNNING.value:
            last = record.last_sync_time
            if last is not None and (datetime.now(UTC) - last) <= STALE_RUNNING_TIMEOUT:
                return None
            record.sync_status = SyncStatus.FAILED.value
            await self.db.commit()

        record.sync_status = SyncStatus.RUNNING.value
        record.last_sync_time = datetime.now(UTC)
        await self.db.commit()
        return record

    async def mark_done(
        self,
        record: SyncMetadata,
        created: int,
        updated: int,
        max_changed_at: datetime | None,
    ) -> None:
        record.events_processed = (record.events_processed or 0) + created + updated
        record.last_sync_time = datetime.now(UTC)
        if max_changed_at:
            record.last_event_time = max_changed_at
        record.sync_status = SyncStatus.IDLE.value
        await self.db.commit()

    async def mark_failed(self, record: SyncMetadata) -> None:
        record.sync_status = SyncStatus.FAILED.value
        record.last_sync_time = datetime.now(UTC)
        await self.db.commit()
