from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    computed_field,
    field_validator,
    model_validator,
)


class _GraphFactBase(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    program_id: UUID
    producer: str = Field(min_length=1)
    source_artifact_id: UUID | None = None
    tool_run_id: UUID | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    properties: dict[str, Any] = Field(default_factory=dict)

    @field_validator("producer")
    @classmethod
    def _strip_required_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("value must not be empty")
        return stripped


class GraphNodeFact(_GraphFactBase):
    kind: str = Field(min_length=1)
    key: str = Field(min_length=1)

    @field_validator("kind", "key")
    @classmethod
    def _strip_identity_part(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("identity part must not be empty")
        return stripped

    @computed_field
    @property
    def identity_key(self) -> str:
        return f"node:{self.kind}:{self.key}"


class GraphEdgeFact(_GraphFactBase):
    edge_kind: str = Field(min_length=1)
    src_kind: str = Field(min_length=1)
    src_key: str = Field(min_length=1)
    dst_kind: str = Field(min_length=1)
    dst_key: str = Field(min_length=1)

    @field_validator("edge_kind", "src_kind", "src_key", "dst_kind", "dst_key")
    @classmethod
    def _strip_identity_part(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("identity part must not be empty")
        return stripped

    @computed_field
    @property
    def identity_key(self) -> str:
        return f"edge:{self.program_id}:{self.src_kind}:{self.src_key}:{self.edge_kind}:{self.dst_kind}:{self.dst_key}"


GraphFact = GraphNodeFact | GraphEdgeFact


class GraphFactBatch(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    program_id: UUID
    facts: list[GraphFact]
    produced_by: str = Field(min_length=1)
    parser_version: str = Field(min_length=1)

    @field_validator("produced_by", "parser_version")
    @classmethod
    def _strip_batch_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("value must not be empty")
        return stripped

    @model_validator(mode="after")
    def _requires_facts_for_one_program(self) -> "GraphFactBatch":
        if not self.facts:
            raise ValueError("graph fact batch must not be empty")
        if any(fact.program_id != self.program_id for fact in self.facts):
            raise ValueError("graph fact batch cannot mix program_id values")
        return self
