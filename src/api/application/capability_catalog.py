"""Manifest-first tool catalog snapshots.

The declarative pipeline YAML / future tool manifests remain the source of truth.
PostgreSQL stores materialized snapshots for runtime lookup and audit, not a
second editable catalog.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from api.application.pipeline.yaml_config import (
    DEFAULT_PIPELINE_CONFIG_PATH,
    PipelineConfig,
    load_pipeline_config,
)
from api.application.execution_limits import ExecutionBudget, ToolOptionSpec

CATALOG_SCHEMA_VERSION = "tool-catalog/v1"


class ToolCatalogEntry(BaseModel):
    """One materialized capability/profile entry from the manifest."""

    model_config = ConfigDict(frozen=True)

    capability_id: str
    profile_id: str
    capability_label: str
    profile_label: str
    request_event: str
    queue: str
    default_profile: str
    mode: str
    scope_policy: str
    safety_class: str
    allowed_options: tuple[str, ...] = Field(default_factory=tuple)
    option_schema: dict[str, ToolOptionSpec] = Field(default_factory=dict)
    execution_budget: ExecutionBudget = Field(default_factory=ExecutionBudget)
    requires_approval: bool = False
    frontend: dict[str, Any] = Field(default_factory=dict)
    manifest_fragment: dict[str, Any] = Field(default_factory=dict)

    @property
    def key(self) -> str:
        return f"{self.capability_id}/{self.profile_id}"

    def accepts_options(self, options: dict[str, Any]) -> tuple[bool, tuple[str, ...]]:
        """Return whether an option dict is allowed for this profile."""
        unknown = tuple(sorted(set(options) - set(self.allowed_options)))
        return not unknown, unknown


class ToolCatalogSnapshot(BaseModel):
    """Deterministic resolved catalog produced from pipeline YAML/manifests."""

    schema_version: str = CATALOG_SCHEMA_VERSION
    catalog_hash: str
    source_hash: str
    source_path: str | None = None
    manifest_json: dict[str, Any]
    entries: tuple[ToolCatalogEntry, ...]
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def entry_for(self, capability_id: str, profile_id: str) -> ToolCatalogEntry | None:
        for entry in self.entries:
            if entry.capability_id == capability_id and entry.profile_id == profile_id:
                return entry
        return None

    def validate_options(
        self,
        *,
        capability_id: str,
        profile_id: str,
        options: dict[str, Any],
    ) -> tuple[bool, tuple[str, ...]]:
        entry = self.entry_for(capability_id, profile_id)
        if entry is None:
            return False, (f"unknown profile: {capability_id}/{profile_id}",)
        return entry.accepts_options(options)


def _canonical_json(data: Any) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _manifest_dict(config: PipelineConfig) -> dict[str, Any]:
    """Return a stable manifest representation from a validated config."""
    return config.model_dump(mode="json", exclude_none=True)


def _entry_from_profile(
    *,
    capability_id: str,
    profile_id: str,
    capability_payload: dict[str, Any],
) -> ToolCatalogEntry:
    profile_payload = capability_payload["profiles"][profile_id]
    option_payload = profile_payload.get("options") or {}
    option_schema = {
        name: ToolOptionSpec.model_validate(spec)
        for name, spec in option_payload.items()
    }
    allowed_options = (
        tuple(sorted(option_schema))
        if option_schema
        else tuple(sorted(profile_payload.get("allowed_options", [])))
    )
    return ToolCatalogEntry(
        capability_id=capability_id,
        profile_id=profile_id,
        capability_label=capability_payload["label"],
        profile_label=profile_payload["label"],
        request_event=capability_payload["request_event"],
        queue=capability_payload["queue"],
        default_profile=capability_payload["default_profile"],
        mode=capability_payload.get("mode", "routed"),
        scope_policy=capability_payload.get("scope", "none"),
        safety_class=profile_payload["safety_level"],
        allowed_options=allowed_options,
        option_schema=option_schema,
        execution_budget=ExecutionBudget.model_validate(
            profile_payload.get("budgets") or {}
        ),
        requires_approval=bool(profile_payload.get("requires_approval", False)),
        frontend=capability_payload.get("frontend", {}),
        manifest_fragment={
            "capability": capability_payload,
            "profile": profile_payload,
        },
    )


def build_tool_catalog_snapshot(
    config: PipelineConfig,
    *,
    source_path: str | Path | None = None,
    source_text: str | None = None,
) -> ToolCatalogSnapshot:
    """Resolve a validated pipeline config into a deterministic catalog snapshot."""
    manifest_json = _manifest_dict(config)
    entries: list[ToolCatalogEntry] = []

    for capability_id in sorted(manifest_json.get("capabilities", {})):
        capability_payload = manifest_json["capabilities"][capability_id]
        for profile_id in sorted(capability_payload.get("profiles", {})):
            entries.append(
                _entry_from_profile(
                    capability_id=capability_id,
                    profile_id=profile_id,
                    capability_payload=capability_payload,
                )
            )

    catalog_payload = {
        "schema_version": CATALOG_SCHEMA_VERSION,
        "entries": [entry.model_dump(mode="json") for entry in entries],
    }
    canonical_manifest = _canonical_json(manifest_json)
    return ToolCatalogSnapshot(
        catalog_hash=_sha256_text(_canonical_json(catalog_payload)),
        source_hash=_sha256_text(source_text if source_text is not None else canonical_manifest),
        source_path=str(source_path) if source_path is not None else None,
        manifest_json=manifest_json,
        entries=tuple(entries),
    )


def load_tool_catalog_snapshot(path: str | Path | None = None) -> ToolCatalogSnapshot:
    """Load and resolve the manifest-first tool catalog from YAML."""
    config_path = Path(path or os.environ.get("PIPELINE_CONFIG_PATH") or DEFAULT_PIPELINE_CONFIG_PATH)
    source_text = config_path.read_text(encoding="utf-8")
    return build_tool_catalog_snapshot(
        load_pipeline_config(config_path),
        source_path=config_path,
        source_text=source_text,
    )
