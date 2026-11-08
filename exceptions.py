class DomainError(Exception):
    """Базовое доменное исключение. HTTP-код назначает presentation-слой."""


class EventNotFoundError(DomainError):
    def __init__(self):
        super().__init__("Event not found")


class EventNotPublishedError(DomainError):
    def __init__(self):
        super().__init__("Event is not published")


class NoAvailableSeatsError(DomainError):
    def __init__(self, message: str = "No available seats"):
        super().__init__(message)


class TicketNotFoundError(DomainError):
    def __init__(self):
        super().__init__("Ticket not found")


class ProviderError(DomainError):
    def __init__(self, message: str):
        super().__init__(message)


class ProviderUnavailableError(DomainError):
    def __init__(self):
        super().__init__(
            "Provider client is not initialized: check EVENTS_PROVIDER_* env variables"
        )


class InternalConsistencyError(DomainError):
    def __init__(self):
        super().__init__("Internal error")
