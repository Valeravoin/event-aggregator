# models.py
from sqlalchemy import Column, Integer, String, DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import declarative_base, relationship
from datetime import datetime

Base = declarative_base()

class SyncMetadata(Base):
    __tablename__ = 'sync_metadata'

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_name = Column(String, nullable=False, unique=True)  # ключевой источник, всегда должен быть
    last_sync_time = Column(DateTime(timezone=True), nullable=True)
    last_changed_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    sync_status = Column(String, default='idle')
    events_processed = Column(Integer, default=0)
    last_event_time = Column(DateTime(timezone=True), nullable=True)


class Event(Base):
    __tablename__ = 'events'

    id = Column(UUID(as_uuid=True), primary_key=True)
    name = Column(String)
    place_id = Column(String)
    place_name = Column(String)
    city = Column(String)
    address = Column(String)
    event_time = Column(DateTime(timezone=True))
    registration_deadline = Column(DateTime(timezone=True))
    status = Column(String)
    number_of_visitors = Column(Integer)
    last_changed_at = Column(DateTime(timezone=True))


class Registration(Base):
    __tablename__ = 'registrations'

    ticket_id = Column(UUID(as_uuid=True), primary_key=True)
    event_id = Column(UUID(as_uuid=True), index=True)
    email = Column(String)
    first_name = Column(String)
    last_name = Column(String)
    seat = Column(String)
    status = Column(String, default='active')
    created_at = Column(DateTime(timezone=True), default=func.now())
