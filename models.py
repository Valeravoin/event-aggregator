from enum import Enum

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class EventStatus(str, Enum):
    PUBLISHED = "published"
    REGISTRATION_CLOSED = "registration_closed"
    FINISHED = "finished"
    CANCELLED = "cancelled"



class TicketStatus(str, Enum):
    """Статусы регистрации (билета)."""

    ACTIVE = "active"
    CANCELLED = "cancelled"


class SyncStatus(str, Enum):
    """Статусы синхронизации с провайдером."""

    IDLE = "idle"


class SyncMetadata(Base):
    __tablename__ = "sync_metadata"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_name = Column(String, nullable=False, unique=True)

    # Время последней синхронизации
    last_sync_time = Column(DateTime(timezone=True), nullable=True)

    # func.now() — время ставится в момент INSERT/UPDATE на стороне БД
    last_changed_at = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())

    sync_status = Column(String, default=SyncStatus.IDLE.value, nullable=False)
    events_processed = Column(Integer, default=0, nullable=False)
    # Храним максимум changed_at провайдера — база для инкрементального синка
    last_event_time = Column(DateTime(timezone=True), nullable=True)


class Event(Base):
    __tablename__ = "events"

    id = Column(UUID(as_uuid=True), primary_key=True)
    name = Column(String, nullable=False)
    # place_id храним как строку — провайдер присылает UUID строкой
    place_id = Column(String)
    place_name = Column(String)
    city = Column(String)
    address = Column(String)
    # Схема мест провайдера, формат "A1-1000,B1-2000" — нужна для теста event detail
    seats_pattern = Column(String)
    event_time = Column(DateTime(timezone=True))
    registration_deadline = Column(DateTime(timezone=True))
    status = Column(String, default=EventStatus.PUBLISHED.value)
    number_of_visitors = Column(Integer, default=0)
    last_changed_at = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())

    # Связь "один ко многим" — у события может быть много регистраций
    registrations = relationship(
        "Registration",
        back_populates="event",
        cascade="all, delete-orphan",
    )


class Registration(Base):
    __tablename__ = "registrations"

    ticket_id = Column(UUID(as_uuid=True), primary_key=True)

    # Внешний ID билета, который вернул провайдер
    external_ticket_id = Column(String, nullable=True)

    # Жесткая связь с таблицей events
    event_id = Column(
        UUID(as_uuid=True),
        ForeignKey("events.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    email = Column(String)
    first_name = Column(String)
    last_name = Column(String)
    seat = Column(String)
    status = Column(String, default=TicketStatus.ACTIVE.value, nullable=False)
    created_at = Column(DateTime(timezone=True), default=func.now())

    # Обратная связь к событию
    event = relationship("Event", back_populates="registrations")
