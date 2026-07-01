"""HTTP capture helpers for the Playwright crawler."""
from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any
from urllib.parse import parse_qs, urlparse

from crawler.static_resources import STATIC_EXTENSIONS


def is_static_resource(url: str) -> bool:
    """Return whether the URL points at a static asset."""
    lower_url = url.lower().split("?", 1)[0]
    return any(lower_url.endswith(ext) for ext in STATIC_EXTENSIONS)


def is_same_origin(start_url: str, url: str) -> bool:
    """Return whether a captured URL belongs to the scanner origin."""
    return urlparse(start_url).netloc == urlparse(url).netloc


def make_request_key(method: str, url: str, body: str | None = None) -> str:
    """Create a normalized key for request deduplication."""
    parsed = urlparse(url)
    normalized_path = parsed.path or "/"
    query_sig = ",".join(sorted(parse_qs(parsed.query).keys())) if parsed.query else ""

    body_schema = ""
    if body:
        try:
            body_obj = json.loads(body)
        except json.JSONDecodeError:
            body_schema = str(hash(body))[:8]
        else:
            if isinstance(body_obj, dict):
                body_schema = ",".join(sorted(body_obj.keys()))

    return f"{method}:{normalized_path}:{query_sig}:{body_schema}"


def build_raw_request(
    *,
    method: str,
    url: str,
    headers: Mapping[str, str],
    post_data: str | None = None,
) -> str:
    """Build a raw-ish HTTP request representation for scanner output."""
    parsed = urlparse(url)
    target = parsed.path or "/"
    if parsed.query:
        target = f"{target}?{parsed.query}"

    raw = f"{method} {target} HTTP/1.1\r\n"
    for key, value in headers.items():
        raw += f"{key}: {value}\r\n"
    raw += "\r\n"

    if post_data:
        raw += post_data
    return raw


def build_request_capture(
    *,
    method: str,
    url: str,
    headers: Mapping[str, str],
    resource_type: str,
    post_data: str | None = None,
) -> dict[str, Any]:
    """Build the request half of a scanner result object."""
    request: dict[str, Any] = {
        "method": method,
        "endpoint": url,
        "headers": dict(headers),
        "resource_type": resource_type,
        "raw": build_raw_request(method=method, url=url, headers=headers, post_data=post_data),
    }
    if method in {"POST", "PUT", "PATCH"} and post_data:
        request["body"] = post_data
    return {"request": request}


def extract_json_keys(data: str) -> set[str]:
    """Extract top-level and one-level nested JSON object keys."""
    try:
        obj = json.loads(data)
    except json.JSONDecodeError:
        return set()

    if not isinstance(obj, dict):
        return set()

    keys = set(obj.keys())
    for value in obj.values():
        if isinstance(value, dict):
            keys.update(value.keys())
    return keys


def extract_graphql_operation(data: str, content_type: str, url: str) -> str | None:
    """Extract a coarse GraphQL operation marker from a body."""
    if "graphql" in url.lower() or "application/graphql" in content_type.lower():
        return "graphql_raw"

    if "application/json" not in content_type.lower():
        return None

    try:
        obj = json.loads(data)
    except json.JSONDecodeError:
        return None

    if isinstance(obj, list):
        if any("query" in item or "mutation" in item for item in obj if isinstance(item, dict)):
            return "graphql_batch"
        return None

    if isinstance(obj, dict):
        if "query" in obj or "mutation" in obj:
            return obj.get("operationName", "anonymous")
        if "id" in obj and "variables" in obj:
            return "graphql_persisted"
    return None


def endpoint_label(method: str, url: str) -> str:
    """Return the method/path label used by scanner uniqueness counters."""
    parsed = urlparse(url)
    return f"{method} {parsed.path}"
