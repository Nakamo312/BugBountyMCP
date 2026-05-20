"""Read-only artifact contracts exposed to MCP clients."""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ArtifactModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class HostArtifact(ArtifactModel):
    id: UUID
    program_id: UUID
    host: str
    in_scope: bool
    cname: Any = None


class IPArtifact(ArtifactModel):
    id: UUID
    program_id: UUID
    address: str
    in_scope: bool


class ServiceArtifact(ArtifactModel):
    id: UUID
    ip_id: UUID
    address: str
    scheme: str
    port: int
    technologies: Any = None
    favicon_hash: str | None = None
    websocket: bool | None = None


class EndpointArtifact(ArtifactModel):
    id: UUID
    program_id: UUID
    host_id: UUID
    host: str
    service_id: UUID
    scheme: str
    port: int
    path: str
    normalized_path: str
    methods: list[str] = Field(default_factory=list)
    status_code: int | None = None


class EndpointDetailArtifact(EndpointArtifact):
    parameters: list[dict[str, Any]] = Field(default_factory=list)
    headers: list[dict[str, Any]] = Field(default_factory=list)
    bodies: list[dict[str, Any]] = Field(default_factory=list)


class ParameterArtifact(ArtifactModel):
    id: UUID
    endpoint_id: UUID
    service_id: UUID
    name: str
    location: str
    param_type: str
    reflected: bool | None = None
    is_array: bool | None = None
    example_value: str | None = None


class HeaderArtifact(ArtifactModel):
    id: UUID
    endpoint_id: UUID
    name: str
    value: str


class BodyArtifact(ArtifactModel):
    id: UUID
    endpoint_id: UUID
    body_hash: str
    body_ref: str
    body_length: int
    body_preview: str
    body_content: str | None = None


class DNSRecordArtifact(ArtifactModel):
    id: UUID
    host_id: UUID
    host: str
    record_type: str
    value: str
    ttl: int | None = None
    priority: int | None = None
    is_wildcard: bool


class FindingArtifact(ArtifactModel):
    id: UUID
    program_id: UUID
    vuln_type_id: UUID
    vuln_code: str | None = None
    severity: str | None = None
    host_id: UUID | None = None
    endpoint_id: UUID | None = None
    parameter_id: UUID | None = None
    description: str
    evidence: Any = None
    verified: bool | None = None
    false_positive: bool | None = None


class LeakArtifact(ArtifactModel):
    id: UUID
    program_id: UUID
    endpoint_id: UUID | None = None
    content: str
    verified: bool | None = None
    false_positive: bool | None = None


class EventArtifact(ArtifactModel):
    id: UUID
    event_id: UUID
    event_type: str
    program_id: UUID
    job_id: UUID | None = None
    run_id: UUID | None = None
    correlation_id: UUID
    causation_id: UUID | None = None
    source: str
    profile: str | None = None
    confidence: float
    payload: Any = None
    created_at: datetime
