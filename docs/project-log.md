## Milestone 1 - Deterministic Telemetry Simulator

Implemented a deterministic telemetry simulator that generates one bucket per simulated second with normal traffic variation for latency, errors, CPU, and memory.

Supported scheduled `latency_spike`, `error_burst`, and `resource_saturation` faults. Ground-truth fault labels are written separately from telemetry so future anomaly detection does not receive fault labels as input.

Added focused pytest coverage for determinism, sensible value ranges, fault behavior, label correctness, and prevention of label leakage into telemetry.

Local Windows verification succeeded: `py -m pip install -e ".[dev]"` completed, `py -m pytest` collected and passed 7 tests, and the CLI generated telemetry JSONL plus labels JSON successfully.

## Milestone 2 - FastAPI Telemetry Ingestion and SQLite Storage

Implemented a small FastAPI app with `GET /health`, `POST /events`, and `GET /events`. Incoming telemetry is validated with Pydantic schemas matching simulator buckets: UTC timestamp, service name, latency list, error count, CPU percent, and memory percent.

Added SQLite persistence with SQLAlchemy 2.x. Each telemetry bucket is stored as one `telemetry_events` row with an auto-incrementing ID, timestamp, service, JSON-serialized latency list, error count, CPU percent, and memory percent. The default local database lives under `backend/data/incidentlens.db`, can be overridden with `INCIDENTLENS_DATABASE_URL`, and is ignored by git.

Added focused API/storage tests using an isolated temporary SQLite database. Coverage includes health checks, valid ingestion, persistence, retrieval, invalid payload rejection, CPU and memory bounds, negative latency/error rejection, and a simple storage retrieval helper for future time/service queries.

Added `app.send_telemetry`, a tiny JSONL sender that posts simulator-generated telemetry to the API without sending ground-truth labels or changing the simulator.
