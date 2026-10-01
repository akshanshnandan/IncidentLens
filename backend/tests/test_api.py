from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app import storage
from app.main import app


@pytest.fixture()
def client(tmp_path) -> Generator[TestClient, None, None]:
    database_url = f"sqlite:///{(tmp_path / 'test.db').as_posix()}"
    test_engine = create_engine(database_url, connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(bind=test_engine, autoflush=False, expire_on_commit=False)
    storage.Base.metadata.create_all(bind=test_engine)
    app.state.database_engine = test_engine

    def override_get_session() -> Generator[Session, None, None]:
        with TestingSessionLocal() as session:
            yield session

    app.dependency_overrides[storage.get_session] = override_get_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    del app.state.database_engine
    test_engine.dispose()


def valid_payload() -> dict:
    return {
        "timestamp": "2026-09-24T12:00:00Z",
        "service": "checkout",
        "latencies_ms": [91.2, 104.5, 88.0],
        "error_count": 1,
        "cpu_percent": 43.5,
        "memory_percent": 58.25,
    }


def test_health_returns_ok(client: TestClient):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_valid_telemetry_can_be_posted_and_is_persisted(client: TestClient):
    response = client.post("/events", json=valid_payload())

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "stored"
    assert body["event"]["id"] == 1
    assert body["event"]["service"] == "checkout"
    assert body["event"]["latencies_ms"] == [91.2, 104.5, 88.0]

    TestingSessionLocal = sessionmaker(
        bind=client.app.state.database_engine,
        autoflush=False,
        expire_on_commit=False,
    )
    with TestingSessionLocal() as session:
        stored = storage.list_recent_events(session)

    assert len(stored) == 1
    assert stored[0].service == "checkout"


def test_get_events_returns_stored_telemetry_newest_first(client: TestClient):
    older = valid_payload()
    newer = valid_payload() | {"timestamp": "2026-09-24T12:00:05Z", "service": "payments"}
    client.post("/events", json=older)
    client.post("/events", json=newer)

    response = client.get("/events?limit=2")

    assert response.status_code == 200
    events = response.json()
    assert [event["service"] for event in events] == ["payments", "checkout"]
    assert [event["id"] for event in events] == [2, 1]


@pytest.mark.parametrize(
    "field,value",
    [
        ("timestamp", "not-a-timestamp"),
        ("service", "   "),
        ("latencies_ms", []),
    ],
)
def test_invalid_telemetry_is_rejected(client: TestClient, field: str, value):
    payload = valid_payload() | {field: value}

    response = client.post("/events", json=payload)

    assert response.status_code == 422


def test_cpu_over_100_is_rejected(client: TestClient):
    response = client.post("/events", json=valid_payload() | {"cpu_percent": 100.1})

    assert response.status_code == 422


def test_memory_over_100_is_rejected(client: TestClient):
    response = client.post("/events", json=valid_payload() | {"memory_percent": 100.1})

    assert response.status_code == 422


def test_negative_latency_is_rejected(client: TestClient):
    response = client.post("/events", json=valid_payload() | {"latencies_ms": [42.0, -1.0]})

    assert response.status_code == 422


def test_negative_error_count_is_rejected(client: TestClient):
    response = client.post("/events", json=valid_payload() | {"error_count": -1})

    assert response.status_code == 422


def test_storage_supports_future_service_and_time_retrieval(client: TestClient):
    client.post("/events", json=valid_payload())
    client.post(
        "/events",
        json=valid_payload() | {"timestamp": "2026-09-24T12:01:00Z", "service": "checkout"},
    )
    client.post(
        "/events",
        json=valid_payload() | {"timestamp": "2026-09-24T12:01:30Z", "service": "api"},
    )

    TestingSessionLocal = sessionmaker(
        bind=client.app.state.database_engine,
        autoflush=False,
        expire_on_commit=False,
    )
    with TestingSessionLocal() as session:
        events = storage.list_events_for_service_since(
            session,
            service="checkout",
            start_time=datetime(2026, 9, 24, 12, 0, 30, tzinfo=UTC),
        )

    assert len(events) == 1
    assert events[0].service == "checkout"
    assert events[0].timestamp == datetime(2026, 9, 24, 12, 1, tzinfo=UTC)
