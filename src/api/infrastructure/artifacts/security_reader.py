"""Finding, leak, event, and raw preview artifact queries."""
from __future__ import annotations

import uuid

from sqlalchemy import select

from api.application.artifact_contracts import (
    EventArtifact,
    FindingArtifact,
    LeakArtifact,
    RawArtifactPreview,
)
from api.infrastructure.adapters.orm import event_store, findings, leaks, raw_artifacts, vuln_types
from api.infrastructure.artifacts.common import ArtifactQueryExecutor, sanitize_leak_row


class SecurityArtifactReader:
    """Read security result artifacts and pipeline event metadata."""

    def __init__(self, executor: ArtifactQueryExecutor):
        self.executor = executor

    async def list_artifact_previews(
        self,
        *,
        program_id: uuid.UUID,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[RawArtifactPreview]:
        query = (
            select(
                raw_artifacts.c.id.label("artifact_id"),
                raw_artifacts.c.program_id,
                raw_artifacts.c.artifact_type,
                raw_artifacts.c.sanitized_preview,
                raw_artifacts.c.sanitizer_version,
                raw_artifacts.c.redaction_policy_version,
                raw_artifacts.c.sanitized_safe_for_llm,
                raw_artifacts.c.created_at,
            )
            .where(raw_artifacts.c.program_id == program_id)
            .where(raw_artifacts.c.sanitized_safe_for_llm.is_(True))
            .where(raw_artifacts.c.sanitized_preview.is_not(None))
            .order_by(raw_artifacts.c.created_at.desc())
        )
        rows = await self.executor.fetch_all(query, limit, offset)
        return [RawArtifactPreview.model_validate(row) for row in rows]

    async def list_findings(
        self,
        program_id: uuid.UUID,
        severity: str | None = None,
        verified: bool | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[FindingArtifact]:
        query = (
            select(
                findings.c.id,
                findings.c.program_id,
                findings.c.vuln_type_id,
                vuln_types.c.code.label("vuln_code"),
                vuln_types.c.severity,
                findings.c.host_id,
                findings.c.endpoint_id,
                findings.c.parameter_id,
                findings.c.description,
                findings.c.evidence,
                findings.c.verified,
                findings.c.false_positive,
            )
            .select_from(findings.outerjoin(vuln_types, findings.c.vuln_type_id == vuln_types.c.id))
            .where(findings.c.program_id == program_id)
        )
        if severity:
            query = query.where(vuln_types.c.severity == severity)
        if verified is not None:
            query = query.where(findings.c.verified == verified)
        rows = await self.executor.fetch_all(query.order_by(findings.c.id), limit, offset)
        return [FindingArtifact.model_validate(row) for row in rows]

    async def list_leaks(
        self,
        program_id: uuid.UUID,
        verified: bool | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[LeakArtifact]:
        query = select(leaks).where(leaks.c.program_id == program_id)
        if verified is not None:
            query = query.where(leaks.c.verified == verified)
        rows = await self.executor.fetch_all(query.order_by(leaks.c.id), limit, offset)
        return [LeakArtifact.model_validate(sanitize_leak_row(row)) for row in rows]

    async def list_events(
        self,
        program_id: uuid.UUID,
        event_type: str | None = None,
        profile: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[EventArtifact]:
        query = select(
            event_store.c.id,
            event_store.c.event_id,
            event_store.c.event_type,
            event_store.c.program_id,
            event_store.c.job_id,
            event_store.c.run_id,
            event_store.c.correlation_id,
            event_store.c.causation_id,
            event_store.c.source,
            event_store.c.profile,
            event_store.c.confidence,
            event_store.c.created_at,
        ).where(event_store.c.program_id == program_id)
        if event_type:
            query = query.where(event_store.c.event_type == event_type)
        if profile:
            query = query.where(event_store.c.profile == profile)
        rows = await self.executor.fetch_all(query.order_by(event_store.c.created_at.desc()), limit, offset)
        return [EventArtifact.model_validate(row) for row in rows]
