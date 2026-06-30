from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from api.application.contracts import ExecutionMode
from api.application.process_event_contracts import ProcessEvent
from api.application.pipeline.context_factory import PipelineContextFactory
from api.application.pipeline.scan_node import ScanNode
from api.application.pipeline.scope_policy import ScopePolicy
from api.application.event_contracts import EventType


def _read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def test_startup_activates_manifest_before_registry_start() -> None:
    source = _read("src/api/presentation/rest/app.py")

    activate_pos = source.index("await activator.activate(manifest)")
    register_pos = source.index("register_manifest_nodes(")
    start_pos = source.index("await registry.start()")

    assert "load_tool_catalog_snapshot(settings.PIPELINE_CONFIG_PATH)" in source
    assert "ManifestActivator" in source
    assert activate_pos < register_pos < start_pos


def test_pipeline_provider_does_not_read_yaml_for_registry() -> None:
    source = _read("src/api/infrastructure/providers/pipeline.py")
    provider_block = source[source.index("class PipelineProvider"):]

    assert "register_yaml_nodes" not in provider_block
    assert "PIPELINE_CONFIG_PATH" not in provider_block


def _pipeline_provider():
    dishka = pytest.importorskip("dishka")
    if not hasattr(dishka, "Provider"):
        pytest.skip("dishka Provider unavailable in this test environment")
    from api.infrastructure.providers.pipeline import PipelineProvider

    return PipelineProvider()


def test_pipeline_provider_wires_registry_with_context_factory() -> None:
    provider = _pipeline_provider()
    context_factory = PipelineContextFactory(
        raw_outputs=None,
        raw_artifact_metadata=None,
        run_states=None,
        action_outcomes=None,
        scope_filter=None,
    )

    registry = provider.get_node_registry(
        bus=SimpleNamespace(),
        settings=SimpleNamespace(),
        container=SimpleNamespace(),
        context_factory=context_factory,
    )

    from api.infrastructure.events.queue_config import QueueConfig

    assert registry.context_factory is context_factory
    assert registry.subscription_queues == tuple(QueueConfig.get_all_queues())


class RawOutputsStub:
    def capture_stream(self, stream, **kwargs):
        return stream


class RawArtifactMetadataStub:
    async def record(self, metadata: dict) -> None:
        return None


class ScopeFilterStub:
    async def filter_by_scope(
        self,
        *,
        program_id: UUID,
        targets: list[str],
        policy: ScopePolicy,
    ) -> tuple[list[str], list[str]]:
        return targets, []


@pytest.mark.asyncio
async def test_registered_scan_node_receives_context_with_raw_capture() -> None:
    provider = _pipeline_provider()
    context_factory = provider.get_pipeline_context_factory(
        raw_outputs=RawOutputsStub(),
        raw_artifact_metadata=RawArtifactMetadataStub(),
        run_states=None,
        action_outcomes=None,
        scope_filter=ScopeFilterStub(),
    )
    registry = provider.get_node_registry(
        bus=SimpleNamespace(),
        settings=SimpleNamespace(),
        container=SimpleNamespace(),
        context_factory=context_factory,
    )
    node = ScanNode(
        node_id="httpx",
        event_in={EventType.HOST_DISCOVERED},
        event_out={},
        runner_type=object,
        processor_type=object,
        execution_mode=ExecutionMode.INLINE,
    )

    registry.register(node)
    context = await node._create_context()

    async def stream():
        yield ProcessEvent(type="stdout", payload="value")

    captured = context.capture_raw_stream(
        stream(),
        program_id=uuid4(),
        event_name="host_discovered",
        targets=["example.com"],
    )
    assert [event async for event in captured] == [ProcessEvent(type="stdout", payload="value")]


@pytest.mark.asyncio
async def test_scan_node_context_factory_fallback_is_legacy_without_raw_capture() -> None:
    node = ScanNode(
        node_id="httpx",
        event_in={EventType.HOST_DISCOVERED},
        event_out={},
        runner_type=object,
        processor_type=object,
        execution_mode=ExecutionMode.INLINE,
    )
    node.set_context_factory(
        bus=SimpleNamespace(),
        container=SimpleNamespace(),
        settings=SimpleNamespace(),
        context_factory=None,
    )

    context = await node._create_context()

    async def stream():
        yield ProcessEvent(type="stdout", payload="value")

    assert node.legacy_context_fallback is True
    with pytest.raises(RuntimeError, match="Raw artifact capture not available"):
        context.capture_raw_stream(
            stream(),
            program_id=uuid4(),
            event_name="host_discovered",
            targets=["example.com"],
        )


def test_builder_can_register_nodes_from_manifest_json() -> None:
    source = _read("src/api/infrastructure/pipeline/builder.py")

    assert "def register_manifest_nodes" in source
    assert "PipelineConfig.model_validate(manifest_json)" in source
    assert "def register_config_nodes" in source


def test_runtime_manifest_activator_owns_postgres_activation() -> None:
    source = _read("src/api/infrastructure/runtime_manifest.py")

    assert "class ManifestActivator" in source
    assert "async def activate" in source
    assert "async def active_manifest" in source
    assert "tool_catalog_snapshots" in source
    assert "tool_catalog_entries" in source
