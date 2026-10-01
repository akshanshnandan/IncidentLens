"""FastAPI application for IncidentLens telemetry ingestion."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Query, status
from sqlalchemy.orm import Session

from app import storage
from app.schemas import (
    EventIngestResponse,
    HealthResponse,
    TelemetryEventCreate,
    TelemetryEventRead,
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    database_engine = getattr(app.state, "database_engine", storage.engine)
    storage.init_db(database_engine)
    yield


app = FastAPI(title="IncidentLens Telemetry API", lifespan=lifespan)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@app.post("/events", response_model=EventIngestResponse, status_code=status.HTTP_201_CREATED)
def create_event(
    event: TelemetryEventCreate,
    session: Session = Depends(storage.get_session),
) -> EventIngestResponse:
    stored_event = storage.store_event(session, event)
    return EventIngestResponse(status="stored", event=stored_event)


@app.get("/events", response_model=list[TelemetryEventRead])
def get_events(
    limit: int = Query(default=100, ge=1, le=1000),
    session: Session = Depends(storage.get_session),
) -> list[TelemetryEventRead]:
    """Return the newest stored telemetry buckets first."""

    return storage.list_recent_events(session, limit=limit)
