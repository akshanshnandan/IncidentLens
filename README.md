# IncidentLens
IncidentLens monitors live service data like latency, errors, CPU, and memory, then detects when something goes wrong. It automatically creates incidents and shows them on a live dashboard. Basically, it's a mini version of the monitoring systems real engineering teams use.

## Backend setup

Install the backend dependencies:

```bash
cd backend
py -m pip install -e ".[dev]"
```

Run the tests:

```bash
py -m pytest
```

## Milestone 1: Telemetry Simulator

Run a normal simulation:

```bash
py -m app.simulator --seed 42 --start-time 2026-09-24T12:00:00Z --duration 10 --service checkout --telemetry-output output/telemetry.jsonl --labels-output output/labels.json
```

Run a simulation with scheduled faults by passing a JSON file like:

```json
[
  {
    "fault_type": "latency_spike",
    "start": "2026-09-24T12:00:20Z",
    "end": "2026-09-24T12:00:40Z"
  },
  {
    "fault_type": "error_burst",
    "start": "2026-09-24T12:00:45Z",
    "end": "2026-09-24T12:00:55Z"
  }
]
```

```bash
py -m app.simulator --seed 42 --start-time 2026-09-24T12:00:00Z --duration 60 --service checkout --fault-schedule output/faults.json --telemetry-output output/telemetry-with-faults.jsonl --labels-output output/labels-with-faults.json
```

## Milestone 2: Telemetry API and SQLite Storage

Start the FastAPI app:

```bash
cd backend
py -m uvicorn app.main:app --reload
```

Check health:

```bash
py -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/health').read().decode())"
```

Generate telemetry JSONL:

```bash
py -m app.simulator --seed 42 --start-time 2026-09-24T12:00:00Z --duration 10 --service checkout --telemetry-output output/telemetry.jsonl --labels-output output/labels.json
```

Send telemetry into the running API:

```bash
py -m app.send_telemetry --telemetry-input output/telemetry.jsonl --api-url http://127.0.0.1:8000
```

View stored events, newest first:

```bash
py -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/events?limit=5').read().decode())"
```
