"""HTTP request/response capture for the Playwright crawler."""
from __future__ import annotations

import asyncio
import json
from collections.abc import Iterable
from typing import Any
from urllib.parse import urlparse

from crawler.http_capture import (
    build_request_capture,
    endpoint_label,
    extract_graphql_operation,
    extract_json_keys,
    is_same_origin,
    is_static_resource,
    make_request_key,
)
from crawler.scanner_logging import logger


class NetworkCapture:
    """Track same-origin non-static HTTP observations emitted by Playwright."""

    def __init__(
        self,
        *,
        start_url: str,
        response_body_errors: Iterable[type[BaseException]] = (),
    ) -> None:
        self.start_url = start_url
        self.response_body_errors = tuple(response_body_errors)
        self.results: list[dict[str, Any]] = []
        self.pending_requests: dict[str, dict[str, Any]] = {}
        self.seen_requests: set[str] = set()
        self.unique_endpoints: set[str] = set()
        self.unique_methods_paths: set[str] = set()
        self.unique_json_keys: set[str] = set()
        self.unique_graphql_ops: set[str] = set()
        self.request_count = 0

    def should_capture(self, url: str, resource_type: str) -> bool:
        if is_static_resource(url):
            return False
        if resource_type in {"beacon", "ping"}:
            return False
        return is_same_origin(self.start_url, url)

    def log_request(self, request: Any) -> None:
        if self.should_capture(request.url, request.resource_type):
            logger.info(f"Request: {request.method} {request.url}")

    async def intercept_request(self, route: Any) -> None:
        """Intercept and stage request metadata until the response arrives."""
        request = route.request
        if not self.should_capture(request.url, request.resource_type):
            await route.continue_()
            return

        result = build_request_capture(
            method=request.method,
            url=request.url,
            headers=request.headers,
            resource_type=request.resource_type,
            post_data=request.post_data,
        )
        key = make_request_key(request.method, request.url, request.post_data)

        if key not in self.seen_requests:
            self.seen_requests.add(key)
            self.pending_requests[key] = result

            parsed = urlparse(request.url)
            body_hint = f"[body: {len(request.post_data)} bytes]" if request.post_data else ""
            logger.info(f"Captured: {request.method} {parsed.path} {body_hint}")

        await route.continue_()

    async def handle_response(self, response: Any) -> None:
        """Combine response metadata with a previously staged request."""
        request = response.request
        key = make_request_key(request.method, request.url, request.post_data)
        result = self.pending_requests.pop(key, None)
        if result is None:
            return

        result["response"] = {
            "status_code": response.status,
            "headers": dict(response.headers),
        }
        result["timestamp"] = asyncio.get_event_loop().time()

        self.results.append(result)
        self.request_count += 1
        self.unique_endpoints.add(request.url)
        self.unique_methods_paths.add(endpoint_label(request.method, request.url))
        self._record_request_body_observations(request)
        await self._record_response_body_observations(response, request.url)

        logger.info(f"Found: {request.method} {request.url} -> {response.status}")
        print(json.dumps(result), flush=True)

    def _record_request_body_observations(self, request: Any) -> None:
        post_data = request.post_data
        if not post_data:
            return
        self.unique_json_keys.update(extract_json_keys(post_data))

        content_type = request.headers.get("content-type", "")
        graphql_op = extract_graphql_operation(post_data, content_type, request.url)
        if graphql_op:
            self.unique_graphql_ops.add(graphql_op)

        try:
            body_obj = json.loads(post_data)
        except json.JSONDecodeError:
            return
        if isinstance(body_obj, dict):
            body_schema = ",".join(sorted(body_obj.keys()))
            logger.info(f"POST body schema: {body_schema}")

    async def _record_response_body_observations(self, response: Any, url: str) -> None:
        try:
            body = await response.text()
        except self.response_body_errors as exc:  # type: ignore[misc]
            logger.debug(f"Failed to read response body for {url}: {exc}")
            return
        self.unique_json_keys.update(extract_json_keys(body))
