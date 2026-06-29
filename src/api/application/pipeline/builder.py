"""Build runtime pipeline nodes from declarative YAML config."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from api.application.pipeline.catalog import (
    INGESTORS,
    PROCESSORS,
    resolve_component,
    resolve_parser_ref,
    resolve_runner_ref,
    validate_component_refs,
)
from api.application.contracts import ExecutionMode
from api.application.pipeline.factory import NodeFactory
from api.application.pipeline.registry import NodeRegistry
from api.application.pipeline.scope_policy import ScopePolicy
from api.application.pipeline.yaml_config import PipelineConfig, PipelineNodeSpec, load_pipeline_config
from api.config import Settings
from api.infrastructure.events.event_types import EventType


def register_yaml_nodes(
    registry: NodeRegistry,
    settings: Settings,
    config_path: str | Path | None = None,
) -> None:
    config = load_pipeline_config(config_path)
    register_config_nodes(registry, settings, config)


def register_manifest_nodes(
    registry: NodeRegistry,
    settings: Settings,
    manifest_json: PipelineConfig | dict[str, Any],
) -> None:
    manifest = (
        manifest_json
        if isinstance(manifest_json, PipelineConfig)
        else PipelineConfig.model_validate(manifest_json)
    )
    register_config_nodes(registry, settings, manifest)


def register_config_nodes(
    registry: NodeRegistry,
    settings: Settings,
    config: PipelineConfig,
) -> None:
    validate_component_refs(config.workers)
    for node_id, spec in config.workers.items():
        registry.register(build_node(node_id, spec, settings))


def build_node(node_id: str, spec: PipelineNodeSpec, settings: Settings):
    event_in = _resolve_event_set(spec.inputs, node_id, "inputs")
    event_out = _resolve_event_set(spec.outputs.keys(), node_id, "outputs")
    max_parallelism = _resolve_int(spec.max_parallelism, settings, node_id, "max_parallelism")
    execution_mode = ExecutionMode(spec.execution_mode)
    retry_policy = _resolve_retry_policy(spec.retry, settings, node_id)
    scope_policy = _resolve_scope(spec.scope, node_id)
    max_targets_per_run = _resolve_optional_int(
        spec.max_targets_per_run,
        settings,
        node_id,
        "max_targets_per_run",
    )
    cooldown_seconds = _resolve_non_negative_number(
        spec.cooldown_seconds,
        settings,
        node_id,
        "cooldown_seconds",
    )
    max_fanout_per_event = _resolve_optional_int(
        spec.max_fanout_per_event,
        settings,
        node_id,
        "max_fanout_per_event",
    )
    max_expansion_depth = _resolve_optional_int(
        spec.max_expansion_depth,
        settings,
        node_id,
        "max_expansion_depth",
    )
    token_cost = _resolve_positive_number(
        spec.token_cost,
        settings,
        node_id,
        "token_cost",
    )
    runtime_concurrency = _resolve_runtime_concurrency(spec, settings, node_id)

    runner_ref = resolve_runner_ref(spec.runner, node_id)
    return NodeFactory.create_scan_node(
        node_id=node_id,
        event_in=event_in,
        event_out=_resolve_scan_outputs(spec.outputs, node_id),
        runner_type=runner_ref,
        parser_type=resolve_parser_ref(spec.parser, runner_ref, node_id),
        processor_type=resolve_component(PROCESSORS, spec.processor, "processor", node_id),
        ingestor_type=resolve_component(INGESTORS, spec.ingestor, "ingestor", node_id),
        max_parallelism=max_parallelism,
        execution_delay=_resolve_number(spec.execution_delay, settings, node_id, "execution_delay"),
        execution_mode=execution_mode,
        max_targets_per_run=max_targets_per_run,
        cooldown_seconds=cooldown_seconds,
        max_fanout_per_event=max_fanout_per_event,
        max_expansion_depth=max_expansion_depth,
        token_cost=token_cost,
        retry_policy=retry_policy,
        scope_policy=scope_policy,
        runtime=spec.runtime,
        runtime_concurrency=runtime_concurrency,
        requires_execution_context=(scope_policy is not ScopePolicy.NONE),
    )


def _resolve_scan_outputs(outputs: dict[str, str | None], node_id: str) -> dict[EventType, str]:
    resolved = {}
    for event_name, result_key in outputs.items():
        if not result_key:
            raise ValueError(f"Scan node '{node_id}' output '{event_name}' must define a result key")
        resolved[_resolve_event(event_name, node_id, "outputs")] = result_key
    return resolved


def _resolve_event_set(event_names, node_id: str, field_name: str) -> set[EventType | str]:
    return {_resolve_event(event_name, node_id, field_name) for event_name in event_names}


def _resolve_event(event_name: str, node_id: str, field_name: str) -> EventType | str:
    try:
        return EventType(event_name)
    except ValueError:
        if not isinstance(event_name, str) or not event_name.strip():
            raise ValueError(
                f"Invalid event '{event_name}' in {field_name} for pipeline node '{node_id}'"
            )
        return event_name


def _resolve_scope(scope: str, node_id: str) -> ScopePolicy:
    try:
        return ScopePolicy(scope)
    except ValueError as exc:
        raise ValueError(f"Unknown scope policy '{scope}' for pipeline node '{node_id}'") from exc


def _resolve_retry_policy(spec, settings: Settings, node_id: str) -> dict[str, Any]:
    return {
        "max_attempts": spec.max_attempts,
        "backoff_seconds": _resolve_number(
            spec.backoff_seconds,
            settings,
            node_id,
            "retry.backoff_seconds",
        ),
        "terminal_outcomes": list(spec.terminal_outcomes),
    }


def _resolve_int(value: int | str, settings: Settings, node_id: str, field_name: str) -> int:
    resolved = _resolve_number(value, settings, node_id, field_name)
    if not isinstance(resolved, int):
        raise ValueError(f"Pipeline node '{node_id}' field '{field_name}' must resolve to int")
    return resolved


def _resolve_optional_int(
    value: int | str | None,
    settings: Settings,
    node_id: str,
    field_name: str,
) -> int | None:
    if value is None:
        return None
    resolved = _resolve_int(value, settings, node_id, field_name)
    if resolved < 1:
        raise ValueError(f"Pipeline node '{node_id}' field '{field_name}' must be >= 1")
    return resolved


def _resolve_runtime_concurrency(
    spec: PipelineNodeSpec,
    settings: Settings,
    node_id: str,
) -> int | None:
    runtime_value = spec.runtime.concurrency if spec.runtime is not None else None
    value = runtime_value if runtime_value is not None else spec.max_concurrent_scans
    if value is None:
        return None
    return _resolve_int(value, settings, node_id, "runtime.concurrency")


def _resolve_non_negative_number(
    value: int | float | str,
    settings: Settings,
    node_id: str,
    field_name: str,
) -> int | float:
    resolved = _resolve_number(value, settings, node_id, field_name)
    if resolved < 0:
        raise ValueError(
            f"Pipeline node '{node_id}' field '{field_name}' must be >= 0"
        )
    return resolved


def _resolve_positive_number(
    value: int | float | str,
    settings: Settings,
    node_id: str,
    field_name: str,
) -> int | float:
    resolved = _resolve_number(value, settings, node_id, field_name)
    if resolved <= 0:
        raise ValueError(
            f"Pipeline node '{node_id}' field '{field_name}' must be > 0"
        )
    return resolved


def _resolve_number(
    value: int | float | str,
    settings: Settings,
    node_id: str,
    field_name: str,
) -> int | float:
    if isinstance(value, (int, float)):
        return value

    resolved: Any = getattr(settings, value, None)
    if resolved is None:
        raise ValueError(
            f"Pipeline node '{node_id}' field '{field_name}' references unknown setting '{value}'"
        )
    if not isinstance(resolved, (int, float)):
        raise ValueError(
            f"Pipeline node '{node_id}' field '{field_name}' setting '{value}' is not numeric"
        )
    return resolved
