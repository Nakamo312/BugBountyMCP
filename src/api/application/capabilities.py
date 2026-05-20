"""YAML-backed capability registry for scans, profiles, and future MCP tools."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from api.application.contracts import SafetyLevel
from api.application.pipeline.scope_policy import ScopePolicy
from api.application.pipeline.yaml_config import (
    CapabilitySpecConfig,
    DEFAULT_PIPELINE_CONFIG_PATH,
    load_pipeline_config,
)


@dataclass(frozen=True)
class ProfileSpec:
    id: str
    label: str
    safety_level: SafetyLevel
    allowed_options: frozenset[str] = frozenset()
    requires_approval: bool = False


@dataclass(frozen=True)
class CapabilitySpec:
    id: str
    label: str
    request_event: str
    queue: str
    default_profile: str
    profiles: tuple[ProfileSpec, ...]
    scope_policy: ScopePolicy
    mode: str = "routed"
    frontend: dict[str, Any] = field(default_factory=dict)

    @property
    def profile_ids(self) -> set[str]:
        return {profile.id for profile in self.profiles}


def _capability_from_config(
    capability_id: str,
    config: CapabilitySpecConfig,
) -> CapabilitySpec:
    return CapabilitySpec(
        id=capability_id,
        label=config.label,
        request_event=config.request_event,
        queue=config.queue,
        default_profile=config.default_profile,
        scope_policy=ScopePolicy(config.scope),
        mode=config.mode,
        frontend=config.frontend,
        profiles=tuple(
            ProfileSpec(
                id=profile_id,
                label=profile.label,
                safety_level=SafetyLevel(profile.safety_level),
                allowed_options=frozenset(profile.allowed_options),
                requires_approval=profile.requires_approval,
            )
            for profile_id, profile in config.profiles.items()
        ),
    )


def load_capabilities(path: str | Path | None = None) -> tuple[CapabilitySpec, ...]:
    """Load capability specs from the YAML control-plane config."""
    config_path = path or os.environ.get("PIPELINE_CONFIG_PATH") or DEFAULT_PIPELINE_CONFIG_PATH
    config = load_pipeline_config(config_path)
    return tuple(
        _capability_from_config(capability_id, capability)
        for capability_id, capability in config.capabilities.items()
    )


CAPABILITIES: tuple[CapabilitySpec, ...] = load_capabilities()
CAPABILITY_BY_ID = {capability.id: capability for capability in CAPABILITIES}
CAPABILITY_BY_EVENT = {capability.request_event: capability for capability in CAPABILITIES}


def get_capability(capability_id: str) -> CapabilitySpec:
    return CAPABILITY_BY_ID[capability_id]

