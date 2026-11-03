import asyncio
import logging

logging.basicConfig(level=logging.INFO)

from sqlalchemy import func, select

from database import SessionLocal
from models import Event
from sync_runner import run_sync


async def main():
    with SessionLocal() as db:
        ok = await run_sync(db)
        print("SYNC RESULT:", ok)
    with SessionLocal() as db2:
        total = db2.execute(select(func.count()).select_from(Event)).scalar()
        print("EVENTS IN DB:", total)


asyncio.run(main())
