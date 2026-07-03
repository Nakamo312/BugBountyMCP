"""Operator-controlled Workbench projection refresh use case.

This is the explicit mutation boundary that makes the dashboard usable when the
read models are missing or stale. It is deliberately not a generic command
executor: callers choose from a small operation enum, and the infrastructure
layer maps that enum to safe internal projection routines.
"""
from __future__ import annotations

from enum import StrEnum
from typing import Any, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class WorkbenchProjectionOperation(StrEnum):
    BUILD_SURFACE = "build_surface"
    MATERIALIZE_COMPONENTS = "materialize_components"
    REFRESH_WORKBENCH = "refresh_workbench"
    SYNC_NEO4J = "sync_neo4j"


class WorkbenchProjectionRunRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    program_id: UUID
    operation: WorkbenchProjectionOperation = WorkbenchProjectionOperation.REFRESH_WORKBENCH

    @field_validator("operation", mode="before")
    @classmethod
    def _normalize_operation_alias(cls, value: object) -> object:
        if value is None:
            return value
        text = str(value).strip().lower()
        aliases = {
            "neo4j": "sync_neo4j",
            "neo4j_sync": "sync_neo4j",
            "sync_graph": "sync_neo4j",
            "sync_relationship_graph": "sync_neo4j",
            "rebuild_neo4j": "sync_neo4j",
            "build_neo4j": "sync_neo4j",
        }
        return aliases.get(text, value)
    limit: int = Field(default=10_000, ge=1, le=100_000)
    snapshot_id: UUID | None = None
    component_limit: int = Field(default=10, ge=1, le=100)
    candidate_limit: int = Field(default=10, ge=1, le=100)
    similarity_cutoff: float = Field(default=0.03, ge=0.0, le=1.0)


class WorkbenchProjectionStepResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step_id: str
    status: str
    message: str
    snapshot_id: UUID | None = None
    analysis_run_id: UUID | None = None
    counts: dict[str, int] = Field(default_factory=dict)
    details: dict[str, Any] = Field(default_factory=dict)


class WorkbenchProjectionRunResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    program_id: UUID
    operation: WorkbenchProjectionOperation
    status: str
    message: str
    snapshot_id: UUID | None = None
    analysis_run_id: UUID | None = None
    steps: list[WorkbenchProjectionStepResult] = Field(default_factory=list)
    counts: dict[str, int] = Field(default_factory=dict)
    boundary: dict[str, Any] = Field(default_factory=dict)


class WorkbenchProjectionControlStore(Protocol):
    async def run_projection_operation(
        self,
        request: WorkbenchProjectionRunRequest,
    ) -> WorkbenchProjectionRunResult: ...


class WorkbenchProjectionControlService:
    def __init__(self, store: WorkbenchProjectionControlStore) -> None:
        self._store = store

    async def run_projection_operation(
        self,
        request: WorkbenchProjectionRunRequest,
    ) -> WorkbenchProjectionRunResult:
        return await self._store.run_projection_operation(request)


def workbench_projection_control_boundary() -> dict[str, Any]:
    return {
        "surface": "operator_controlled_projection_refresh",
        "allowed_operations": [operation.value for operation in WorkbenchProjectionOperation],
        "arbitrary_command_execution": "forbidden",
        "user_supplied_command_text": "forbidden",
        "tool_execution": "forbidden",
        "action_submission": "forbidden",
        "proposal_creation": "forbidden",
        "raw_cypher": "forbidden",
        "raw_secret_material": "forbidden",
        "manual_snapshot_id_required": False,
        "purpose": "make_workbench_read_models_usable_from_dashboard",
    }
