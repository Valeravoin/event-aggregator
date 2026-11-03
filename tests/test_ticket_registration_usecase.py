from datetime import UTC, datetime
from unittest.mock import Mock
from uuid import uuid4

import pytest

from http_client import EventsApiClient
from repositories.event_repository import EventRepository
from repositories.registration_repository import RegistrationRepository
from services.ticket_registration_usecase import TicketRegistrationUseCase


@pytest.mark.asyncio
async def test_registration_success():
    # Генерируем event_id как строку — именно так ожидает репозиторий
    event_id = str(uuid4())

    # Мок события
    mock_event = Mock()
    mock_event.id = event_id
    mock_event.status = "published"
    mock_event.registration_deadline = datetime(2099, 1, 1, tzinfo=UTC)
    mock_event.name = "Test Event"

    # Мок репозитория событий
    mock_event_repo = Mock(spec=EventRepository)
    mock_event_repo.get_by_id.return_value = mock_event

    # Мок репозитория регистраций
    # spec=RegistrationRepository можно оставить, потому что мы уже добавили find_by_seat_and_event
    mock_ticket_repo = Mock(spec=RegistrationRepository)

    # ВАЖНО: Мокаем метод, который реально вызывается в UseCase
    # Возвращаем None — значит, места A1 ещё никто не занял, регистрация возможна
    mock_ticket_repo.find_by_seat_and_event.return_value = None

    # Мок объекта регистрации (результат create)
    mock_reg = Mock()
    mock_reg.ticket_id = "ticket-123"
    mock_ticket_repo.create.return_value = mock_reg

    # Мок HTTP-клиента
    mock_client = Mock(spec=EventsApiClient)
    # UseCase ожидает кортеж (data, error)
    mock_client.register_ticket.return_value = ({"ticket_id": "ticket-123"}, None)

    # Создаём UseCase с моками
    usecase = TicketRegistrationUseCase(
        event_repo=mock_event_repo,
        ticket_repo=mock_ticket_repo,
        client=mock_client,
    )

    # Вызываем do через await — это критично, иначе будет ошибка про корутину
    result = await usecase.do(
        first_name="Ivan",
        last_name="Petrov",
        email="ivan@example.com",
        event_id=event_id,  # передаём строку
        seat="A1",
    )

    # Проверки
    assert result["status"] == "registered"
    assert mock_client.register_ticket.called
    assert mock_ticket_repo.create.called
    assert mock_ticket_repo.find_by_seat_and_event.called
