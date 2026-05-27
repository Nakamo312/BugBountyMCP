"""Small OpenSearch HTTP client used by the standalone indexer."""
from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from typing import Any

import requests


def build_bulk_payload(index_name: str, documents: Iterable[Mapping[str, Any]]) -> str:
    lines: list[str] = []
    for document in documents:
        document_id = document.get("id")
        if not document_id:
            raise ValueError("OpenSearch documents must contain a non-empty id field")
        lines.append(
            json.dumps(
                {"index": {"_index": index_name, "_id": str(document_id)}},
                separators=(",", ":"),
            )
        )
        lines.append(json.dumps(dict(document), separators=(",", ":"), default=str))
    return "\n".join(lines) + ("\n" if lines else "")


class OpenSearchClient:
    def __init__(
        self,
        base_url: str,
        *,
        timeout_seconds: float = 30.0,
        username: str | None = None,
        password: str | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.auth = (username, password) if username and password else None

    def bulk_index(self, index_name: str, documents: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
        payload = build_bulk_payload(index_name, documents)
        if not payload:
            return {"errors": False, "items": []}

        response = requests.post(
            f"{self.base_url}/_bulk",
            data=payload,
            headers={"Content-Type": "application/x-ndjson"},
            timeout=self.timeout_seconds,
            auth=self.auth,
        )
        response.raise_for_status()
        result = response.json()
        if result.get("errors"):
            raise RuntimeError(f"OpenSearch bulk index reported item errors: {result}")
        return result

    def ensure_index(self, index_name: str, mapping: Mapping[str, Any]) -> None:
        response = requests.put(
            f"{self.base_url}/{index_name}",
            json=mapping,
            timeout=self.timeout_seconds,
            auth=self.auth,
        )
        if response.status_code not in {200, 201, 400}:
            response.raise_for_status()
        if response.status_code == 400 and "resource_already_exists_exception" not in response.text:
            response.raise_for_status()

