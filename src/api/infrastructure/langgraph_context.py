"""Infrastructure adapters for LangGraph read-only context tools."""
from __future__ import annotations

from pathlib import Path
import asyncio
import sys
from typing import Any, Mapping
from uuid import UUID

import requests

from api.config import Settings
from api.infrastructure.artifacts.postgres_reader import PostgresArtifactReader


class ArtifactProgramContextAdapter:
    def __init__(self, reader: PostgresArtifactReader) -> None:
        self.reader = reader

    async def list_hosts(self, *, program_id: UUID, limit: int) -> list[Any]:
        return await self.reader.list_hosts(program_id=program_id, limit=limit)

    async def list_services(self, *, program_id: UUID, limit: int) -> list[Any]:
        return await self.reader.list_services(program_id=program_id, limit=limit)

    async def list_endpoints(self, *, program_id: UUID, limit: int) -> list[Any]:
        return await self.reader.list_endpoints(program_id=program_id, limit=limit)


class ArtifactPreviewAdapter:
    def __init__(self, reader: PostgresArtifactReader) -> None:
        self.reader = reader

    async def list_bodies(self, **kwargs) -> list[Any]:
        if kwargs.get("endpoint_id") is None and kwargs.get("body_hash") is None:
            return await self.reader.list_artifact_previews(
                program_id=kwargs["program_id"],
                limit=kwargs.get("limit"),
            )
        return await self.reader.list_bodies(**kwargs)


class SafeGraphTemplateRenderer:
    def __init__(self, registry=None) -> None:
        self.registry = registry or self._default_registry()

    def render(
        self,
        *,
        template_name: str,
        parameters: Mapping[str, Any],
    ) -> dict[str, Any]:
        rendered = self.registry.get(template_name).render(parameters)
        return {
            "template_name": template_name,
            "cypher": rendered.cypher,
            "parameters": dict(rendered.parameters),
        }

    @staticmethod
    def _default_registry():
        graph_projector_path = Path("services/graph-projector").resolve()
        graph_projector_path_text = str(graph_projector_path)
        if graph_projector_path_text not in sys.path:
            sys.path.insert(0, graph_projector_path_text)

        from graph_projector.query_templates import default_query_template_registry

        return default_query_template_registry()


class OpenSearchSanitizedSearchReader:
    def __init__(self, settings: Settings) -> None:
        self.base_url = settings.OPENSEARCH_URL.rstrip("/")
        self.timeout_seconds = settings.OPENSEARCH_TIMEOUT_SECONDS
        self.auth = (
            (settings.OPENSEARCH_USERNAME, settings.OPENSEARCH_PASSWORD)
            if settings.OPENSEARCH_USERNAME and settings.OPENSEARCH_PASSWORD
            else None
        )
        self.verify_certs = settings.OPENSEARCH_VERIFY_CERTS

    async def search(
        self,
        *,
        program_id: UUID,
        index: str,
        query: str,
        limit: int,
    ) -> dict[str, Any]:
        return await asyncio.to_thread(
            self._search_sync,
            program_id=program_id,
            index=index,
            query=query,
            limit=limit,
        )

    async def search_hypotheses(
        self,
        *,
        program_id: UUID,
        status: str | None,
        hypothesis_type: str | None,
        min_priority_score: int,
        limit: int,
    ) -> dict[str, Any]:
        return await asyncio.to_thread(
            self._search_hypotheses_sync,
            program_id=program_id,
            status=status,
            hypothesis_type=hypothesis_type,
            min_priority_score=min_priority_score,
            limit=limit,
        )

    def _search_sync(
        self,
        *,
        program_id: UUID,
        index: str,
        query: str,
        limit: int,
    ) -> dict[str, Any]:
        request = {
            "size": max(1, min(int(limit), 100)),
            "query": {
                "bool": {
                    "filter": [{"term": {"program_id": str(program_id)}}],
                    "must": [
                        {
                            "simple_query_string": {
                                "query": query or "*",
                                "fields": ["*"],
                                "default_operator": "and",
                            }
                        }
                    ],
                }
            },
        }
        response = requests.post(
            f"{self.base_url}/{index}/_search",
            json=request,
            timeout=self.timeout_seconds,
            auth=self.auth,
            verify=self.verify_certs,
        )
        response.raise_for_status()
        payload = response.json()
        hits = [
            {
                **(hit.get("_source") or {}),
                "_id": hit.get("_id"),
                "_score": hit.get("_score"),
            }
            for hit in payload.get("hits", {}).get("hits", [])
        ]
        return {
            "index": index,
            "program_id": str(program_id),
            "hits": hits,
        }

    def _search_hypotheses_sync(
        self,
        *,
        program_id: UUID,
        status: str | None,
        hypothesis_type: str | None,
        min_priority_score: int,
        limit: int,
    ) -> dict[str, Any]:
        filters: list[dict[str, Any]] = [
            {"term": {"program_id": str(program_id)}},
            {"range": {"priority_score": {"gte": int(min_priority_score)}}},
        ]
        if status:
            filters.append({"term": {"status": status}})
        if hypothesis_type:
            filters.append({"term": {"hypothesis_type": hypothesis_type}})
        request = {
            "size": max(1, min(int(limit), 100)),
            "_source": {
                "includes": [
                    "hypothesis_id",
                    "program_id",
                    "hypothesis_type",
                    "status",
                    "priority_score",
                    "confidence",
                    "severity_guess",
                    "safety_level",
                    "score_version",
                    "source_signal_fingerprints",
                    "evidence_count",
                    "evidence_ref_types",
                    "evidence_roles",
                    "evidence_claim_types",
                    "evidence_ref_ids",
                    "safe_evidence_text",
                    "last_seen",
                    "updated_at",
                ]
            },
            "query": {"bool": {"filter": filters}},
            "sort": [
                {"priority_score": {"order": "desc"}},
                {"last_seen": {"order": "desc", "missing": "_last"}},
                {"hypothesis_id": {"order": "asc"}},
            ],
        }
        response = requests.post(
            f"{self.base_url}/bb-research-hypotheses/_search",
            json=request,
            timeout=self.timeout_seconds,
            auth=self.auth,
            verify=self.verify_certs,
        )
        response.raise_for_status()
        payload = response.json()
        hits = [
            {
                **(hit.get("_source") or {}),
                "_id": hit.get("_id"),
                "_score": hit.get("_score"),
            }
            for hit in payload.get("hits", {}).get("hits", [])
        ]
        return {
            "index": "bb-research-hypotheses",
            "program_id": str(program_id),
            "hits": hits,
        }
