"""Read-only context tools for LangGraph workflows.

These tools are a narrow facade over existing read models. They enforce program
boundaries and expose sanitized pointers/previews only; they do not run tools,
publish transport events, or return raw artifact bodies.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any, Protocol
from uuid import UUID

from api.application.hypothesis_selection import HypothesisSelectionPolicy


class ProgramBoundaryError(ValueError):
    pass


class RawArtifactAccessDenied(PermissionError):
    pass


class InvalidHypothesisSearch(ValueError):
    pass


HYPOTHESIS_SEARCH_INDEX = "bb-research-hypotheses"
HYPOTHESIS_STATUSES = frozenset({
    "new",
    "needs_verification",
    "reviewing",
    "dismissed",
    "duplicate",
    "promoted",
    "stale",
})
HYPOTHESIS_RESULT_FIELDS = frozenset({
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
})


class ProgramContextReader(Protocol):
    async def list_hosts(self, *, program_id: UUID, limit: int) -> list[Any]: ...

    async def list_services(self, *, program_id: UUID, limit: int) -> list[Any]: ...

    async def list_endpoints(self, *, program_id: UUID, limit: int) -> list[Any]: ...


class ResultSetReader(Protocol):
    async def list_result_sets(self, **kwargs) -> list[dict[str, Any]]: ...


class ArtifactPreviewReader(Protocol):
    async def list_bodies(self, **kwargs) -> list[Any]: ...


class SearchReader(Protocol):
    async def search(
        self,
        *,
        program_id: UUID,
        index: str,
        query: str,
        limit: int,
    ) -> dict[str, Any]: ...

    async def search_hypotheses(
        self,
        *,
        program_id: UUID,
        status: str | None,
        hypothesis_type: str | None,
        min_priority_score: int,
        limit: int,
    ) -> dict[str, Any]: ...


class GraphTemplateRenderer(Protocol):
    def render(
        self,
        *,
        template_name: str,
        parameters: Mapping[str, Any],
    ) -> dict[str, Any]: ...


class LangGraphContextTools:
    def __init__(
        self,
        *,
        program_reader: ProgramContextReader,
        result_set_reader: ResultSetReader,
        artifact_preview_reader: ArtifactPreviewReader,
        search_reader: SearchReader,
        graph_renderer: GraphTemplateRenderer,
    ) -> None:
        self.program_reader = program_reader
        self.result_set_reader = result_set_reader
        self.artifact_preview_reader = artifact_preview_reader
        self.search_reader = search_reader
        self.graph_renderer = graph_renderer

    async def program_context(self, *, program_id: UUID, limit: int = 25) -> dict[str, Any]:
        bounded_limit = self._limit(limit)
        hosts = self._normalize_rows(
            await self.program_reader.list_hosts(program_id=program_id, limit=bounded_limit)
        )
        services = self._normalize_rows(
            await self.program_reader.list_services(program_id=program_id, limit=bounded_limit)
        )
        endpoints = self._normalize_rows(
            await self.program_reader.list_endpoints(program_id=program_id, limit=bounded_limit)
        )
        self._ensure_program_boundary(program_id, hosts + services + endpoints)
        return {
            "program_id": str(program_id),
            "hosts": self._strip_raw_fields(hosts),
            "services": self._strip_raw_fields(services),
            "endpoints": self._strip_raw_fields(endpoints),
        }

    async def result_sets(
        self,
        *,
        program_id: UUID,
        result_key: str | None = None,
        action_id: UUID | None = None,
        campaign_id: UUID | None = None,
        workflow_id: UUID | None = None,
        workflow_run_id: UUID | None = None,
        limit: int = 25,
    ) -> dict[str, Any]:
        rows = await self.result_set_reader.list_result_sets(
            program_id=program_id,
            result_key=result_key,
            action_id=action_id,
            campaign_id=campaign_id,
            workflow_id=workflow_id,
            workflow_run_id=workflow_run_id,
            limit=self._limit(limit),
        )
        items = self._normalize_rows(rows)
        self._ensure_program_boundary(program_id, items)
        return {"program_id": str(program_id), "items": self._strip_raw_fields(items)}

    async def opensearch_search(
        self,
        *,
        program_id: UUID,
        index: str,
        query: str,
        limit: int = 25,
    ) -> dict[str, Any]:
        result = await self.search_reader.search(
            program_id=program_id,
            index=index,
            query=query,
            limit=self._limit(limit),
        )
        hits = self._normalize_rows(result.get("hits", []))
        self._ensure_program_boundary(program_id, hits)
        return {
            **result,
            "hits": self._strip_raw_fields(hits),
        }


    async def search_hypotheses(
        self,
        *,
        program_id: UUID,
        status: str | Iterable[str] | None = None,
        hypothesis_type: str | None = None,
        min_priority_score: int = 0,
        limit: int = 25,
    ) -> dict[str, Any]:
        statuses = self._normalize_hypothesis_status(status)
        priority = self._priority_score(min_priority_score)
        result = await self.search_reader.search_hypotheses(
            program_id=program_id,
            status=statuses[0] if len(statuses) == 1 else None,
            hypothesis_type=self._safe_optional_text(hypothesis_type, field_name="hypothesis_type"),
            min_priority_score=priority,
            limit=self._limit(limit),
        )
        hits = self._normalize_rows(result.get("hits", []))
        if len(statuses) > 1:
            hits = [hit for hit in hits if str(hit.get("status")) in statuses]
        self._ensure_program_boundary(program_id, hits)
        safe_hits = [
            self._project_hypothesis_search_hit(hit)
            for hit in self._strip_raw_fields(hits)
        ]
        return {
            "index": HYPOTHESIS_SEARCH_INDEX,
            "program_id": str(program_id),
            "status": statuses if statuses else None,
            "hypothesis_type": hypothesis_type,
            "min_priority_score": priority,
            "hits": safe_hits,
        }

    async def select_hypotheses(
        self,
        *,
        program_id: UUID,
        status: str | Iterable[str] | None = ("new", "needs_verification", "reviewing", "stale"),
        hypothesis_type: str | None = None,
        min_priority_score: int = 0,
        limit: int = 25,
    ) -> dict[str, Any]:
        search_result = await self.search_hypotheses(
            program_id=program_id,
            status=status,
            hypothesis_type=hypothesis_type,
            min_priority_score=min_priority_score,
            limit=limit,
        )
        policy = HypothesisSelectionPolicy(max_items=self._limit(limit))
        selection = policy.select(search_result.get("hits", ()))
        return {
            "program_id": str(program_id),
            "source_index": HYPOTHESIS_SEARCH_INDEX,
            "decisions": [
                {
                    "hypothesis_id": item.hypothesis_id,
                    "next_step": item.next_step,
                    "priority_band": item.priority_band,
                    "reasons": list(item.reasons),
                    "requires_human_review": item.requires_human_review,
                    "safe_context": item.safe_context,
                }
                for item in selection.decisions
            ],
        }

    async def graph_template_query(
        self,
        *,
        program_id: UUID,
        template_name: str,
        parameters: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        safe_parameters = dict(parameters or {})
        safe_parameters["program_id"] = str(program_id)
        if "limit" in safe_parameters:
            safe_parameters["limit"] = self._limit(int(safe_parameters["limit"]))
        rendered = self.graph_renderer.render(
            template_name=template_name,
            parameters=safe_parameters,
        )
        rendered_parameters = dict(rendered.get("parameters") or {})
        rendered_parameters["program_id"] = str(program_id)
        if "limit" in rendered_parameters:
            rendered_parameters["limit"] = self._limit(int(rendered_parameters["limit"]))
        return {
            **rendered,
            "parameters": rendered_parameters,
        }

    async def artifact_previews(
        self,
        *,
        program_id: UUID,
        endpoint_id: UUID | None = None,
        body_hash: str | None = None,
        limit: int = 25,
    ) -> dict[str, Any]:
        rows = await self.artifact_preview_reader.list_bodies(
            program_id=program_id,
            endpoint_id=endpoint_id,
            body_hash=body_hash,
            limit=self._limit(limit),
        )
        items = self._normalize_rows(rows)
        self._ensure_program_boundary(program_id, items)
        return {"program_id": str(program_id), "items": self._strip_raw_fields(items)}

    async def raw_artifact(self, *, artifact_id: UUID) -> None:
        raise RawArtifactAccessDenied(
            f"raw artifact access requires explicit workflow policy: {artifact_id}"
        )

    @staticmethod
    def _limit(value: int) -> int:
        return max(1, min(int(value), 100))

    @staticmethod
    def _priority_score(value: int | float) -> int:
        score = int(value)
        if score < 0 or score > 100:
            raise InvalidHypothesisSearch("min_priority_score must be between 0 and 100")
        return score

    @staticmethod
    def _safe_optional_text(value: str | None, *, field_name: str) -> str | None:
        if value is None:
            return None
        text = value.strip()
        if not text:
            return None
        if len(text) > 100:
            raise InvalidHypothesisSearch(f"{field_name} is too long")
        allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_:-.")
        if any(char not in allowed for char in text):
            raise InvalidHypothesisSearch(f"{field_name} contains unsupported characters")
        return text

    @classmethod
    def _normalize_hypothesis_status(cls, status: str | Iterable[str] | None) -> list[str]:
        if status is None:
            return []
        if isinstance(status, str):
            values = [status]
        else:
            values = list(status)
        normalized: list[str] = []
        for item in values:
            text = str(item).strip()
            if not text:
                continue
            if text not in HYPOTHESIS_STATUSES:
                raise InvalidHypothesisSearch(f"unsupported hypothesis status: {text}")
            if text not in normalized:
                normalized.append(text)
        return normalized

    @staticmethod
    def _project_hypothesis_search_hit(row: dict[str, Any]) -> dict[str, Any]:
        return {
            key: row[key]
            for key in HYPOTHESIS_RESULT_FIELDS
            if key in row
        }

    @classmethod
    def _normalize_rows(cls, rows: list[Any]) -> list[dict[str, Any]]:
        return [cls._normalize_value(row) for row in rows]

    @classmethod
    def _normalize_value(cls, value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return cls._stringify_ids(dict(value))
        if hasattr(value, "model_dump"):
            return cls._stringify_ids(value.model_dump(mode="json"))
        if hasattr(value, "__dict__"):
            return cls._stringify_ids(dict(value.__dict__))
        return cls._stringify_ids(dict(value))

    @staticmethod
    def _stringify_ids(row: dict[str, Any]) -> dict[str, Any]:
        return {
            key: str(value) if isinstance(value, UUID) else value
            for key, value in row.items()
        }

    @classmethod
    def _strip_raw_fields(cls, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        forbidden = {
            "body_content",
            "raw_content",
            "raw_body",
            "preview",
            "headers",
            "cookies",
            "authorization",
            "secret",
            "token",
        }
        return [
            {key: value for key, value in row.items() if key.lower() not in forbidden}
            for row in rows
        ]

    @staticmethod
    def _ensure_program_boundary(program_id: UUID, rows: list[dict[str, Any]]) -> None:
        expected = str(program_id)
        for row in rows:
            row_program_id = row.get("program_id")
            if row_program_id is not None and str(row_program_id) != expected:
                raise ProgramBoundaryError(
                    f"row belongs to another program: {row_program_id}"
                )
