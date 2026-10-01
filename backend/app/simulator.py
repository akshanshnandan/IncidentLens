"""Deterministic telemetry simulator for IncidentLens.

This module intentionally stays small and explicit. It generates one telemetry
bucket per simulated second, and it keeps ground-truth fault labels separate
from the telemetry so future detectors cannot see the answer key.
"""

from __future__ import annotations

import argparse
import json
import random
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable


FAULT_LATENCY_SPIKE = "latency_spike"
FAULT_ERROR_BURST = "error_burst"
FAULT_RESOURCE_SATURATION = "resource_saturation"
SUPPORTED_FAULT_TYPES = {
    FAULT_LATENCY_SPIKE,
    FAULT_ERROR_BURST,
    FAULT_RESOURCE_SATURATION,
}


@dataclass(frozen=True)
class FaultWindow:
    """A scheduled fault with an explicit UTC start and end time."""

    fault_type: str
    start: datetime
    end: datetime

    def is_active_at(self, timestamp: datetime) -> bool:
        return self.start <= timestamp < self.end


@dataclass(frozen=True)
class TelemetryBucket:
    """One second of service telemetry."""

    timestamp: datetime
    service: str
    latencies_ms: list[float]
    error_count: int
    cpu_percent: float
    memory_percent: float


@dataclass(frozen=True)
class FaultLabel:
    """Ground-truth fault label for future evaluation."""

    fault_type: str
    start: datetime
    end: datetime


def parse_utc_datetime(value: str) -> datetime:
    """Parse an ISO-8601 timestamp and return a timezone-aware UTC datetime."""

    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        raise ValueError(f"Timestamp must include a timezone: {value}")
    return parsed.astimezone(UTC)


def _serialize_datetime(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _count_successes(rng: random.Random, trials: int, probability: float) -> int:
    return sum(1 for _ in range(trials) if rng.random() < probability)


def load_fault_schedule(path: str | Path | None) -> list[FaultWindow]:
    """Load a fault schedule from a JSON file.

    The expected format is a list of objects:
    [
      {"fault_type": "latency_spike", "start": "...Z", "end": "...Z"}
    ]
    """

    if path is None:
        return []

    raw_faults = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(raw_faults, list):
        raise ValueError("Fault schedule must be a JSON list.")

    faults: list[FaultWindow] = []
    for raw_fault in raw_faults:
        fault_type = raw_fault["fault_type"]
        if fault_type not in SUPPORTED_FAULT_TYPES:
            supported = ", ".join(sorted(SUPPORTED_FAULT_TYPES))
            raise ValueError(f"Unsupported fault type {fault_type!r}. Use one of: {supported}.")

        start = parse_utc_datetime(raw_fault["start"])
        end = parse_utc_datetime(raw_fault["end"])
        if end <= start:
            raise ValueError("Fault end timestamp must be after start timestamp.")

        faults.append(FaultWindow(fault_type=fault_type, start=start, end=end))

    return faults


def labels_for_faults(faults: Iterable[FaultWindow]) -> list[FaultLabel]:
    return [
        FaultLabel(fault_type=fault.fault_type, start=fault.start, end=fault.end)
        for fault in faults
    ]


def generate_telemetry(
    *,
    seed: int,
    start_time: datetime,
    duration_seconds: int,
    service_name: str,
    faults: Iterable[FaultWindow] | None = None,
) -> list[TelemetryBucket]:
    """Generate deterministic telemetry buckets."""

    if duration_seconds < 0:
        raise ValueError("duration_seconds must be non-negative.")

    start_time = start_time.astimezone(UTC)
    scheduled_faults = list(faults or [])
    rng = random.Random(seed)
    buckets: list[TelemetryBucket] = []

    for offset_seconds in range(duration_seconds):
        timestamp = start_time + timedelta(seconds=offset_seconds)
        active_fault_types = {
            fault.fault_type for fault in scheduled_faults if fault.is_active_at(timestamp)
        }

        request_count = rng.randint(70, 130)
        latency_spike = FAULT_LATENCY_SPIKE in active_fault_types
        error_burst = FAULT_ERROR_BURST in active_fault_types
        resource_saturation = FAULT_RESOURCE_SATURATION in active_fault_types

        base_latency = rng.gauss(95.0, 10.0)
        latencies_ms: list[float] = []
        for _ in range(request_count):
            latency = rng.gauss(base_latency, 18.0)
            if latency_spike:
                latency = latency * rng.uniform(2.5, 3.5) + rng.uniform(120.0, 220.0)
            latencies_ms.append(round(_clamp(latency, 5.0, 2500.0), 2))

        error_probability = 0.008
        if error_burst:
            error_probability = 0.13
        error_count = _count_successes(rng, request_count, error_probability)

        cpu_percent = rng.gauss(38.0, 7.0)
        memory_percent = rng.gauss(52.0, 6.0)
        if resource_saturation:
            cpu_percent += rng.uniform(35.0, 48.0)
            memory_percent += rng.uniform(25.0, 38.0)

        buckets.append(
            TelemetryBucket(
                timestamp=timestamp,
                service=service_name,
                latencies_ms=latencies_ms,
                error_count=error_count,
                cpu_percent=round(_clamp(cpu_percent, 0.0, 100.0), 2),
                memory_percent=round(_clamp(memory_percent, 0.0, 100.0), 2),
            )
        )

    return buckets


def telemetry_bucket_to_dict(bucket: TelemetryBucket) -> dict[str, Any]:
    data = asdict(bucket)
    data["timestamp"] = _serialize_datetime(bucket.timestamp)
    return data


def fault_label_to_dict(label: FaultLabel) -> dict[str, str]:
    return {
        "fault_type": label.fault_type,
        "start": _serialize_datetime(label.start),
        "end": _serialize_datetime(label.end),
    }


def write_telemetry_jsonl(buckets: Iterable[TelemetryBucket], path: str | Path) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as output_file:
        for bucket in buckets:
            output_file.write(json.dumps(telemetry_bucket_to_dict(bucket)) + "\n")


def write_fault_labels_json(labels: Iterable[FaultLabel], path: str | Path) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    label_data = [fault_label_to_dict(label) for label in labels]
    output_path.write_text(json.dumps(label_data, indent=2) + "\n", encoding="utf-8")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate deterministic IncidentLens telemetry.")
    parser.add_argument("--seed", type=int, required=True, help="Random seed for reproducible output.")
    parser.add_argument(
        "--start-time",
        required=True,
        help="UTC simulation start time, for example 2026-09-24T12:00:00Z.",
    )
    parser.add_argument(
        "--duration",
        type=int,
        required=True,
        help="Simulation duration in seconds.",
    )
    parser.add_argument("--service", required=True, help="Service name to include in telemetry.")
    parser.add_argument(
        "--fault-schedule",
        help="Optional path to a JSON fault schedule.",
    )
    parser.add_argument(
        "--telemetry-output",
        required=True,
        help="Path for telemetry JSONL output.",
    )
    parser.add_argument(
        "--labels-output",
        required=True,
        help="Path for ground-truth fault labels JSON output.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    start_time = parse_utc_datetime(args.start_time)
    faults = load_fault_schedule(args.fault_schedule)
    buckets = generate_telemetry(
        seed=args.seed,
        start_time=start_time,
        duration_seconds=args.duration,
        service_name=args.service,
        faults=faults,
    )
    labels = labels_for_faults(faults)

    write_telemetry_jsonl(buckets, args.telemetry_output)
    write_fault_labels_json(labels, args.labels_output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
