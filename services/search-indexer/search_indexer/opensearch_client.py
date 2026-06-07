"""Small OpenSearch HTTP client used by the standalone indexer."""
from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from typing import Any

import requests
from urllib3.exceptions import InsecureRequestWarning


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
        verify_certs: bool = True,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.auth = (username, password) if username and password else None
        self.verify_certs = verify_certs
        if not verify_certs:
            requests.packages.urllib3.disable_warnings(category=InsecureRequestWarning)

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
            verify=self.verify_certs,
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
            verify=self.verify_certs,
        )
        if response.status_code not in {200, 201, 400}:
            response.raise_for_status()
        if response.status_code == 400 and "resource_already_exists_exception" not in response.text:
            response.raise_for_status()

    def ensure_ism_policy(self, policy_id: str, policy: Mapping[str, Any]) -> None:
        existing = requests.get(
            f"{self.base_url}/_plugins/_ism/policies/{policy_id}",
            timeout=self.timeout_seconds,
            auth=self.auth,
            verify=self.verify_certs,
        )
        if existing.status_code == 200:
            return
        if existing.status_code != 404:
            existing.raise_for_status()

        response = requests.put(
            f"{self.base_url}/_plugins/_ism/policies/{policy_id}",
            json=policy,
            timeout=self.timeout_seconds,
            auth=self.auth,
            verify=self.verify_certs,
        )
        response.raise_for_status()

    def apply_ism_policy(self, index_name: str, policy_id: str) -> None:
        response = requests.post(
            f"{self.base_url}/_plugins/_ism/add/{index_name}",
            json={"policy_id": policy_id},
            timeout=self.timeout_seconds,
            auth=self.auth,
            verify=self.verify_certs,
        )
        response.raise_for_status()

    def delete_index(self, index_name: str) -> None:
        response = requests.delete(
            f"{self.base_url}/{index_name}",
            timeout=self.timeout_seconds,
            auth=self.auth,
            verify=self.verify_certs,
        )
        if response.status_code not in {200, 202, 404}:
            response.raise_for_status()
