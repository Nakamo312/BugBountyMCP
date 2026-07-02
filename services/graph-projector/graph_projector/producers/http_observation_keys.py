from __future__ import annotations

from uuid import UUID

from .http_observation_projection import canonical_hostname


def service_key(*, hostname: str, port: int, scheme: str) -> str:
    return f"{canonical_hostname(hostname)}:{int(port)}/{scheme.strip().lower()}"


def service_method_normalized_path_key(*, service_key: str, method: str, normalized_path: str) -> str:
    return f"{service_key.strip()}:{method.strip().upper()}:{normalized_path.strip()}"


def parameter_key(*, endpoint_key: str, location: str, name: str) -> str:
    return f"{endpoint_key.strip()}:{location.strip().lower()}:{name.strip()}"


def request_shape_key(*, endpoint_key: str, method: str, path_params: tuple[str, ...], query_params: tuple[str, ...]) -> str:
    path_part = ",".join(path_params) or "-"
    query_part = ",".join(query_params) or "-"
    return f"{endpoint_key.strip()}:request:{method.strip().upper()}:path={path_part}:query={query_part}"


def http_observations_dedupe_key(raw_artifact_id: UUID | str, parser_version: str) -> str:
    return f"http-observations:{raw_artifact_id}:{parser_version}"
