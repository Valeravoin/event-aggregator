from pydantic import BaseModel


class TicketCreate(BaseModel):
    event_id: str  # UUID события как строка
    user_email: str
    seat_number: str | None = None  # если есть нумерация мест

class TicketRequest(BaseModel):
    first_name: str
    last_name: str
    email: str
    seat: str
    event_id: str