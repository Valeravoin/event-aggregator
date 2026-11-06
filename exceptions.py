# exceptions.py
class DomainError(Exception):
    """Базовое доменное исключение с HTTP-статусом."""
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


class EventNotPublishedError(DomainError):
    def __init__(self):
        super().__init__("Событие не опубликовано", status_code=400)


class TicketAlreadyCancelledError(DomainError):
    def __init__(self):
        super().__init__("Билет уже отменён", status_code=409)


class NoAvailableSeatsError(DomainError):
    def __init__(self):
        super().__init__("Нет свободных мест", status_code=409)

class TicketNotFoundError(DomainError):
    def __init__(self):
        super().__init__("Билет не найден", status_code=404)


class ProviderError(DomainError):
    def __init__(self, message: str):
        super().__init__(message, status_code=502)
