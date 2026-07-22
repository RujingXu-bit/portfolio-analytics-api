import json
from collections.abc import Iterable
from pathlib import Path
from typing import TypedDict


class LocustMetrics(TypedDict):
    request_count: int
    failure_count: int
    p50_ms: float
    p95_ms: float
    requests_per_second: float


class ApplicationMetrics(TypedDict):
    cache_hits: int
    cache_misses: int
    cache_hit_rate_percent: float
    provider_calls: int
    provider_p50_ms: float | None
    provider_p95_ms: float | None


def read_locust_metrics(path: Path) -> LocustMetrics:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list) or len(payload) != 1:
        raise ValueError("Locust JSON must contain exactly one request row")
    row = payload[0]
    if not isinstance(row, dict):
        raise ValueError("Locust request row must be an object")
    response_times = row.get("response_times")
    if not isinstance(response_times, dict):
        raise ValueError("Locust request row has no response-time histogram")
    histogram = {
        float(response_time): int(count)
        for response_time, count in response_times.items()
        if isinstance(response_time, str) and isinstance(count, int)
    }
    request_count = int(row["num_requests"])
    started_at = float(row["start_time"])
    finished_at = float(row["last_request_timestamp"])
    return {
        "request_count": request_count,
        "failure_count": int(row["num_failures"]),
        "p50_ms": _histogram_percentile(histogram, 50),
        "p95_ms": _histogram_percentile(histogram, 95),
        "requests_per_second": round(
            request_count / max(finished_at - started_at, 0.001), 3
        ),
    }


def read_json_log_slice(path: Path, offset: int) -> list[dict[str, object]]:
    with path.open(encoding="utf-8") as source:
        source.seek(offset)
        records: list[dict[str, object]] = []
        for line in source:
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                records.append(value)
        return records


def summarize_application_logs(
    records: Iterable[dict[str, object]],
) -> ApplicationMetrics:
    records = list(records)
    cache_statuses = [
        record.get("cache_status")
        for record in records
        if record.get("event") == "market_data.cache"
    ]
    cache_hits = cache_statuses.count("hit")
    cache_misses = cache_statuses.count("miss")
    cache_lookups = cache_hits + cache_misses
    provider_latencies: list[float] = []
    for record in records:
        duration = record.get("duration_ms")
        if (
            record.get("event") == "market_data.provider.request"
            and record.get("outcome") == "success"
            and isinstance(duration, int | float)
        ):
            provider_latencies.append(float(duration))
    return {
        "cache_hits": cache_hits,
        "cache_misses": cache_misses,
        "cache_hit_rate_percent": (
            round(cache_hits / cache_lookups * 100, 3) if cache_lookups else 0.0
        ),
        "provider_calls": len(provider_latencies),
        "provider_p50_ms": percentile(provider_latencies, 50),
        "provider_p95_ms": percentile(provider_latencies, 95),
    }


def percentile(values: Iterable[float], percentile_value: int) -> float | None:
    if not 0 < percentile_value <= 100:
        raise ValueError("percentile must be between 1 and 100")
    ordered = sorted(values)
    if not ordered:
        return None
    index = max(0, (len(ordered) * percentile_value + 99) // 100 - 1)
    return round(ordered[index], 3)


def _histogram_percentile(histogram: dict[float, int], percentile_value: int) -> float:
    total = sum(histogram.values())
    if total <= 0:
        raise ValueError("Locust response-time histogram must not be empty")
    target = (total * percentile_value + 99) // 100
    cumulative = 0
    for response_time, count in sorted(histogram.items()):
        cumulative += count
        if cumulative >= target:
            return response_time
    raise AssertionError("histogram percentile must resolve")
