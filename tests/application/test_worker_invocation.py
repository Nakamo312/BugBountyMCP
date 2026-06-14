from __future__ import annotations

import sys
import types
from uuid import uuid4

import pytest

# ScanNode imports PipelineContext, which imports dishka. Keep this unit test
# independent from optional DI packages installed in production containers.
dishka_module = types.ModuleType("dishka")
class AsyncContainer:  # pragma: no cover - import stub
    pass
dishka_module.AsyncContainer = AsyncContainer
sys.modules["dishka"] = dishka_module

event_bus_module = types.ModuleType("api.infrastructure.events.event_bus")
class EventBus:  # pragma: no cover - import stub
    pass
event_bus_module.EventBus = EventBus
sys.modules["api.infrastructure.events.event_bus"] = event_bus_module

raw_repo_module = types.ModuleType("api.infrastructure.artifacts.raw_artifact_repository")
class RawArtifactRepository:  # pragma: no cover - import stub
    pass
raw_repo_module.RawArtifactRepository = RawArtifactRepository
sys.modules["api.infrastructure.artifacts.raw_artifact_repository"] = raw_repo_module

from api.application.contracts import SafetyLevel
from api.application.pipeline.invocation import build_invocation, metadata, option_map, run_raw
from api.application.pipeline.context import PipelineContext
from api.application.pipeline.scan_node import ScanNode
from api.application.contracts import ExecutionMode
from api.infrastructure.events.event_types import EventType
from api.infrastructure.schemas.models.process_event import ProcessEvent


def _event(**overrides):
    action_id = uuid4()
    policy_id = uuid4()
    scope_id = uuid4()
    campaign_id = uuid4()
    event = {
        "event_id": str(uuid4()),
        "event": "katana_scan_requested",
        "program_id": str(uuid4()),
        "job_id": str(uuid4()),
        "run_id": str(uuid4()),
        "correlation_id": str(uuid4()),
        "action_id": str(action_id),
        "capability_id": "katana",
        "profile_id": "crawl-light",
        "safety_level": SafetyLevel.PASSIVE.value,
        "policy_decision_id": str(policy_id),
        "scope_decision_id": str(scope_id),
        "campaign_id": str(campaign_id),
        "requested_by": "api",
        "targets": ["https://example.com"],
        "options": {"depth": 4, "timeout": 10},
        "payload": {"options": {"depth": 3}},
    }
    event.update(overrides)
    return event


def test_build_invocation_from_action_event() -> None:
    event = _event()

    invocation = build_invocation(event, ["https://example.com"])

    assert invocation is not None
    assert invocation.capability_id == "katana"
    assert invocation.profile_id == "crawl-light"
    assert invocation.options == {"depth": 4, "timeout": 10}
    assert invocation.safety_level is SafetyLevel.PASSIVE
    assert metadata(invocation)["capability_id"] == "katana"


def test_build_invocation_ignores_downstream_events() -> None:
    event = {
        "event": "host_discovered",
        "program_id": str(uuid4()),
        "job_id": str(uuid4()),
        "run_id": str(uuid4()),
        "targets": ["api.example.com"],
    }

    assert build_invocation(event, ["api.example.com"]) is None


def test_option_map_prefers_nested_options() -> None:
    event = {
        "event": "katana_scan_requested",
        "depth": 9,
        "payload": {"options": {"depth": 2}},
        "options": {"depth": 4},
    }

    assert option_map(event) == {"depth": 4}


def test_run_raw_passes_only_supported_options() -> None:
    class Runner:
        def __init__(self) -> None:
            self.calls = []

        def run_raw(self, targets, depth=1):
            self.calls.append((targets, depth))
            async def stream():
                yield ProcessEvent(type="stdout", payload="ok")
            return stream()

    runner = Runner()
    invocation = build_invocation(_event(), ["https://example.com"])

    run_raw(runner, ["https://example.com"], invocation)

    assert runner.calls == [(["https://example.com"], 4)]


@pytest.mark.asyncio
async def test_scan_node_passes_invocation_options_to_runner() -> None:
    class Runner:
        def __init__(self) -> None:
            self.calls = []

        def run_raw(self, targets, depth=1):
            self.calls.append((targets, depth))
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
        def __init__(self, runner) -> None:
            self.runner = runner
            self.captured = []
            self.emitted = []

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

        async def emit(self, **kwargs):
            self.emitted.append(kwargs)

    runner = Runner()
    ctx = Context(runner)
    node = ScanNode(
        node_id="katana",
        event_in={EventType.KATANA_SCAN_REQUESTED},
        event_out={},
        runner_type=Runner,
        processor_type=Processor,
        parser_type=Parser,
        execution_mode=ExecutionMode.INLINE,
    )

    await node.execute(_event(), ctx)  # type: ignore[arg-type]

    assert runner.calls == [(["https://example.com"], 4)]
    assert ctx.captured[0]["metadata"]["capability_id"] == "katana"
    assert ctx.captured[0]["metadata"]["safety_level"] == "passive"
