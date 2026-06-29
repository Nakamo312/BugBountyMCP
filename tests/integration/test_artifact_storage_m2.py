from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import insert, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker

from api.infrastructure.adapters.orm import (
    action_requests,
    programs,
    raw_artifacts,
    scope_decisions,
)


pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_m2_artifact_metadata_roundtrip_and_lineage_constraints(
    integration_async_engine,
) -> None:
    session_factory = async_sessionmaker(
        integration_async_engine,
        expire_on_commit=False,
    )
    program_id = uuid4()
    parent_artifact_id = uuid4()
    child_artifact_id = uuid4()
    scope_decision_id = uuid4()
    action_id = uuid4()

    async with session_factory() as session:
        await session.execute(
            insert(programs).values(
                id=program_id,
                name=f"artifact-m2-{program_id}",
            )
        )
        await session.execute(
            insert(action_requests).values(
                id=action_id,
                program_id=program_id,
                kind="scan",
                capability_id="httpx",
                profile_id="safe-web-probe",
                requested_by="integration-test",
                metadata={},
                status="allowed",
                request={
                    "program_id": str(program_id),
                    "catalog_id": str(uuid4()),
                    "targets": ["example.com"],
                },
            )
        )
        await session.execute(
            insert(scope_decisions).values(
                id=scope_decision_id,
                action_id=action_id,
                status="allowed",
                scope_policy="strict",
                reasons=[],
                allowed_targets=["example.com"],
                blocked_targets=[],
                metadata={},
            )
        )
        await session.execute(
            insert(raw_artifacts).values(
                id=parent_artifact_id,
                program_id=program_id,
                node_id="httpx",
                event_name="httpx.completed",
                artifact_type="raw_tool_output",
                storage_uri="data/raw/parent.ndjson.gz",
                sha256="a" * 64,
                size_bytes=2048,
                storage_size_bytes=256,
                content_encoding="gzip",
                retention_class="program_lifetime",
                preview="Authorization: Bearer secret",
                sanitized_preview="Authorization: [redacted]",
                sanitizer_version="research-sanitizer-v1",
                redaction_policy_version="redaction-policy-v1",
                raw_safe_for_llm=False,
                sanitized_safe_for_llm=True,
                parser_name="HTTPXProcessEventParser",
                parser_version="1",
                scope_decision_id=scope_decision_id,
                source_targets=["example.com"],
                artifact_metadata={},
            )
        )
        await session.execute(
            insert(raw_artifacts).values(
                id=child_artifact_id,
                program_id=program_id,
                node_id="derived",
                event_name="derived.completed",
                artifact_type="raw_tool_output",
                storage_uri="data/raw/child.ndjson",
                sha256="b" * 64,
                size_bytes=64,
                storage_size_bytes=64,
                content_encoding="identity",
                retention_class="short_lived",
                raw_safe_for_llm=False,
                sanitized_safe_for_llm=False,
                parser_name="DerivedParser",
                parser_version="2",
                scope_decision_id=scope_decision_id,
                source_targets=["https://example.com/api"],
                parent_artifact_id=parent_artifact_id,
                artifact_metadata={},
            )
        )
        await session.commit()

    async with session_factory() as session:
        parent = (
            await session.execute(
                select(raw_artifacts).where(
                    raw_artifacts.c.id == parent_artifact_id
                )
            )
        ).mappings().one()
        child = (
            await session.execute(
                select(raw_artifacts).where(
                    raw_artifacts.c.id == child_artifact_id
                )
            )
        ).mappings().one()

    assert parent["content_encoding"] == "gzip"
    assert parent["storage_size_bytes"] < parent["size_bytes"]
    assert parent["raw_safe_for_llm"] is False
    assert parent["sanitized_safe_for_llm"] is True
    assert "secret" not in parent["sanitized_preview"]
    assert parent["scope_decision_id"] == scope_decision_id
    assert child["parent_artifact_id"] == parent_artifact_id
    assert child["source_targets"] == ["https://example.com/api"]

    async with session_factory() as session:
        await session.execute(
            update(raw_artifacts)
            .where(raw_artifacts.c.id == child_artifact_id)
            .values(parent_artifact_id=None)
        )
        await session.commit()


@pytest.mark.asyncio
async def test_m2_rejects_llm_safe_flag_without_sanitizer_lineage(
    integration_async_engine,
) -> None:
    session_factory = async_sessionmaker(
        integration_async_engine,
        expire_on_commit=False,
    )
    program_id = uuid4()

    async with session_factory() as session:
        await session.execute(
            insert(programs).values(
                id=program_id,
                name=f"artifact-m2-invalid-{program_id}",
            )
        )
        with pytest.raises(Exception):
            await session.execute(
                insert(raw_artifacts).values(
                    id=uuid4(),
                    program_id=program_id,
                    node_id="invalid",
                    event_name="invalid.completed",
                    artifact_type="raw_tool_output",
                    storage_uri="data/raw/invalid.ndjson",
                    sha256="c" * 64,
                    size_bytes=1,
                    storage_size_bytes=1,
                    content_encoding="identity",
                    retention_class="ephemeral",
                    sanitized_safe_for_llm=True,
                    parser_name="InvalidParser",
                    parser_version="1",
                    source_targets=[],
                    artifact_metadata={},
                )
            )
        await session.rollback()
