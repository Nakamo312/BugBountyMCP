from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit
from uuid import UUID

from .http_observation_projection import canonical_hostname


def js_file_key(url: str) -> str:
    return canonical_url_without_query(url)


def javascript_reference_dedupe_key(raw_artifact_id: UUID | str, parser_version: str) -> str:
    return f"javascript-references:{raw_artifact_id}:{parser_version}"


def canonical_url_without_query(url: str) -> str:
    parsed = urlsplit(url.strip())
    scheme = (parsed.scheme or "https").lower()
    hostname = canonical_hostname(parsed.hostname or "")
    netloc = hostname
    if parsed.port is not None:
        netloc = f"{hostname}:{parsed.port}"
    path = parsed.path or "/"
    return urlunsplit((scheme, netloc, path, "", ""))
