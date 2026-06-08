"""Prometheus metrics endpoint and lightweight HTTP instrumentation."""
from __future__ import annotations

import time
from collections.abc import Callable
import logging

from fastapi import FastAPI, Request, Response
from sqlalchemy.ext.asyncio import async_sessionmaker

from api.infrastructure.orchestration.metrics import PipelineMetricsCollector

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

logger = logging.getLogger(__name__)


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
        body = generate_latest()
        body += (await _collect_pipeline_metrics(app)).encode("utf-8")
        return Response(body, media_type=CONTENT_TYPE_LATEST)


async def _collect_pipeline_metrics(app: FastAPI) -> str:
    container = getattr(app.state, "dishka_container", None)
    if container is None:
        return PipelineMetricsCollector.unavailable_sample()
    try:
        session_factory = await container.get(async_sessionmaker)
        return await PipelineMetricsCollector(session_factory).collect()
    except Exception:
        logger.exception("Failed to collect pipeline metrics")
        return PipelineMetricsCollector.unavailable_sample()
