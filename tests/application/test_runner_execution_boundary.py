from __future__ import annotations

from types import SimpleNamespace
from typing import get_type_hints

import pytest

from api.application.event_contracts import EventType
from api.application.pipeline.scan_execution import ScanRuntime, resolve_runner
from api.application.ports.runners import ToolRunnerFactoryPort, ToolRunnerPort, ToolRunnerRef


class FakeRunner:
    async def run_raw(self, targets, **options):
        if False:
            yield None

    async def run(self, targets, **options):
        if False:
            yield None


class FakeToolRunnerFactory:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def create(self, tool_name: str, **options):
        self.calls.append((tool_name, dict(options)))
        return FakeRunner()


class FakeContext:
    def __init__(self, factory: FakeToolRunnerFactory) -> None:
        self.factory = factory
        self.requested: list[object] = []

    async def get_service(self, service_type):
        self.requested.append(service_type)
        if service_type is ToolRunnerFactoryPort:
            return self.factory
        raise AssertionError(f"unexpected service request: {service_type!r}")


def _runtime(runner_type) -> ScanRuntime:
    return ScanRuntime(
        node_id="test",
        logger=SimpleNamespace(info=lambda *args, **kwargs: None),
        event_out_map={EventType.HOST_DISCOVERED: "hosts"},
        runner_type=runner_type,
        processor_type=None,
        ingestor_type=None,
        parser_factory=lambda: SimpleNamespace(),
        target_extractor=lambda event: ["example.com"],
        runner_name="test-runner",
        semaphore=SimpleNamespace(),
        enforce_execution_context=lambda event, invocation, context: None,
    )


@pytest.mark.asyncio
async def test_scan_execution_resolves_tool_runner_refs_through_application_port() -> None:
    factory = FakeToolRunnerFactory()
    ctx = FakeContext(factory)
    runner_ref = ToolRunnerRef("httpx", {"mode": "probe"}, "cli_tool:httpx:probe")

    runner = await resolve_runner(_runtime(runner_ref), ctx)  # type: ignore[arg-type]

    assert isinstance(runner, FakeRunner)
    assert factory.calls == [("httpx", {"mode": "probe"})]
    assert ctx.requested == [ToolRunnerFactoryPort]


def test_legacy_cli_tool_runner_ref_preserves_cli_string_form() -> None:
    from api.infrastructure.runners.cli_tool import CliToolRunnerRef

    ref = CliToolRunnerRef("httpx")

    assert isinstance(ref, ToolRunnerRef)
    assert str(ref) == "cli_tool:httpx"


def test_tool_runner_factory_port_returns_runner_with_raw_and_parsed_contract() -> None:
    hints = get_type_hints(ToolRunnerFactoryPort.create)

    assert hints["return"] is ToolRunnerPort
    assert hasattr(ToolRunnerPort, "run_raw")
    assert hasattr(ToolRunnerPort, "run")
