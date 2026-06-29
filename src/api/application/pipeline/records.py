"""Typed canonical records flowing between parsers and fact ingestors."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar, Literal, Mapping, TypeAlias


@dataclass(frozen=True)
class HostFinding:
    """A discovered host name, independent of the tool that found it."""

    host: str
    source_tool: str
    target: str | None = None
    confidence: float | None = None
    ip: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    raw: Mapping[str, Any] | str | None = None

    kind: ClassVar[Literal["host_finding"]] = "host_finding"


@dataclass(frozen=True)
class UrlFinding:
    """URL evidence discovered by a tool, not yet an inventory endpoint."""

    url: str
    source_tool: str
    source_target: str | None = None
    discovered_from: str | None = None
    confidence: float | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    raw: Mapping[str, Any] | str | None = None

    kind: ClassVar[Literal["url_finding"]] = "url_finding"


@dataclass(frozen=True)
class FuzzFinding:
    """A fuzzing observation for a discovered URL candidate."""

    url: str
    source_tool: str
    source_target: str | None = None
    status_code: int | None = None
    length: int | None = None
    words: int | None = None
    lines: int | None = None
    redirect_location: str | None = None
    confidence: float | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    raw: Mapping[str, Any] | str | None = None

    kind: ClassVar[Literal["fuzz_finding"]] = "fuzz_finding"


@dataclass(frozen=True)
class JavaScriptReferenceFinding:
    """A JavaScript artifact reference to another URL."""

    source_url: str
    referenced_url: str
    source_tool: str
    source_target: str | None = None
    confidence: float | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    raw: Mapping[str, Any] | str | None = None

    kind: ClassVar[Literal["javascript_reference_finding"]] = "javascript_reference_finding"


@dataclass(frozen=True)
class ServiceFinding:
    """An exposed network service, independent of the scanner that found it."""

    ip: str
    port: int
    source_tool: str
    protocol: str = "tcp"
    scheme: str | None = None
    host: str | None = None
    service_name: str | None = None
    target: str | None = None
    confidence: float | None = None
    technologies: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)
    raw: Mapping[str, Any] | str | None = None

    kind: ClassVar[Literal["service_finding"]] = "service_finding"


CanonicalRecord: TypeAlias = (
    HostFinding
    | UrlFinding
    | FuzzFinding
    | JavaScriptReferenceFinding
    | ServiceFinding
)
