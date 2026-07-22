import itertools
import os

from locust import HttpUser, task

from benchmarks.fixture import cold_query_window, hot_query_window

_portfolio_id = os.environ["BENCHMARK_PORTFOLIO_ID"]
_access_token = os.environ["BENCHMARK_ACCESS_TOKEN"]
_scenario = os.environ["BENCHMARK_SCENARIO"]
if _scenario not in {"cold", "hot"}:
    raise RuntimeError("BENCHMARK_SCENARIO must be 'cold' or 'hot'")
_cold_ordinals = itertools.count()


class AnalyticsUser(HttpUser):
    @task
    def analytics(self) -> None:
        if _scenario == "cold":
            start_date, end_date = cold_query_window(next(_cold_ordinals))
        else:
            start_date, end_date = hot_query_window()
        with self.client.get(
            f"/portfolios/{_portfolio_id}/analytics",
            params={
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
            },
            headers={"Authorization": f"Bearer {_access_token}"},
            name="GET /portfolios/{portfolio_id}/analytics",
            catch_response=True,
        ) as response:
            if response.status_code != 200:
                response.failure(f"unexpected status {response.status_code}")
            elif response.json().get("stale") is not False:
                response.failure("benchmark analytics unexpectedly used stale data")
