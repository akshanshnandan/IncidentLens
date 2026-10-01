"""SQLite persistence for telemetry events."""

from __future__ import annotations

import json
import os
from collections.abc import Generator
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import DateTime, Float, Integer, String, Text, create_engine, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from app.schemas import TelemetryEventCreate, TelemetryEventRead


DEFAULT_DATABASE_PATH = Path(__file__).resolve().parents[1] / "data" / "incidentlens.db"
DEFAULT_DATABASE_URL = f"sqlite:///{DEFAULT_DATABASE_PATH.as_posix()}"
DATABASE_URL_ENV_VAR = "INCIDENTLENS_DATABASE_URL"


class Base(DeclarativeBase):
    pass


class TelemetryEventRow(Base):
    """SQLAlchemy row for one stored telemetry bucket."""

    __tablename__ = "telemetry_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    service: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    latencies_ms_json: Mapped[str] = mapped_column(Text, nullable=False)
    error_count: Mapped[int] = mapped_column(Integer, nullable=False)
    cpu_percent: Mapped[float] = mapped_column(Float, nullable=False)
    memory_percent: Mapped[float] = mapped_column(Float, nullable=False)


def database_url_from_env() -> str:
    return os.getenv(DATABASE_URL_ENV_VAR, DEFAULT_DATABASE_URL)


def create_database_engine(database_url: str | None = None) -> Engine:
    resolved_url = database_url or database_url_from_env()
    if resolved_url.startswith("sqlite:///"):
        database_path = Path(resolved_url.removeprefix("sqlite:///"))
        if not database_path.is_absolute():
            database_path = Path.cwd() / database_path
        database_path.parent.mkdir(parents=True, exist_ok=True)

    connect_args = {"check_same_thread": False} if resolved_url.startswith("sqlite") else {}
    return create_engine(resolved_url, connect_args=connect_args)


engine = create_database_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def init_db(database_engine: Engine = engine) -> None:
    Base.metadata.create_all(bind=database_engine)


def get_session() -> Generator[Session, None, None]:
    with SessionLocal() as session:
        yield session


def _row_to_schema(row: TelemetryEventRow) -> TelemetryEventRead:
    timestamp = row.timestamp
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=UTC)

    return TelemetryEventRead(
        id=row.id,
        timestamp=timestamp,
        service=row.service,
        latencies_ms=json.loads(row.latencies_ms_json),
        error_count=row.error_count,
        cpu_percent=row.cpu_percent,
        memory_percent=row.memory_percent,
    )


def store_event(session: Session, event: TelemetryEventCreate) -> TelemetryEventRead:
    row = TelemetryEventRow(
        timestamp=event.timestamp,
        service=event.service,
        latencies_ms_json=json.dumps(event.latencies_ms),
        error_count=event.error_count,
        cpu_percent=event.cpu_percent,
        memory_percent=event.memory_percent,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return _row_to_schema(row)


def list_recent_events(session: Session, limit: int = 100) -> list[TelemetryEventRead]:
    query = select(TelemetryEventRow).order_by(TelemetryEventRow.timestamp.desc()).limit(limit)
    rows = session.scalars(query).all()
    return [_row_to_schema(row) for row in rows]


def list_events_for_service_since(
    session: Session,
    *,
    service: str,
    start_time: datetime,
    limit: int = 1000,
) -> list[TelemetryEventRead]:
    """Simple retrieval hook for future rolling-feature code."""

    query = (
        select(TelemetryEventRow)
        .where(TelemetryEventRow.service == service)
        .where(TelemetryEventRow.timestamp >= start_time)
        .order_by(TelemetryEventRow.timestamp.asc())
        .limit(limit)
    )
    rows = session.scalars(query).all()
    return [_row_to_schema(row) for row in rows]
