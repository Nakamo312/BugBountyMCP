from __future__ import annotations

import asyncio
import sys
import types
from uuid import UUID, uuid4

import pytest

# Keep this unit test usable in minimal environments without replacing real
# modules when the project dependencies are installed.
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

from api.application.contracts import SafetyLevel
from api.application.pipeline.invocation import (
    RUNNER_CONTEXT_PAYLOAD_KEY,
    build_invocation,
    build_runner_context,
    metadata,
    option_map,
    run_raw,
)
from api.application.pipeline.context import PipelineContext
from api.application.pipeline.scope_policy import ScopePolicy
from api.application.pipeline.scan_node import ScanNode
from api.application.contracts import ExecutionMode
from api.application.event_contracts import EventType
from api.application.process_event_contracts import ProcessEvent


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
        "execution_budget": {
            "max_duration_seconds": 60,
            "max_targets": 20,
            "rate_per_second": 10,
            "concurrency": 2,
        },
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
    assert invocation.execution_budget.max_targets == 20
    assert invocation.execution_budget.concurrency == 2
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



def test_runner_context_uses_lineage_budget_without_root_action_options() -> None:
    class Runner:
        def __init__(self) -> None:
            self.calls = []

        def run_raw(self, targets, timeout=30, depth=1):
            self.calls.append((targets, timeout, depth))

            async def stream():
                yield ProcessEvent(type="stdout", payload="ok")

            return stream()

    root_action_id = uuid4()
    event = {
        "event": "host_discovered",
        "event_id": str(uuid4()),
        "program_id": str(uuid4()),
        "job_id": str(uuid4()),
        "run_id": str(uuid4()),
        "targets": ["https://api.example.com"],
        "payload": {
            "options": {"depth": 9},
            "execution_lineage": {
                "root_action_id": str(root_action_id),
                "root_capability_id": "katana",
                "root_profile_id": "crawl-light",
                "root_safety_level": "safe_active",
                "root_execution_budget": {"max_duration_seconds": 5},
            },
            RUNNER_CONTEXT_PAYLOAD_KEY: {"node_id": "httpx"},
        },
    }

    context = build_runner_context(
        event,
        ["https://api.example.com"],
        node_id="katana",
    )
    assert context is not None
    assert context.node_id == "katana"
    assert context.root_action_id == root_action_id
    assert context.root_capability_id == "katana"
    assert context.upstream_node_id == "httpx"

    runner = Runner()
    run_raw(runner, ["https://api.example.com"], context)

    assert runner.calls == [(["https://api.example.com"], 5, 1)]


def test_metadata_includes_runner_context_without_faking_capability() -> None:
    event = {
        "event": "host_discovered",
        "event_id": str(uuid4()),
        "program_id": str(uuid4()),
        "job_id": str(uuid4()),
        "run_id": str(uuid4()),
        "targets": ["api.example.com"],
        "payload": {
            "execution_lineage": {
                "root_action_id": str(uuid4()),
                "root_capability_id": "subfinder",
                "root_profile_id": "passive-recon",
                "root_safety_level": "passive",
            }
        },
    }

    context = build_runner_context(event, ["api.example.com"], node_id="httpx")
    assert context is not None

    data = metadata(None, context)

    assert data["node_id"] == "httpx"
    assert data["root_capability_id"] == "subfinder"
    assert "capability_id" not in data
    assert data["safety_level"] == "passive"

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
        parser_version = "test-parser-v2"

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
    assert ctx.captured[0]["parser_name"] == "Parser"
    assert ctx.captured[0]["parser_version"] == "test-parser-v2"
    assert ctx.captured[0]["scope_decision_id"] == UUID(
        ctx.captured[0]["metadata"]["scope_decision_id"]
    )


@pytest.mark.asyncio
async def test_scoped_scan_node_rejects_event_without_runner_lineage() -> None:
    class Runner:
        def __init__(self) -> None:
            self.calls = []

        def run_raw(self, targets):
            self.calls.append(targets)

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

        async def get_service(self, service_type):
            if service_type is Runner:
                return self.runner
            if service_type is Processor:
                return Processor()
            raise AssertionError(service_type)

        def capture_raw_stream(self, stream, **kwargs):
            return stream

        def ingest_context(self, raw_artifact_id=None):
            return None

    runner = Runner()
    node = ScanNode(
        node_id="httpx",
        event_in={EventType.HOST_DISCOVERED},
        event_out={},
        runner_type=Runner,
        processor_type=Processor,
        parser_type=Parser,
        execution_mode=ExecutionMode.INLINE,
        scope_policy=ScopePolicy.CONFIDENCE,
    )

    with pytest.raises(RuntimeError, match="requires complete runner context"):
        await node.execute(
            {
                "event": "host_discovered",
                "program_id": str(uuid4()),
                "job_id": str(uuid4()),
                "run_id": str(uuid4()),
                "targets": ["https://api.example.com"],
            },
            Context(runner),
        )

    assert runner.calls == []


@pytest.mark.asyncio
async def test_scoped_scan_node_accepts_complete_downstream_runner_context() -> None:
    class Runner:
        def __init__(self) -> None:
            self.calls = []

        def run_raw(self, targets, timeout=30):
            self.calls.append((targets, timeout))

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

    runner = Runner()
    node = ScanNode(
        node_id="httpx",
        event_in={EventType.HOST_DISCOVERED},
        event_out={},
        runner_type=Runner,
        processor_type=Processor,
        parser_type=Parser,
        execution_mode=ExecutionMode.INLINE,
        scope_policy=ScopePolicy.CONFIDENCE,
    )
    scope_decision_id = uuid4()
    policy_decision_id = uuid4()
    event = {
        "event": "host_discovered",
        "event_id": str(uuid4()),
        "program_id": str(uuid4()),
        "job_id": str(uuid4()),
        "run_id": str(uuid4()),
        "targets": ["https://api.example.com"],
        "payload": {
            "execution_lineage": {
                "root_action_id": str(uuid4()),
                "root_capability_id": "subfinder",
                "root_profile_id": "passive-recon",
                "root_safety_level": "passive",
                "policy_decision_id": str(policy_decision_id),
                "scope_decision_id": str(scope_decision_id),
                "root_execution_budget": {"max_duration_seconds": 7},
            },
            RUNNER_CONTEXT_PAYLOAD_KEY: {"node_id": "subfinder"},
        },
    }

    await node.execute(event, Context(runner))

    assert runner.calls == [(["https://api.example.com"], 7)]


@pytest.mark.asyncio
async def test_partial_action_event_is_rejected_before_runner_starts() -> None:
    class Runner:
        def __init__(self) -> None:
            self.calls = []

        def run_raw(self, targets):
            self.calls.append(targets)

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

        async def get_service(self, service_type):
            if service_type is Runner:
                return self.runner
            if service_type is Processor:
                return Processor()
            raise AssertionError(service_type)

        def capture_raw_stream(self, stream, **kwargs):
            return stream

        def ingest_context(self, raw_artifact_id=None):
            return None

    runner = Runner()
    node = ScanNode(
        node_id="legacy-passive",
        event_in={EventType.SUBDOMAIN_DISCOVERED},
        event_out={},
        runner_type=Runner,
        processor_type=Processor,
        parser_type=Parser,
        execution_mode=ExecutionMode.INLINE,
        scope_policy=ScopePolicy.NONE,
    )

    with pytest.raises(RuntimeError, match="incomplete action context"):
        await node.execute(
            {
                "event": "subdomain_discovered",
                "program_id": str(uuid4()),
                "job_id": str(uuid4()),
                "run_id": str(uuid4()),
                "action_id": str(uuid4()),
                "safety_level": SafetyLevel.ACTIVE.value,
                "targets": ["api.example.com"],
            },
            Context(runner),
        )

    assert runner.calls == []


@pytest.mark.asyncio
async def test_scan_node_runtime_concurrency_limits_runner_streams() -> None:
    class Runner:
        def __init__(self) -> None:
            self.calls = 0
            self.active = 0
            self.max_active = 0

        def run_raw(self, targets):
            async def stream():
                self.calls += 1
                self.active += 1
                self.max_active = max(self.max_active, self.active)
                try:
                    await asyncio.sleep(0.05)
                    yield ProcessEvent(type="stdout", payload=targets[0])
                finally:
                    self.active -= 1

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

        async def get_service(self, service_type):
            if service_type is Runner:
                return self.runner
            if service_type is Processor:
                return Processor()
            raise AssertionError(service_type)

        def capture_raw_stream(self, stream, **kwargs):
            return stream

        def ingest_context(self, raw_artifact_id=None):
            return None

    runner = Runner()
    node = ScanNode(
        node_id="httpx",
        event_in={EventType.HTTPX_SCAN_REQUESTED},
        event_out={},
        runner_type=Runner,
        processor_type=Processor,
        parser_type=Parser,
        execution_mode=ExecutionMode.INLINE,
        max_parallelism=4,
        runtime_concurrency=1,
    )

    event_one = _event(
        event="httpx_scan_requested",
        capability_id="httpx",
        profile_id="probe-lite",
        targets=["https://one.example.com"],
        options={},
    )
    event_two = _event(
        event="httpx_scan_requested",
        capability_id="httpx",
        profile_id="probe-lite",
        targets=["https://two.example.com"],
        options={},
    )

    await asyncio.gather(
        node.execute(event_one, Context(runner)),
        node.execute(event_two, Context(runner)),
    )

    assert runner.calls == 2
    assert runner.max_active == 1
