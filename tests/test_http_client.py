import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest

import http_client
from http_client import EventsApiClient, EventsPaginator


def _response(status_code=200, json_data=None, text=""):
    resp = SimpleNamespace(status_code=status_code, text=text)
    resp.reason_phrase = "OK" if status_code < 400 else "Server Error"
    resp.json = lambda: json_data
    return resp


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr(http_client, "EVENTS_PROVIDER_API_KEY", "test-key")
    return EventsApiClient(base_url="http://provider.test")


def _make_mocked_client(monkeypatch, pages):
    """Клиент с мокнутым _make_request: ответы выдаются по очереди (кортежи data/error)."""
    monkeypatch.setattr(http_client, "EVENTS_PROVIDER_API_KEY", "test-key")
    client = EventsApiClient(base_url="http://provider.test")
    client._make_request = AsyncMock(side_effect=[(page, None) for page in pages])
    return client


async def _drain(paginator):
    async for _page in paginator:
        pass


# --- EventsApiClient ---

def test_register_ticket_sends_post_with_payload(client):
    mock_request = AsyncMock(return_value=_response(201, {"ticket_id": "t-1"}))
    client.client.request = mock_request

    event_id = uuid4()
    data, error = asyncio.run(client.register_ticket(event_id, "A1", "a@b.c", "Ivan", "Petrov"))

    assert error is None
    assert data == {"ticket_id": "t-1"}
    method, endpoint = mock_request.call_args[0]
    assert method == "POST"
    assert endpoint == f"/api/events/{event_id}/register/"
    assert mock_request.call_args.kwargs["json"] == {
        "seat": "A1",
        "email": "a@b.c",
        "first_name": "Ivan",
        "last_name": "Petrov",
    }


def test_get_seats_sends_get(client):
    mock_request = AsyncMock(return_value=_response(200, {"available_seats": []}))
    client.client.request = mock_request

    event_id = uuid4()
    data, error = asyncio.run(client.get_seats(event_id))

    assert error is None
    method, endpoint = mock_request.call_args[0]
    assert method == "GET"
    assert endpoint == f"/api/events/{event_id}/seats/"


def test_register_ticket_http_error_returns_error_tuple(client):
    client.client.request = AsyncMock(
        return_value=_response(409, {"detail": "seat taken"}, text="conflict")
    )
    data, error = asyncio.run(client.register_ticket(uuid4(), "A1", "a@b.c", "I", "P"))

    assert data is None
    assert error is not None and "409" in error


def test_network_error_returns_error_tuple(client):
    client.client.request = AsyncMock(side_effect=httpx.ConnectError("boom"))
    data, error = asyncio.run(client.get_seats(uuid4()))

    assert data is None
    assert error is not None and "Network error" in error


def test_client_requires_api_key(monkeypatch):
    monkeypatch.setattr(http_client, "EVENTS_PROVIDER_API_KEY", None)
    with pytest.raises(ValueError):
        EventsApiClient(base_url="http://provider.test")


# --- EventsPaginator ---

def test_paginator_walks_all_pages(monkeypatch):
    client = _make_mocked_client(monkeypatch, [
        {"results": [{"id": "e1"}], "next": "http://provider.test/api/events/?page=2"},
        {"results": [{"id": "e2"}], "next": None},
    ])

    events = asyncio.run(client.fetch_all_events(changed_at="2026-01-01"))

    assert events == [{"id": "e1"}, {"id": "e2"}]
    first_call = client._make_request.await_args_list[0]
    assert first_call.args == ("GET", "/api/events/")
    assert first_call.kwargs.get("params") == {"changed_at": "2026-01-01"}
    second_call = client._make_request.await_args_list[1]
    # next-URL без base_url, параметры не дублируются
    assert second_call.args == ("GET", "/api/events/?page=2")
    assert second_call.kwargs.get("params") is None


def test_paginator_sync_protocol_over_buffer(monkeypatch):
    client = _make_mocked_client(monkeypatch, [
        {"results": [{"id": "a"}], "next": "http://provider.test/api/events/?page=2"},
        {"results": [{"id": "b"}], "next": None},
    ])
    paginator = EventsPaginator(client, "/api/events/", params={"changed_at": "2000-01-01"})

    asyncio.run(_drain(paginator))

    pages = list(paginator)  # __iter__/__next__ поверх загруженного буфера
    assert pages == [[{"id": "a"}], [{"id": "b"}]]
    with pytest.raises(StopIteration):
        next(paginator)


def test_paginator_raises_on_provider_error(monkeypatch):
    monkeypatch.setattr(http_client, "EVENTS_PROVIDER_API_KEY", "test-key")
    client = EventsApiClient(base_url="http://provider.test")
    client._make_request = AsyncMock(return_value=(None, "HTTP 500: internal"))

    paginator = EventsPaginator(client, "/api/events/", params={})
    with pytest.raises(RuntimeError):
        asyncio.run(_drain(paginator))


def test_paginator_handles_non_dict_response(monkeypatch):
    client = _make_mocked_client(monkeypatch, [[1, 2, 3]])
    events = asyncio.run(client.fetch_all_events())
    assert events == []
