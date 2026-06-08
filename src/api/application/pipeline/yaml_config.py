"""YAML-backed control-plane configuration models and loader."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


DEFAULT_PIPELINE_CONFIG_PATH = Path(__file__).with_name("pipeline.yaml")
NodeType = Literal["scan", "ffuf", "amass", "hakip2host"]
ScopePolicyName = Literal["none", "confidence", "strict", "approval_required"]
SafetyLevelName = Literal["passive", "safe_active", "active", "sensitive"]
CapabilityMode = Literal["routed", "compatibility", "manual"]
QueueName = Literal["discovery", "enumeration", "validation", "analysis"]
ExecutionModeName = Literal["inline", "scheduled"]
RetryOutcomeName = Literal["tool_failed"]


class PipelineDefaults(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_parallelism: int | str = 1
    execution_delay: int | float | str = 0
    execution_mode: ExecutionModeName = "inline"
    retry: "RetryPolicyConfig" = Field(default_factory=lambda: RetryPolicyConfig())
    scope: ScopePolicyName = "none"


class RetryPolicyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_attempts: int = Field(default=1, ge=1)
    backoff_seconds: int | float | str = Field(default=0)
    terminal_outcomes: list[RetryOutcomeName] = Field(default_factory=list)


class ToolRuntimeSpec(BaseModel):
    """Optional declarative runtime metadata for generic/CLI workers.

    The runtime block is intentionally data-only. It can describe tool names,
    static args, and option mappings, but the runtime builder still resolves
    only whitelisted runner classes/components from the Python catalog.
    """

    model_config = ConfigDict(extra="forbid")

    tool: str | None = None
    path_key: str | None = None
    timeout: int | str | None = None
    static_args: list[str] = Field(default_factory=list)
    option_args: dict[str, str] = Field(default_factory=dict)


class EventSpecConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    queue: QueueName


class ProfileSpecConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    safety_level: SafetyLevelName
    allowed_options: list[str] = Field(default_factory=list)
    requires_approval: bool = False

    @field_validator("allowed_options")
    @classmethod
    def unique_allowed_options(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("allowed_options must be unique")
        return value


class CapabilitySpecConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    request_event: str = Field(min_length=1)
    queue: str = Field(min_length=1)
    default_profile: str = Field(min_length=1)
    scope: ScopePolicyName = "none"
    profiles: dict[str, ProfileSpecConfig]
    mode: CapabilityMode = "routed"
    frontend: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def default_profile_must_exist(self) -> "CapabilitySpecConfig":
        if self.default_profile not in self.profiles:
            raise ValueError(
                f"default_profile '{self.default_profile}' is not declared in profiles"
            )
        return self


class PipelineNodeSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: NodeType
    inputs: list[str] = Field(default_factory=list)
    outputs: dict[str, str | None] = Field(default_factory=dict)
    runner: str | None = None
    parser: str | None = None
    processor: str | None = None
    ingestor: str | None = None
    max_parallelism: int | str = 1
    execution_delay: int | float | str = 0
    execution_mode: ExecutionModeName = "inline"
    retry: RetryPolicyConfig = Field(default_factory=RetryPolicyConfig)
    max_concurrent_scans: int | str | None = None
    scope: ScopePolicyName = "none"
    runtime: ToolRuntimeSpec | None = None

    @field_validator("inputs")
    @classmethod
    def unique_inputs(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("inputs must be unique")
        return value


class PipelineConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    defaults: PipelineDefaults = Field(default_factory=PipelineDefaults)
    events: dict[str, EventSpecConfig] = Field(default_factory=dict)
    capabilities: dict[str, CapabilitySpecConfig] = Field(default_factory=dict)
    workers: dict[str, PipelineNodeSpec]

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_nodes_key(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        data = dict(data)
        if "workers" not in data and "nodes" in data:
            data["workers"] = data.pop("nodes")
        defaults = data.get("defaults") or {}
        workers = data.get("workers") or {}
        if isinstance(defaults, dict) and isinstance(workers, dict):
            defaultable_fields = (
                "max_parallelism",
                "execution_delay",
                "execution_mode",
                "retry",
                "scope",
            )
            data["workers"] = {
                worker_id: {
                    **{
                        field_name: defaults[field_name]
                        for field_name in defaultable_fields
                        if field_name in defaults
                    },
                    **worker_spec,
                }
                if isinstance(worker_spec, dict)
                else worker_spec
                for worker_id, worker_spec in workers.items()
            }
        return data

    @field_validator("workers")
    @classmethod
    def require_workers(cls, value: dict[str, PipelineNodeSpec]) -> dict[str, PipelineNodeSpec]:
        if not value:
            raise ValueError("pipeline config must declare at least one worker")
        return value

    @model_validator(mode="after")
    def validate_capabilities(self) -> "PipelineConfig":
        request_events: dict[str, str] = {}
        worker_inputs = {
            event_name
            for worker in self.workers.values()
            for event_name in worker.inputs
        }

        for capability_id, capability in self.capabilities.items():
            owner = request_events.get(capability.request_event)
            if owner is not None:
                raise ValueError(
                    f"request_event '{capability.request_event}' is used by both "
                    f"'{owner}' and '{capability_id}'"
                )
            request_events[capability.request_event] = capability_id

            if capability.mode == "routed" and capability.request_event not in worker_inputs:
                raise ValueError(
                    f"capability '{capability_id}' request_event "
                    f"'{capability.request_event}' is not consumed by any worker"
                )

        return self

    @property
    def nodes(self) -> dict[str, PipelineNodeSpec]:
        """Backward-compatible alias for older builder/tests."""
        return self.workers


def load_pipeline_config(path: str | Path | None = None) -> PipelineConfig:
    config_path = Path(path) if path else DEFAULT_PIPELINE_CONFIG_PATH
    raw: dict[str, Any] | None = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if raw is None:
        raw = {}
    return PipelineConfig.model_validate(raw)
