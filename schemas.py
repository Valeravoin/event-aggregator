from uuid import UUID

from pydantic import BaseModel


class TicketCreate(BaseModel):
    event_id: str
    user_email: str
    seat_number: str | None = None

class TicketRequest(BaseModel):
    first_name: str
    last_name: str
    email: str
    seat: str
    event_id: UUID
