import uuid
from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_successful_registration(client, valid_event):
    """Успешная регистрация: событие есть в БД, место свободно, провайдер отвечает успехом."""
    with patch("http_client.EventsApiClient.register_ticket") as mock_register:
        mock_register.return_value = ({"ticket_id": "ticket-123"}, None)

        response = client.post("/api/tickets", json={
            "first_name": "Ivan",
            "last_name": "Petrov",
            "email": "ivan@test.com",
            "seat": "A1",
            "event_id": str(valid_event.id),  # UUID из БД, приводим к строке для JSON
        })

    assert response.status_code == 201, \
        f"Ожидался 201, но получил {response.status_code}: {response.text}"
    data = response.json()
    assert "ticket_id" in data or data.get("status") == "registered"


@pytest.mark.asyncio
async def test_double_registration_conflict(client, valid_event):
    """Повторная регистрация на то же место должна дать 400 или 409."""
    with patch("http_client.EventsApiClient.register_ticket") as mock_register:
        mock_register.return_value = ({"ticket_id": "ticket-first"}, None)

        # Первый запрос — успешный
        r1 = client.post("/api/tickets", json={
            "first_name": "Ivan1",
            "last_name": "P1",
            "email": "i1@test.com",
            "seat": "A1",
            "event_id": str(valid_event.id),
        })
        assert r1.status_code == 201, \
            f"Первый запрос: ожидался 201, но получил {r1.status_code}: {r1.text}"

    # Второй запрос — конфликт (сработает проверка find_by_seat_and_event в UseCase)
    r2 = client.post("/api/tickets", json={
        "first_name": "Ivan2",
        "last_name": "P2",
        "email": "i2@test.com",
        "seat": "A1",
        "event_id": str(valid_event.id),
    })

    assert r2.status_code in [400, 409], \
        f"Ожидался 400 или 409, но получил {r2.status_code}: {r2.text}"


@pytest.mark.asyncio
async def test_registration_non_existent_event(client):
    """Регистрация на несуществующее событие — 400 или 404."""
    fake_id = str(uuid.uuid4())

    response = client.post("/api/tickets", json={
        "first_name": "Bad",
        "last_name": "User",
        "email": "bad@test.com",
        "seat": "A1",
        "event_id": fake_id,
    })

    assert response.status_code in [400, 404], \
        f"Получил {response.status_code}, а ждал 400 или 404: {response.text}"
    if response.status_code == 404:
        detail = str(response.json().get("detail", ""))
        assert "not found" in detail.lower()


@pytest.mark.asyncio
async def test_cache_seats_endpoint(client, valid_event):
    """Эндпоинт мест должен отвечать 200 для события из БД."""
    mock_get_seats = AsyncMock()
    mock_get_seats.return_value = (
        {
            "available_seats": [
                {"seat": "A1", "status": "available"},
                {"seat": "B1", "status": "booked"},
            ]
        },
        None,
    )

    with patch("main.client.get_seats", mock_get_seats):
        response = client.get(f"/api/events/{valid_event.id!s}/seats")

    assert response.status_code == 200, \
        f"Получил {response.status_code}: {response.text}"
    data = response.json()
    assert isinstance(data, dict)



@pytest.mark.asyncio
async def test_api_provider_failure_handling(client, valid_event):
    """Если внешний API падает — эндпоинт возвращает ошибку сервера."""
    def raise_network_error(*args, **kwargs):
        raise Exception("Network error from provider")

    with patch("http_client.EventsApiClient.register_ticket",
           side_effect=raise_network_error):
        response = client.post("/api/tickets", json={
            "first_name": "Crash",
            "last_name": "Test",
            "email": "crash@test.com",
            "seat": "A1",
            "event_id": str(valid_event.id),
        })

    assert response.status_code >= 500, \
        f"Ожидается ошибка сервера (>=500), но получил {response.status_code}: {response.text}"
