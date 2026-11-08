from uuid import UUID

from pydantic import BaseModel, EmailStr


class TicketRequest(BaseModel):
    first_name: str
    last_name: str
    email: EmailStr
    seat: str
    event_id: UUID
