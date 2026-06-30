from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from api.application.contracts import EventEnvelope
from api.application.pipeline.context import PipelineContext
from api.application.pipeline.scope_policy import ScopePolicy
from api.application.utils.scope_checker import ScopeChecker
from api.domain.enums import RuleType, ScopeAction
from api.domain.models import ScopeRuleModel


class RecordingBus:
    def __init__(self) -> None:
        self.events: list[EventEnvelope] = []

    async def publish(self, event: EventEnvelope) -> None:
        self.events.append(event)


class ScopeFilterStub:
    def __init__(self, rules: list[ScopeRuleModel]) -> None:
        self._rules = rules

    async def filter_by_scope(
        self,
        *,
        program_id: UUID,
        targets: list[str],
        policy: ScopePolicy,
    ) -> tuple[list[str], list[str]]:
        scope_rules = [rule for rule in self._rules if rule.program_id == program_id]
        if not scope_rules:
            if policy == ScopePolicy.NONE:
                return targets, []
            return [], targets
        return ScopeChecker.filter_in_scope(targets, scope_rules)


@pytest.mark.asyncio
async def test_strict_pipeline_scope_blocks_targets_when_program_has_no_scope_rules() -> None:
    bus = RecordingBus()
    context = PipelineContext(
        node_id="httpx",
        bus=bus,
        scope_policy=ScopePolicy.STRICT,
        scope_filter=ScopeFilterStub([]),
    )

    await context.emit(
        event="http_service_discovered",
        targets=["https://api.example.com"],
        program_id=uuid4(),
    )

    assert bus.events == []


@pytest.mark.asyncio
async def test_confidence_pipeline_scope_blocks_targets_when_program_has_no_scope_rules() -> None:
    bus = RecordingBus()
    context = PipelineContext(
        node_id="katana",
        bus=bus,
        scope_policy=ScopePolicy.CONFIDENCE,
        scope_filter=ScopeFilterStub([]),
    )

    await context.emit(
        event="endpoint_discovered",
        targets=["https://api.example.com"],
        program_id=uuid4(),
    )

    assert bus.events == []


@pytest.mark.asyncio
async def test_approval_required_pipeline_scope_blocks_targets_when_program_has_no_scope_rules() -> None:
    bus = RecordingBus()
    context = PipelineContext(
        node_id="manual-review-node",
        bus=bus,
        scope_policy=ScopePolicy.APPROVAL_REQUIRED,
        scope_filter=ScopeFilterStub([]),
    )

    await context.emit(
        event="manual_review_requested",
        targets=["https://api.example.com"],
        program_id=uuid4(),
    )

    assert bus.events == []


@pytest.mark.asyncio
async def test_strict_pipeline_scope_keeps_only_matching_targets() -> None:
    bus = RecordingBus()
    program_id = uuid4()
    rules = [
        ScopeRuleModel(
            program_id=program_id,
            action=ScopeAction.INCLUDE,
            rule_type=RuleType.DOMAIN,
            pattern="*.example.com",
        )
    ]
    context = PipelineContext(
        node_id="httpx",
        bus=bus,
        scope_policy=ScopePolicy.STRICT,
        scope_filter=ScopeFilterStub(rules),
    )

    await context.emit(
        event="http_service_discovered",
        targets=["https://api.example.com", "https://evil.test"],
        program_id=program_id,
    )

    assert len(bus.events) == 1
    assert bus.events[0].targets == ["https://api.example.com"]
