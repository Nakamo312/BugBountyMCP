from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit, urlunsplit

from research_engine.contracts import EvidencePack, EvidenceRef, PackSafety, Subject
from research_engine.features import extract_safe_features


def build_observation_pack(row: dict[str, Any]) -> EvidencePack:
    if row.get("safe_for_llm") is not True:
        raise ValueError("HTTP observation row is not safe for LLM")

    program_id = _required_text(row, "program_id")
    endpoint_id = _optional_text(row, "endpoint_id")
    observation_id = _optional_text(row, "observation_id") or _required_text(row, "id")
    pack_id = f"http-observation:{program_id}:{endpoint_id or 'none'}:{observation_id}"

    headers = _headers(row.get("headers"))
    query_params = _query_params(row.get("query_params"))
    body_preview_safe = _optional_text(row, "body_preview_safe")

    safe_features = extract_safe_features(
        path=_optional_text(row, "path"),
        title=_optional_text(row, "title"),
        content_type=_optional_text(row, "content_type"),
        headers=headers,
        query_params=query_params,
        body_preview=body_preview_safe,
    )

    evidence_refs = _build_evidence_refs(
        pack_id=pack_id,
        observation_id=observation_id,
        row=row,
        safe_features=safe_features,
    )

    return EvidencePack(
        pack_id=pack_id,
        pack_type="observation",
        program_id=program_id,
        subject=Subject(
            type="http_endpoint",
            id=endpoint_id,
            url=_safe_url(_optional_text(row, "url")),
            method=_optional_text(row, "method"),
            host=_optional_text(row, "host"),
            path=_optional_text(row, "path"),
            status_code=_optional_int(row, "status_code"),
            content_type=_optional_text(row, "content_type"),
            title=_optional_text(row, "title"),
        ),
        safe_features=safe_features,
        evidence_refs=evidence_refs,
        safety=PackSafety(
            safe_for_llm=True,
            safe_for_embedding=True,
            sanitizer_version=_optional_text(row, "sanitizer_version") or "research-sanitizer-v1",
            redaction_policy_version=_optional_text(row, "redaction_policy_version") or "redaction-policy-v1",
        ),
    )


def _build_evidence_refs(
    *,
    pack_id: str,
    observation_id: str,
    row: dict[str, Any],
    safe_features: dict[str, Any],
) -> list[EvidenceRef]:
    refs: list[EvidenceRef] = []

    if row.get("status_code") is not None:
        refs.append(
            _ref(
                pack_id,
                "status",
                observation_id,
                "status_code",
                "status_observed",
                str(row["status_code"]),
            )
        )
    title = _optional_text(row, "title")
    if title:
        refs.append(_ref(pack_id, "title", observation_id, "title", "title_observed", title[:128]))
    if safe_features.get("shape_markers") or safe_features.get("json_keys"):
        body_shape = ",".join(sorted(set(safe_features.get("shape_markers", []) + safe_features.get("json_keys", []))))
        refs.append(_ref(pack_id, "body-shape", observation_id, "body_preview_safe", "body_shape_observed", body_shape))

    for index, param in enumerate(safe_features.get("query_params", [])):
        shape = param["shape"]
        refs.append(
            _ref(
                pack_id,
                f"query-param-{index}",
                observation_id,
                shape.get("field_path") or f"query.{param['name']}",
                shape["claim_type"],
                shape["sample_redacted"],
            )
        )

    return refs


def _ref(
    pack_id: str,
    suffix: str,
    observation_id: str,
    field_path: str,
    claim_type: str,
    safe_excerpt: str | None,
) -> EvidenceRef:
    return EvidenceRef(
        id=f"{pack_id}:ev:{suffix}",
        ref_type="http_observation",
        ref_id=observation_id,
        field_path=field_path,
        claim_type=claim_type,
        role="primary",
        safe_excerpt=safe_excerpt,
        safe_for_llm=True,
        safe_for_search=True,
    )


def _headers(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {str(name).strip().lower(): None for name in value}


def _query_params(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return {str(name): item for name, item in value.items()}
    if isinstance(value, list):
        params: dict[str, Any] = {}
        for item in value:
            if isinstance(item, dict) and "name" in item:
                params[str(item["name"])] = item.get("value", "")
        return params
    return {}


def _safe_url(value: str | None) -> str | None:
    if not value:
        return None
    parts = urlsplit(value)
    if not parts.scheme or not parts.netloc:
        return value.split("?", 1)[0].split("#", 1)[0]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def _required_text(row: dict[str, Any], key: str) -> str:
    value = _optional_text(row, key)
    if not value:
        raise ValueError(f"missing required observation field: {key}")
    return value


def _optional_text(row: dict[str, Any], key: str) -> str | None:
    value = row.get(key)
    if value is None:
        return None
    return str(value)


def _optional_int(row: dict[str, Any], key: str) -> int | None:
    value = row.get(key)
    if value is None:
        return None
    return int(value)
