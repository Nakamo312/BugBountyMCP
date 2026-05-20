"""Build runtime pipeline nodes from declarative YAML config."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from api.application.pipeline.catalog import INGESTORS, PARSERS, PROCESSORS, RUNNERS, resolve_component
from api.application.pipeline.factory import NodeFactory
from api.application.pipeline.nodes.amass_node import AmassNode
from api.application.pipeline.nodes.ffuf_node import FFUFNode
from api.application.pipeline.nodes.hakip2host_node import Hakip2HostNode
from api.application.pipeline.registry import NodeRegistry
from api.application.pipeline.scope_policy import ScopePolicy
from api.application.pipeline.yaml_config import PipelineNodeSpec, load_pipeline_config
from api.config import Settings
from api.infrastructure.events.event_types import EventType


def register_yaml_nodes(
    registry: NodeRegistry,
    settings: Settings,
    config_path: str | Path | None = None,
) -> None:
    config = load_pipeline_config(config_path)
    validate_component_refs(config.workers)
    for node_id, spec in config.workers.items():
        registry.register(build_node(node_id, spec, settings))


def validate_component_refs(workers: dict[str, PipelineNodeSpec]) -> None:
    for node_id, spec in workers.items():
        resolve_component(RUNNERS, spec.runner, "runner", node_id)
        if spec.parser is not None:
            resolve_component(PARSERS, spec.parser, "parser", node_id)
        if spec.processor is not None:
            resolve_component(PROCESSORS, spec.processor, "processor", node_id)
        if spec.ingestor is not None:
            resolve_component(INGESTORS, spec.ingestor, "ingestor", node_id)


def build_node(node_id: str, spec: PipelineNodeSpec, settings: Settings):
    event_in = _resolve_event_set(spec.inputs, node_id, "inputs")
    event_out = _resolve_event_set(spec.outputs.keys(), node_id, "outputs")
    max_parallelism = _resolve_int(spec.max_parallelism, settings, node_id, "max_parallelism")
    scope_policy = _resolve_scope(spec.scope, node_id)

    if spec.type == "scan":
        return NodeFactory.create_scan_node(
            node_id=node_id,
            event_in=event_in,
            event_out=_resolve_scan_outputs(spec.outputs, node_id),
            runner_type=resolve_component(RUNNERS, spec.runner, "runner", node_id),
            parser_type=resolve_component(PARSERS, spec.parser, "parser", node_id),
            processor_type=resolve_component(PROCESSORS, spec.processor, "processor", node_id),
            ingestor_type=resolve_component(INGESTORS, spec.ingestor, "ingestor", node_id),
            max_parallelism=max_parallelism,
            execution_delay=_resolve_number(spec.execution_delay, settings, node_id, "execution_delay"),
            scope_policy=scope_policy,
        )

    if spec.type == "ffuf":
        return FFUFNode(
            node_id=node_id,
            event_in=event_in,
            event_out=event_out,
            runner_key=resolve_component(RUNNERS, spec.runner, "runner", node_id),
            ingestor_key=resolve_component(INGESTORS, spec.ingestor, "ingestor", node_id),
            max_parallelism=max_parallelism,
            max_concurrent_scans=_resolve_int(
                spec.max_concurrent_scans or 5,
                settings,
                node_id,
                "max_concurrent_scans",
            ),
            scope_policy=scope_policy,
        )

    if spec.type == "amass":
        return AmassNode(
            node_id=node_id,
            event_in=event_in,
            event_out=event_out,
            runner_key=resolve_component(RUNNERS, spec.runner, "runner", node_id),
            ingestor_key=resolve_component(INGESTORS, spec.ingestor, "ingestor", node_id),
            max_parallelism=max_parallelism,
            max_concurrent_scans=_resolve_int(
                spec.max_concurrent_scans or 5,
                settings,
                node_id,
                "max_concurrent_scans",
            ),
            scope_policy=scope_policy,
        )

    if spec.type == "hakip2host":
        return Hakip2HostNode(
            node_id=node_id,
            event_in=event_in,
            event_out=event_out,
            runner_key=resolve_component(RUNNERS, spec.runner, "runner", node_id),
            processor_key=resolve_component(PROCESSORS, spec.processor, "processor", node_id),
            host_ingestor_key=resolve_component(INGESTORS, spec.ingestor, "ingestor", node_id),
            max_parallelism=max_parallelism,
            scope_policy=scope_policy,
        )

    raise ValueError(f"Unsupported pipeline node type '{spec.type}' for node '{node_id}'")


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


def _resolve_int(value: int | str, settings: Settings, node_id: str, field_name: str) -> int:
    resolved = _resolve_number(value, settings, node_id, field_name)
    if not isinstance(resolved, int):
        raise ValueError(f"Pipeline node '{node_id}' field '{field_name}' must resolve to int")
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
