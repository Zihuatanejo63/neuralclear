"""Prometheus text metrics for the clearing gateway.

Labels may include a tenant id. They never include an API key or other secret.
"""

from __future__ import annotations

import threading
import time

BUCKETS: tuple[float, ...] = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10)


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\n", "").replace('"', '\\"')


def _le(bound: float) -> str:
    text = f"{bound:.3f}".rstrip("0").rstrip(".")
    return text or "0"


class GatewayMetrics:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.started = time.time()
        self._requests: dict[tuple[str, str, str, str], int] = {}
        self._auth = {"missing": 0, "invalid": 0}
        self._bucket: dict[tuple[str, str, str], int] = {}
        self._sum: dict[tuple[str, str], float] = {}
        self._count: dict[tuple[str, str], int] = {}

    def observe(
        self,
        method: str,
        route: str,
        status: int,
        tenant_id: str,
        elapsed_seconds: float,
    ) -> None:
        status_text = str(status)
        request_key = (method, route, status_text, tenant_id)
        series = (method, route)
        with self._lock:
            self._requests[request_key] = self._requests.get(request_key, 0) + 1
            self._count[series] = self._count.get(series, 0) + 1
            self._sum[series] = self._sum.get(series, 0.0) + float(elapsed_seconds)
            for bound in BUCKETS:
                if elapsed_seconds <= bound:
                    key = (method, route, _le(bound))
                    self._bucket[key] = self._bucket.get(key, 0) + 1
            inf_key = (method, route, "+Inf")
            self._bucket[inf_key] = self._bucket.get(inf_key, 0) + 1

    def auth_failure(self, reason: str) -> None:
        if reason not in {"missing", "invalid"}:
            reason = "invalid"
        with self._lock:
            self._auth[reason] = self._auth.get(reason, 0) + 1

    def render(self, *, ready: bool) -> str:
        with self._lock:
            requests = dict(self._requests)
            auth = dict(self._auth)
            buckets = dict(self._bucket)
            sums = dict(self._sum)
            counts = dict(self._count)
        lines = [
            "# HELP neuralclear_gateway_up 1 when the gateway process is serving metrics.",
            "# TYPE neuralclear_gateway_up gauge",
            "neuralclear_gateway_up 1",
            "# HELP neuralclear_gateway_ready 1 when configured storage answers.",
            "# TYPE neuralclear_gateway_ready gauge",
            f"neuralclear_gateway_ready {1 if ready else 0}",
            "# HELP neuralclear_gateway_start_time_seconds Unix time when the process started.",
            "# TYPE neuralclear_gateway_start_time_seconds gauge",
            f"neuralclear_gateway_start_time_seconds {self.started:.3f}",
            "# HELP neuralclear_gateway_info Process info. fiat_settlement stays not_live in this build.",
            "# TYPE neuralclear_gateway_info gauge",
            'neuralclear_gateway_info{version="0.4.0.dev0",fiat_settlement="not_live"} 1',
            "# HELP neuralclear_http_requests_total HTTP requests by method, route template, status, and tenant.",
            "# TYPE neuralclear_http_requests_total counter",
        ]
        for method, route, status, tenant_id in sorted(requests):
            labels = (
                f'method="{_escape(method)}",route="{_escape(route)}",'
                f'status="{_escape(status)}",tenant_id="{_escape(tenant_id)}"'
            )
            lines.append(f"neuralclear_http_requests_total{{{labels}}} {requests[(method, route, status, tenant_id)]}")
        lines.extend(
            [
                "# HELP neuralclear_auth_failures_total Rejected authentications. The reason is missing or invalid.",
                "# TYPE neuralclear_auth_failures_total counter",
            ]
        )
        for reason in ("missing", "invalid"):
            lines.append(
                f'neuralclear_auth_failures_total{{reason="{reason}"}} {auth.get(reason, 0)}'
            )
        lines.extend(
            [
                "# HELP neuralclear_http_request_duration_seconds Latency by method and route template.",
                "# TYPE neuralclear_http_request_duration_seconds histogram",
            ]
        )
        for method, route in sorted(counts):
            for bound in BUCKETS:
                label = _le(bound)
                value = buckets.get((method, route, label), 0)
                lines.append(
                    "neuralclear_http_request_duration_seconds_bucket{"
                    f'method="{_escape(method)}",route="{_escape(route)}",le="{label}"'
                    f"}} {value}"
                )
            inf_value = buckets.get((method, route, "+Inf"), 0)
            lines.append(
                "neuralclear_http_request_duration_seconds_bucket{"
                f'method="{_escape(method)}",route="{_escape(route)}",le="+Inf"'
                f"}} {inf_value}"
            )
            lines.append(
                "neuralclear_http_request_duration_seconds_sum{"
                f'method="{_escape(method)}",route="{_escape(route)}"'
                f"}} {sums.get((method, route), 0.0):.6f}"
            )
            lines.append(
                "neuralclear_http_request_duration_seconds_count{"
                f'method="{_escape(method)}",route="{_escape(route)}"'
                f"}} {counts[(method, route)]}"
            )
        return "\n".join(lines) + "\n"
