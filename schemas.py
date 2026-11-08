from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr


class TicketRequest(BaseModel):
    first_name: str
    last_name: str
    email: EmailStr
    seat: str
    event_id: UUID


class PlaceOut(BaseModel):
    id: str | None = None
    name: str | None = None
    city: str | None = None
    address: str | None = None
    seats_pattern: str | None = None


class EventOut(BaseModel):
    id: str
    name: str | None = None
    place: PlaceOut | None = None
    event_time: datetime | None = None
    registration_deadline: datetime | None = None
    status: str | None = None
    number_of_visitors: int | None = None


class EventsPage(BaseModel):
    count: int
    next: str | None = None
    previous: str | None = None
    results: list[EventOut]
