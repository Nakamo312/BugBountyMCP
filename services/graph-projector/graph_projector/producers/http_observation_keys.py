from __future__ import annotations

import hashlib
from uuid import UUID

from .http_observation_projection import canonical_hostname


def service_key(*, hostname: str, port: int, scheme: str) -> str:
    return f"{canonical_hostname(hostname)}:{int(port)}/{scheme.strip().lower()}"


def service_method_normalized_path_key(*, service_key: str, method: str, normalized_path: str) -> str:
    return f"{service_key.strip()}:{method.strip().upper()}:{normalized_path.strip()}"


def parameter_key(*, endpoint_key: str, location: str, name: str) -> str:
    return f"{endpoint_key.strip()}:{location.strip().lower()}:{name.strip()}"


def request_shape_key(
    *,
    endpoint_key: str,
    method: str,
    path_params: tuple[str, ...],
    query_params: tuple[str, ...],
    other_params: tuple[tuple[str, str], ...] = (),
    body_sha256: str | None = None,
    content_type: str | None = None,
) -> str:
    path_part = ",".join(path_params) or "-"
    query_part = ",".join(query_params) or "-"
    other_part = ",".join(f"{location}:{name}" for location, name in other_params) or "-"
    body_part = body_sha256 or "-"
    content_part = (content_type or "-").strip().lower()
    fingerprint = stable_short_hash(path_part, query_part, other_part, body_part, content_part)
    return f"{endpoint_key.strip()}:request:{method.strip().upper()}:shape={fingerprint}"


def response_shape_key(
    *,
    program_id: UUID | str,
    status_code: int | None,
    content_type: str | None,
    response_family: str,
    schema_fingerprint: str | None = None,
    structural_hash: str | None = None,
    body_size_bucket: str | None = None,
    body_sha256: str | None = None,
    header_key_hash: str | None = None,
) -> str:
    """Return a program-scoped response class key, not a raw response event key."""

    fingerprint = stable_short_hash(
        status_code if status_code is not None else "-",
        (content_type or "-").strip().lower(),
        response_family,
        schema_fingerprint or "-",
        structural_hash or "-",
        body_size_bucket or "-",
        body_sha256 or "-",
        header_key_hash or "-",
    )
    status = status_code if status_code is not None else "none"
    return f"response:{program_id}:{status}:{response_family}:shape={fingerprint}"


def stable_short_hash(*parts: object, length: int = 16) -> str:
    return hashlib.sha256("|".join(str(part) for part in parts).encode("utf-8")).hexdigest()[:length]


def http_observations_dedupe_key(raw_artifact_id: UUID | str, parser_version: str) -> str:
    return f"http-observations:{raw_artifact_id}:{parser_version}"
