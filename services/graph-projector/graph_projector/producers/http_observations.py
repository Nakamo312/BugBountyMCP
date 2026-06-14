from __future__ import annotations

from typing import Any, Mapping
from uuid import UUID

from ..contracts import GraphEdgeFact, GraphFactBatch, GraphNodeFact


class HttpObservationGraphFactProducer:
    def __init__(self, *, parser_version: str = "http-observations.v1") -> None:
        self._parser_version = parser_version

    @property
    def parser_version(self) -> str:
        return self._parser_version

    def produce(self, rows: list[Mapping[str, Any]]) -> GraphFactBatch | None:
        facts = []
        seen_identity_keys: set[str] = set()
        batch_program_id: UUID | None = None

        for row in rows:
            run_id = _optional_uuid(row.get("run_id"))
            raw_artifact_id = _optional_uuid(row.get("raw_artifact_id"))
            if run_id is None or raw_artifact_id is None:
                continue

            program_id = _required_uuid(row, "program_id")
            if batch_program_id is None:
                batch_program_id = program_id
            elif batch_program_id != program_id:
                raise ValueError("http observation batch cannot mix program_id values")

            hostname = _required_text(row, "hostname").lower()
            ip_address = _required_text(row, "ip_address")
            scheme = _required_text(row, "scheme").lower()
            port = _required_int(row, "port")
            method = _required_text(row, "method").upper()
            normalized_path = _required_text(row, "normalized_path")
            svc_key = service_key(hostname=hostname, port=port, scheme=scheme)
            endpoint_key = service_method_normalized_path_key(
                service_key=svc_key,
                method=method,
                normalized_path=normalized_path,
            )
            lineage = {
                "program_id": program_id,
                "producer": "httpx",
                "source_artifact_id": raw_artifact_id,
                "tool_run_id": run_id,
                "confidence": 1.0,
            }
            candidates = [
                GraphNodeFact(
                    **lineage,
                    kind="Host",
                    key=hostname,
                    properties={"hostname": hostname},
                ),
                GraphNodeFact(
                    **lineage,
                    kind="IP",
                    key=ip_address,
                    properties={"address": ip_address},
                ),
                GraphNodeFact(
                    **lineage,
                    kind="Service",
                    key=svc_key,
                    properties={
                        "service_key": svc_key,
                        "port": port,
                        "scheme": scheme,
                    },
                ),
                GraphNodeFact(
                    **lineage,
                    kind="Endpoint",
                    key=endpoint_key,
                    properties={
                        "service_method_normalized_path": endpoint_key,
                        "service_key": svc_key,
                        "method": method,
                        "normalized_path": normalized_path,
                        "status_code": _optional_int(row.get("status_code")),
                        "content_type": _optional_text(row.get("content_type")),
                        "url": _optional_text(row.get("url")),
                    },
                ),
                GraphEdgeFact(
                    **lineage,
                    src_kind="Host",
                    src_key=hostname,
                    edge_kind="RESOLVES_TO",
                    dst_kind="IP",
                    dst_key=ip_address,
                ),
                GraphEdgeFact(
                    **lineage,
                    src_kind="IP",
                    src_key=ip_address,
                    edge_kind="EXPOSES_SERVICE",
                    dst_kind="Service",
                    dst_key=svc_key,
                ),
                GraphEdgeFact(
                    **lineage,
                    src_kind="Service",
                    src_key=svc_key,
                    edge_kind="HAS_ENDPOINT",
                    dst_kind="Endpoint",
                    dst_key=endpoint_key,
                ),
            ]
            for fact in candidates:
                if fact.identity_key in seen_identity_keys:
                    continue
                seen_identity_keys.add(fact.identity_key)
                facts.append(fact)

        if batch_program_id is None or not facts:
            return None
        return GraphFactBatch(
            program_id=batch_program_id,
            facts=facts,
            produced_by="httpx-observation-producer",
            parser_version=self._parser_version,
        )


def service_key(*, hostname: str, port: int, scheme: str) -> str:
    return f"{hostname.strip().lower()}:{int(port)}/{scheme.strip().lower()}"


def service_method_normalized_path_key(*, service_key: str, method: str, normalized_path: str) -> str:
    return f"{service_key.strip()}:{method.strip().upper()}:{normalized_path.strip()}"


def http_observations_dedupe_key(raw_artifact_id: UUID | str, parser_version: str) -> str:
    return f"http-observations:{raw_artifact_id}:{parser_version}"


def _required_uuid(row: Mapping[str, Any], key: str) -> UUID:
    value = _optional_uuid(row.get(key))
    if value is None:
        raise ValueError(f"http observation row requires {key}")
    return value


def _optional_uuid(value: Any) -> UUID | None:
    if value is None:
        return None
    if isinstance(value, UUID):
        return value
    return UUID(str(value))


def _required_text(row: Mapping[str, Any], key: str) -> str:
    text = _optional_text(row.get(key))
    if text is None:
        raise ValueError(f"http observation row requires non-empty {key}")
    return text


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _required_int(row: Mapping[str, Any], key: str) -> int:
    if row.get(key) is None:
        raise ValueError(f"http observation row requires {key}")
    return int(row[key])


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)
