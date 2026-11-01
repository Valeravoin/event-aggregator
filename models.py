from sqlalchemy import Column, Integer, String, DateTime, func, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import declarative_base, relationship
from datetime import datetime

Base = declarative_base()

class SyncMetadata(Base):
    __tablename__ = 'sync_metadata'

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_name = Column(String, nullable=False, unique=True)
    
    # Время последней синхронизации
    last_sync_time = Column(DateTime(timezone=True), nullable=True)
    
    # ИСПРАВЛЕНИЕ: используем func.now() вместо datetime.utcnow(), чтобы время ставилось в момент INSERT
    last_changed_at = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())
    
    sync_status = Column(String, default='idle')
    events_processed = Column(Integer, default=0)
    last_event_time = Column(DateTime(timezone=True), nullable=True)


class Event(Base):
    __tablename__ = 'events'

    id = Column(UUID(as_uuid=True), primary_key=True)
    name = Column(String)
    place_id = Column(String)          # Храним как строку, если провайдер присылает UUID строкой
    place_name = Column(String)
    city = Column(String)
    address = Column(String)
    event_time = Column(DateTime(timezone=True))
    registration_deadline = Column(DateTime(timezone=True))
    status = Column(String)
    number_of_visitors = Column(Integer)
    last_changed_at = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())

    # ДОБАВЛЕНО: Связь "один ко многим" — у события может быть много регистраций
    registrations = relationship("Registration", back_populates="event", cascade="all, delete-orphan")


class Registration(Base):
    __tablename__ = 'registrations'

    ticket_id = Column(UUID(as_uuid=True), primary_key=True)
    
    # ДОБАВЛЕНО: ForeignKey для жесткой связи с таблицей events
    event_id = Column(UUID(as_uuid=True), ForeignKey('events.id', ondelete='CASCADE'), index=True)
    
    email = Column(String)
    first_name = Column(String)
    last_name = Column(String)
    seat = Column(String)
    status = Column(String, default='active')
    created_at = Column(DateTime(timezone=True), default=func.now())

    # ДОБАВЛЕНО: Обратная связь к событию
    event = relationship("Event", back_populates="registrations")
