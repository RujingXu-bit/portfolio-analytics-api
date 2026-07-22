import json
from pathlib import Path

import pytest
from benchmarks.fixture import (
    COLD_WINDOW_CAPACITY,
    MAX_WINDOW_DAYS,
    MIN_WINDOW_DAYS,
    PRICE_BAR_COUNT,
    PRICE_BARS,
    cold_query_window,
    hot_query_window,
)
from benchmarks.reporting import (
    percentile,
    read_json_log_slice,
    read_locust_metrics,
    summarize_application_logs,
)


def test_fixture_has_expected_size_and_unique_cold_windows() -> None:
    assert len(PRICE_BARS) == PRICE_BAR_COUNT == 2_000
    sample_windows = [cold_query_window(index) for index in range(10_000)]
    assert len(set(sample_windows)) == len(sample_windows)
    assert COLD_WINDOW_CAPACITY > 300_000
    for start_date, end_date in sample_windows:
        point_count = sum(start_date <= bar.date <= end_date for bar in PRICE_BARS)
        assert MIN_WINDOW_DAYS <= point_count <= MAX_WINDOW_DAYS
    hot_start, hot_end = hot_query_window()
    assert sum(hot_start <= bar.date <= hot_end for bar in PRICE_BARS) == 252


def test_cold_window_rejects_negative_ordinals() -> None:
    with pytest.raises(ValueError, match="ordinal"):
        cold_query_window(-1)


def test_reporting_reads_locust_and_structured_application_metrics(
    tmp_path: Path,
) -> None:
    stats_path = tmp_path / "stats.json"
    stats_path.write_text(
        json.dumps(
            [
                {
                    "name": "GET /portfolios/{portfolio_id}/analytics",
                    "method": "GET",
                    "num_requests": 100,
                    "num_failures": 0,
                    "start_time": 10.0,
                    "last_request_timestamp": 12.0,
                    "response_times": {"12": 50, "25": 45, "30": 5},
                }
            ]
        ),
        encoding="utf-8",
    )
    assert read_locust_metrics(stats_path) == {
        "request_count": 100,
        "failure_count": 0,
        "p50_ms": 12.0,
        "p95_ms": 25.0,
        "requests_per_second": 50.0,
    }

    log_path = tmp_path / "application.jsonl"
    prefix = "ignored prefix\n"
    records = [
        {"event": "market_data.cache", "cache_status": "miss"},
        {
            "event": "market_data.provider.request",
            "outcome": "success",
            "duration_ms": 51.0,
        },
        {"event": "market_data.cache", "cache_status": "hit"},
        {
            "event": "market_data.provider.request",
            "outcome": "success",
            "duration_ms": 49.0,
        },
    ]
    log_path.write_text(
        prefix + "".join(json.dumps(record) + "\n" for record in records),
        encoding="utf-8",
    )
    summary = summarize_application_logs(
        read_json_log_slice(log_path, len(prefix.encode("utf-8")))
    )
    assert summary == {
        "cache_hits": 1,
        "cache_misses": 1,
        "cache_hit_rate_percent": 50.0,
        "provider_calls": 2,
        "provider_p50_ms": 49.0,
        "provider_p95_ms": 51.0,
    }


def test_reporting_validates_missing_rows_and_percentiles(tmp_path: Path) -> None:
    path = tmp_path / "empty.json"
    path.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="exactly one"):
        read_locust_metrics(path)
    assert percentile([], 50) is None
    assert percentile([5, 1, 3, 2, 4], 50) == 3
    assert percentile([5, 1, 3, 2, 4], 95) == 5
    with pytest.raises(ValueError, match="percentile"):
        percentile([1], 0)
