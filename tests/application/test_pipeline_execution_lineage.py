from __future__ import annotations

import sys
import types
from uuid import uuid4

import pytest

try:
    from dishka import AsyncContainer  # noqa: F401
except ImportError:
    dishka_module = types.ModuleType("dishka")

    class AsyncContainer:  # pragma: no cover - import stub
        pass

    dishka_module.AsyncContainer = AsyncContainer
    sys.modules["dishka"] = dishka_module

try:
    from api.infrastructure.events.event_bus import EventBus  # noqa: F401
except ImportError:
    event_bus_module = types.ModuleType("api.infrastructure.events.event_bus")

    class EventBus:  # pragma: no cover - import stub
        pass

    event_bus_module.EventBus = EventBus
    sys.modules["api.infrastructure.events.event_bus"] = event_bus_module

try:
    from api.infrastructure.artifacts.raw_artifact_repository import (  # noqa: F401
        RawArtifactRepository,
    )
except ImportError:
    raw_repo_module = types.ModuleType(
        "api.infrastructure.artifacts.raw_artifact_repository"
    )

    class RawArtifactRepository:  # pragma: no cover - import stub
        pass

    raw_repo_module.RawArtifactRepository = RawArtifactRepository
    sys.modules[
        "api.infrastructure.artifacts.raw_artifact_repository"
    ] = raw_repo_module

from api.application.pipeline.context import LINEAGE_PAYLOAD_KEY, PipelineContext
from api.application.pipeline.invocation import RUNNER_CONTEXT_PAYLOAD_KEY
from api.application.pipeline.invocation import build_invocation


class RecordingBus:
    def __init__(self) -> None:
        self.events = []

    async def publish(self, event):
        self.events.append(event)


@pytest.mark.asyncio
async def test_pipeline_context_emits_namespaced_execution_lineage_without_fake_invocation() -> None:
    bus = RecordingBus()
    action_id = uuid4()
    policy_id = uuid4()
    scope_id = uuid4()
    campaign_id = uuid4()
    correlation_id = uuid4()
    context = PipelineContext(node_id="subfinder", bus=bus)
    context.bind_event(
        {
            "event": "subfinder_scan_requested",
            "event_id": str(uuid4()),
            "job_id": str(uuid4()),
            "run_id": str(uuid4()),
            "program_id": str(uuid4()),
            "campaign_id": str(campaign_id),
            "correlation_id": str(correlation_id),
            "action_id": str(action_id),
            "capability_id": "subfinder",
            "profile_id": "passive-recon",
            "safety_level": "passive",
            "policy_decision_id": str(policy_id),
            "scope_decision_id": str(scope_id),
            "requested_by": "api",
            "execution_budget": {"max_targets": 25},
            "targets": ["example.com"],
        }
    )

    await context.emit(
        event="subdomain_discovered",
        targets=["api.example.com"],
        program_id=uuid4(),
    )

    emitted = bus.events[0]
    lineage = emitted.payload[LINEAGE_PAYLOAD_KEY]
    assert lineage["root_action_id"] == str(action_id)
    assert lineage["root_capability_id"] == "subfinder"
    assert lineage["root_profile_id"] == "passive-recon"
    assert lineage["policy_decision_id"] == str(policy_id)
    assert lineage["scope_decision_id"] == str(scope_id)
    assert lineage["root_execution_budget"] == {"max_targets": 25}

    legacy_event = emitted.to_legacy_dict()
    assert "action_id" not in legacy_event
    assert "capability_id" not in legacy_event
    assert build_invocation(legacy_event, legacy_event["targets"]) is None


@pytest.mark.asyncio
async def test_pipeline_context_emits_parent_artifact_for_downstream_lineage() -> None:
    bus = RecordingBus()
    parent_artifact_id = uuid4()
    context = PipelineContext(node_id="katana", bus=bus)
    context.bind_event(
        {
            "event": "host_discovered",
            "event_id": str(uuid4()),
            "job_id": str(uuid4()),
            "run_id": str(uuid4()),
            "program_id": str(uuid4()),
            "targets": ["https://example.com"],
            "payload": {
                LINEAGE_PAYLOAD_KEY: {
                    "root_action_id": str(uuid4()),
                    "root_capability_id": "httpx",
                }
            },
        }
    )
    context.set_downstream_parent_artifact(parent_artifact_id)

    await context.emit(
        event="js_files_discovered",
        targets=["https://example.com/app.js"],
        program_id=uuid4(),
    )

    emitted = bus.events[0]
    assert emitted.payload["parent_artifact_id"] == str(parent_artifact_id)
    assert emitted.payload[LINEAGE_PAYLOAD_KEY]["root_capability_id"] == "httpx"
    assert emitted.to_legacy_dict()["parent_artifact_id"] == str(parent_artifact_id)


@pytest.mark.asyncio
async def test_pipeline_context_emits_current_runner_context_separately() -> None:
    bus = RecordingBus()
    context = PipelineContext(node_id="httpx", bus=bus)
    context.bind_event(
        {
            "event": "subdomain_discovered",
            "event_id": str(uuid4()),
            "job_id": str(uuid4()),
            "run_id": str(uuid4()),
            "program_id": str(uuid4()),
            "targets": ["api.example.com"],
            "payload": {
                RUNNER_CONTEXT_PAYLOAD_KEY: {
                    "node_id": "subfinder",
                    "target_count": 1,
                }
            },
        }
    )
    context.set_current_runner_context(
        {
            "node_id": "httpx",
            "run_id": str(uuid4()),
            "targets": ["https://api.example.com"],
            "target_count": 1,
        }
    )

    await context.emit(
        event="url_discovered",
        targets=["https://api.example.com"],
        program_id=uuid4(),
    )

    emitted = bus.events[0]
    runner_context = emitted.payload[RUNNER_CONTEXT_PAYLOAD_KEY]
    assert context.upstream_runner_context["node_id"] == "subfinder"
    assert runner_context["node_id"] == "httpx"
    assert runner_context["target_count"] == 1
    assert "action_id" not in emitted.to_legacy_dict()
    assert "capability_id" not in emitted.to_legacy_dict()


@pytest.mark.asyncio
async def test_scan_node_sets_raw_artifact_as_downstream_parent() -> None:
    from api.application.contracts import ExecutionMode, SafetyLevel
    from api.application.pipeline.scan_node import ScanNode
    from api.infrastructure.events.event_types import EventType
    from api.infrastructure.schemas.models.process_event import ProcessEvent

    class Runner:
        def run_raw(self, targets):
            async def stream():
                yield ProcessEvent(type="stdout", payload="value")

            return stream()

    class Parser:
        async def parse_stream(self, stream):
            async for item in stream:
                yield item

    class Processor:
        async def batch_stream(self, stream):
            async for item in stream:
                if item.payload:
                    yield [item.payload]

    class Context(PipelineContext):
        def __init__(self) -> None:
            self.runner = Runner()
            self.captured = []

        async def get_service(self, service_type):
            if service_type is Runner:
                return self.runner
            if service_type is Processor:
                return Processor()
            raise AssertionError(service_type)

        def capture_raw_stream(self, stream, **kwargs):
            self.captured.append(kwargs)
            return stream

        def ingest_context(self, raw_artifact_id=None):
            return None

    node = ScanNode(
        node_id="httpx",
        event_in={EventType.HTTPX_SCAN_REQUESTED},
        event_out={},
        runner_type=Runner,
        processor_type=Processor,
        parser_type=Parser,
        execution_mode=ExecutionMode.INLINE,
    )
    ctx = Context()
    event = {
        "event_id": str(uuid4()),
        "event": "httpx_scan_requested",
        "program_id": str(uuid4()),
        "job_id": str(uuid4()),
        "run_id": str(uuid4()),
        "correlation_id": str(uuid4()),
        "action_id": str(uuid4()),
        "capability_id": "httpx",
        "profile_id": "safe-web-probe",
        "safety_level": SafetyLevel.SAFE_ACTIVE.value,
        "policy_decision_id": str(uuid4()),
        "scope_decision_id": str(uuid4()),
        "campaign_id": str(uuid4()),
        "targets": ["https://example.com"],
        "options": {},
        "execution_budget": {"max_targets": 20},
    }

    await node.execute(event, ctx)  # type: ignore[arg-type]

    assert ctx.downstream_parent_artifact_id == ctx.captured[0]["artifact_id"]
