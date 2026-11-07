# exceptions.py
class DomainError(Exception):
    """Базовое доменное исключение с HTTP-статусом."""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


class EventNotPublishedError(DomainError):
    def __init__(self):
        super().__init__("Event is not published", status_code=400)


class EventNotFoundError(DomainError):
    def __init__(self):
        super().__init__("Event not found", status_code=404)


class TicketAlreadyCancelledError(DomainError):
    def __init__(self):
        super().__init__("Ticket already cancelled", status_code=409)


class NoAvailableSeatsError(DomainError):
    def __init__(self, message: str = "No available seats"):
        super().__init__(message, status_code=409)


class TicketNotFoundError(DomainError):
    def __init__(self):
        super().__init__("Ticket not found", status_code=404)


class ProviderError(DomainError):
    def __init__(self, message: str):
        super().__init__(message, status_code=502)
