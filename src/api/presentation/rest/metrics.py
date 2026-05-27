"""Prometheus metrics endpoint and lightweight HTTP instrumentation."""
from __future__ import annotations

import time
from collections.abc import Callable

from fastapi import FastAPI, Request, Response

try:
    from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
except ImportError:  # pragma: no cover - exercised in environments without optional dependency.
    CONTENT_TYPE_LATEST = "text/plain; version=0.0.4; charset=utf-8"
    Counter = None
    Histogram = None
    generate_latest = None


if Counter is not None and Histogram is not None:
    REQUEST_COUNT = Counter(
        "http_requests_total",
        "Total HTTP requests handled by the API.",
        ["method", "path", "status"],
    )
    REQUEST_DURATION = Histogram(
        "http_request_duration_seconds",
        "HTTP request duration in seconds.",
        ["method", "path"],
    )
else:
    REQUEST_COUNT = None
    REQUEST_DURATION = None


def setup_metrics(app: FastAPI) -> None:
    """Register /metrics and HTTP request instrumentation."""

    if REQUEST_COUNT is not None and REQUEST_DURATION is not None:

        @app.middleware("http")
        async def prometheus_http_metrics(request: Request, call_next: Callable):
            route = request.scope.get("route")
            path = getattr(route, "path", request.url.path)
            start = time.perf_counter()
            response = await call_next(request)
            elapsed = time.perf_counter() - start
            REQUEST_COUNT.labels(request.method, path, str(response.status_code)).inc()
            REQUEST_DURATION.labels(request.method, path).observe(elapsed)
            return response

    @app.get("/metrics", include_in_schema=False)
    async def metrics() -> Response:
        if generate_latest is None:
            return Response(
                "# HELP prometheus_client_available Whether prometheus_client is installed.\n"
                "# TYPE prometheus_client_available gauge\n"
                "prometheus_client_available 0\n",
                media_type=CONTENT_TYPE_LATEST,
            )
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
