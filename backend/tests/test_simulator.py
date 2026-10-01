from __future__ import annotations

from datetime import UTC, datetime

from app.simulator import (
    FAULT_ERROR_BURST,
    FAULT_LATENCY_SPIKE,
    FAULT_RESOURCE_SATURATION,
    FaultWindow,
    fault_label_to_dict,
    generate_telemetry,
    labels_for_faults,
    telemetry_bucket_to_dict,
)


START_TIME = datetime(2026, 9, 24, 12, 0, tzinfo=UTC)


def _average_latency(bucket) -> float:
    return sum(bucket.latencies_ms) / len(bucket.latencies_ms)


def _generate_with_fault(fault_type: str):
    fault = FaultWindow(
        fault_type=fault_type,
        start=datetime(2026, 9, 24, 12, 1, tzinfo=UTC),
        end=datetime(2026, 9, 24, 12, 2, tzinfo=UTC),
    )
    return generate_telemetry(
        seed=123,
        start_time=START_TIME,
        duration_seconds=180,
        service_name="checkout",
        faults=[fault],
    )


def test_same_seed_and_configuration_produce_identical_telemetry():
    fault = FaultWindow(
        fault_type=FAULT_LATENCY_SPIKE,
        start=datetime(2026, 9, 24, 12, 0, 10, tzinfo=UTC),
        end=datetime(2026, 9, 24, 12, 0, 20, tzinfo=UTC),
    )

    first = generate_telemetry(
        seed=42,
        start_time=START_TIME,
        duration_seconds=30,
        service_name="checkout",
        faults=[fault],
    )
    second = generate_telemetry(
        seed=42,
        start_time=START_TIME,
        duration_seconds=30,
        service_name="checkout",
        faults=[fault],
    )

    assert [telemetry_bucket_to_dict(bucket) for bucket in first] == [
        telemetry_bucket_to_dict(bucket) for bucket in second
    ]


def test_generated_telemetry_values_stay_within_sensible_ranges():
    buckets = generate_telemetry(
        seed=7,
        start_time=START_TIME,
        duration_seconds=60,
        service_name="api",
        faults=[],
    )

    for bucket in buckets:
        assert bucket.timestamp.tzinfo == UTC
        assert bucket.service == "api"
        assert 50 <= len(bucket.latencies_ms) <= 150
        assert all(5.0 <= latency <= 2500.0 for latency in bucket.latencies_ms)
        assert 0 <= bucket.error_count <= len(bucket.latencies_ms)
        assert 0.0 <= bucket.cpu_percent <= 100.0
        assert 0.0 <= bucket.memory_percent <= 100.0


def test_latency_spike_clearly_changes_latency():
    buckets = _generate_with_fault(FAULT_LATENCY_SPIKE)

    normal_average = sum(_average_latency(bucket) for bucket in buckets[:60]) / 60
    fault_average = sum(_average_latency(bucket) for bucket in buckets[60:120]) / 60

    assert fault_average > normal_average * 2.0


def test_error_burst_clearly_changes_errors():
    buckets = _generate_with_fault(FAULT_ERROR_BURST)

    normal_errors = sum(bucket.error_count for bucket in buckets[:60])
    fault_errors = sum(bucket.error_count for bucket in buckets[60:120])

    assert fault_errors > normal_errors * 5


def test_resource_saturation_clearly_changes_cpu_and_memory():
    buckets = _generate_with_fault(FAULT_RESOURCE_SATURATION)

    normal_cpu = sum(bucket.cpu_percent for bucket in buckets[:60]) / 60
    fault_cpu = sum(bucket.cpu_percent for bucket in buckets[60:120]) / 60
    normal_memory = sum(bucket.memory_percent for bucket in buckets[:60]) / 60
    fault_memory = sum(bucket.memory_percent for bucket in buckets[60:120]) / 60

    assert fault_cpu > normal_cpu + 30
    assert fault_memory > normal_memory + 20


def test_ground_truth_labels_contain_correct_fault_types_and_timestamps():
    fault = FaultWindow(
        fault_type=FAULT_ERROR_BURST,
        start=datetime(2026, 9, 24, 12, 3, tzinfo=UTC),
        end=datetime(2026, 9, 24, 12, 4, tzinfo=UTC),
    )

    labels = labels_for_faults([fault])

    assert [fault_label_to_dict(label) for label in labels] == [
        {
            "fault_type": "error_burst",
            "start": "2026-09-24T12:03:00Z",
            "end": "2026-09-24T12:04:00Z",
        }
    ]


def test_fault_labels_are_not_leaked_into_telemetry_buckets():
    buckets = _generate_with_fault(FAULT_RESOURCE_SATURATION)

    serialized_bucket = telemetry_bucket_to_dict(buckets[75])

    assert "fault_type" not in serialized_bucket
    assert "fault" not in serialized_bucket
    assert "label" not in serialized_bucket
    assert set(serialized_bucket) == {
        "timestamp",
        "service",
        "latencies_ms",
        "error_count",
        "cpu_percent",
        "memory_percent",
    }
