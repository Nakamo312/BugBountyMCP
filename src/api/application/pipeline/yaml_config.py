"""YAML-backed pipeline configuration models and loader."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator


DEFAULT_PIPELINE_CONFIG_PATH = Path(__file__).with_name("pipeline.yaml")
NodeType = Literal["scan", "ffuf", "amass", "hakip2host"]


class PipelineNodeSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: NodeType
    inputs: list[str] = Field(default_factory=list)
    outputs: dict[str, str | None] = Field(default_factory=dict)
    runner: str | None = None
    processor: str | None = None
    ingestor: str | None = None
    max_parallelism: int | str = 1
    execution_delay: int | float | str = 0
    max_concurrent_scans: int | str | None = None
    scope: str = "none"

    @field_validator("inputs")
    @classmethod
    def unique_inputs(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("inputs must be unique")
        return value


class PipelineConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nodes: dict[str, PipelineNodeSpec]

    @field_validator("nodes")
    @classmethod
    def require_nodes(cls, value: dict[str, PipelineNodeSpec]) -> dict[str, PipelineNodeSpec]:
        if not value:
            raise ValueError("pipeline config must declare at least one node")
        return value


def load_pipeline_config(path: str | Path | None = None) -> PipelineConfig:
    config_path = Path(path) if path else DEFAULT_PIPELINE_CONFIG_PATH
    raw: dict[str, Any] | None = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if raw is None:
        raw = {}
    return PipelineConfig.model_validate(raw)
