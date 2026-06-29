from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from api.application.contracts import ExecutionMode, ExecutionStatus, NodeRunClaim
from api.infrastructure.orchestration.run_claim_store import (
    CampaignBudgetSnapshot,
    RunClaimStore,
    _refilled_tokens,
)


class EmptyResult:
    rowcount = 1


class RecordingSession:
    def __init__(self) -> None:
        self.statements = []
        self.commits = 0
        self.rollbacks = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, statement):
        self.statements.append(statement)
        return EmptyResult()

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1


async def _none(*args, **kwargs):
    return None


def _claim_kwargs(**overrides):
    values = {
        "claim_key": "claim-key",
        "job_id": uuid4(),
        "program_id": uuid4(),
        "node_id": "httpx",
        "event_name": "host_discovered",
        "trigger_event_id": uuid4(),
        "input_fingerprint": "input-fingerprint",
        "target_fingerprint": "target-fingerprint",
        "execution_mode": ExecutionMode.SCHEDULED,
        "target_count": 3,
        "work_key": "work-key",
        "campaign_id": uuid4(),
        "expansion_depth": 2,
        "max_expansion_depth": 6,
        "cooldown_seconds": 300,
        "token_cost": 1,
    }
    values.update(overrides)
    return values


def test_token_bucket_refill_is_capped_by_capacity() -> None:
    now = datetime.now(timezone.utc)

    tokens = _refilled_tokens(
        tokens_available=2,
        token_capacity=10,
        token_refill_per_second=2,
        tokens_refilled_at=now - timedelta(seconds=10),
        now=now,
    )

    assert tokens == 10


def test_campaign_budget_snapshot_reports_first_exhausted_dimension() -> None:
    now = datetime.now(timezone.utc)
    snapshot = CampaignBudgetSnapshot(
        max_runs=2,
        max_targets=10,
        runs_consumed=2,
        targets_consumed=4,
        token_capacity=10.0,
        tokens_available=10.0,
        token_refill_per_second=1.0,
        tokens_refilled_at=now,
    )

    assert (
        snapshot.block_reason(target_count=1, token_cost=1)
        == "campaign_run_budget_exhausted"
    )

    snapshot = CampaignBudgetSnapshot(
        max_runs=2,
        max_targets=10,
        runs_consumed=1,
        targets_consumed=10,
        token_capacity=10.0,
        tokens_available=10.0,
        token_refill_per_second=1.0,
        tokens_refilled_at=now,
    )
    assert (
        snapshot.block_reason(target_count=1, token_cost=1)
        == "campaign_target_budget_exhausted"
    )

    snapshot = CampaignBudgetSnapshot(
        max_runs=2,
        max_targets=10,
        runs_consumed=1,
        targets_consumed=4,
        token_capacity=10.0,
        tokens_available=0.5,
        token_refill_per_second=1.0,
        tokens_refilled_at=now,
    )
    assert (
        snapshot.block_reason(target_count=1, token_cost=1)
        == "campaign_tokens_exhausted"
    )


@pytest.mark.asyncio
async def test_depth_limit_blocks_without_creating_run(monkeypatch) -> None:
    session = RecordingSession()
    store = RunClaimStore(lambda: session)
    monkeypatch.setattr(store, "_select_node_run_claim", _none)
    monkeypatch.setattr(store, "_select_retryable_failed_work_claim", _none)

    claim = await store.claim_node_run(
        **_claim_kwargs(expansion_depth=7, max_expansion_depth=6)
    )

    assert claim.created is False
    assert claim.blocked_reason == "depth_limit"
    assert claim.run_id is None
    assert session.statements == []


@pytest.mark.asyncio
async def test_campaign_budget_blocks_before_run_insert(monkeypatch) -> None:
    session = RecordingSession()
    store = RunClaimStore(lambda: session)
    monkeypatch.setattr(store, "_select_node_run_claim", _none)
    monkeypatch.setattr(store, "_select_retryable_failed_work_claim", _none)
    monkeypatch.setattr(store, "_select_recent_completed_work", _none)

    async def exhausted(*args, **kwargs):
        return {
            "max_runs": 1,
            "max_targets": 100,
            "runs_consumed": 1,
            "targets_consumed": 0,
            "token_capacity": 10.0,
            "tokens_available": 10.0,
            "token_refill_per_second": 1.0,
            "tokens_refilled_at": datetime.now(timezone.utc),
        }

    monkeypatch.setattr(store, "_lock_campaign_budget", exhausted)

    claim = await store.claim_node_run(**_claim_kwargs())

    assert claim.created is False
    assert claim.blocked_reason == "campaign_run_budget_exhausted"
    assert not any("INSERT INTO runs" in str(statement) for statement in session.statements)


@pytest.mark.asyncio
async def test_duplicate_claim_does_not_lock_or_consume_campaign_budget(
    monkeypatch,
) -> None:
    session = RecordingSession()
    store = RunClaimStore(lambda: session)
    existing = NodeRunClaim(
        run_id=uuid4(),
        claim_key="claim-key",
        status=ExecutionStatus.QUEUED,
    )

    async def select_existing(*args, **kwargs):
        return existing

    async def unexpected_budget_lock(*args, **kwargs):
        raise AssertionError("duplicate claim must not consume campaign budget")

    monkeypatch.setattr(store, "_select_node_run_claim", select_existing)
    monkeypatch.setattr(store, "_lock_campaign_budget", unexpected_budget_lock)

    claim = await store.claim_node_run(**_claim_kwargs())

    assert claim is existing
    assert session.commits == 0


@pytest.mark.asyncio
async def test_cooldown_blocks_recently_completed_work_before_budget(
    monkeypatch,
) -> None:
    session = RecordingSession()
    store = RunClaimStore(lambda: session)
    monkeypatch.setattr(store, "_select_node_run_claim", _none)

    async def recent_work(*args, **kwargs):
        return {"id": uuid4()}

    async def unexpected_budget_lock(*args, **kwargs):
        raise AssertionError("cooldown must be checked before campaign budget")

    monkeypatch.setattr(store, "_select_recent_completed_work", recent_work)
    monkeypatch.setattr(store, "_lock_campaign_budget", unexpected_budget_lock)

    claim = await store.claim_node_run(**_claim_kwargs())

    assert claim.created is False
    assert claim.blocked_reason == "cooldown_active"
    assert claim.run_id is None


@pytest.mark.asyncio
async def test_new_run_atomically_consumes_campaign_budget(monkeypatch) -> None:
    session = RecordingSession()
    store = RunClaimStore(lambda: session)
    monkeypatch.setattr(store, "_select_node_run_claim", _none)
    monkeypatch.setattr(store, "_select_recent_completed_work", _none)
    now = datetime.now(timezone.utc)

    async def available(*args, **kwargs):
        return {
            "max_runs": 10,
            "max_targets": 100,
            "runs_consumed": 2,
            "targets_consumed": 7,
            "token_capacity": 10.0,
            "tokens_available": 4.0,
            "token_refill_per_second": 1.0,
            "tokens_refilled_at": now,
        }

    monkeypatch.setattr(store, "_lock_campaign_budget", available)

    claim = await store.claim_node_run(
        **_claim_kwargs(target_count=3, token_cost=2)
    )

    assert claim.created is True
    assert claim.blocked_reason is None
    assert claim.run_id is not None
    assert session.commits == 1
    sql = [str(statement) for statement in session.statements]
    assert any("INSERT INTO runs" in statement for statement in sql)
    assert any("UPDATE campaigns" in statement for statement in sql)


@pytest.mark.asyncio
async def test_retryable_existing_work_does_not_consume_budget(monkeypatch) -> None:
    session = RecordingSession()
    store = RunClaimStore(lambda: session)
    monkeypatch.setattr(store, "_select_node_run_claim", _none)
    existing_id = uuid4()

    async def retryable(*args, **kwargs):
        return {
            "id": existing_id,
            "claim_key": "existing-claim",
            "status": ExecutionStatus.FAILED.value,
            "terminal_outcome": "tool_failed",
            "coalesced_triggers": [],
        }

    async def unexpected_budget_lock(*args, **kwargs):
        raise AssertionError("retry must not consume campaign budget")

    monkeypatch.setattr(store, "_select_retryable_failed_work_claim", retryable)
    monkeypatch.setattr(store, "_lock_campaign_budget", unexpected_budget_lock)

    claim = await store.claim_node_run(
        **_claim_kwargs(
            retry_policy={
                "max_attempts": 2,
                "terminal_outcomes": ["tool_failed"],
            }
        )
    )

    assert claim.run_id == existing_id
    assert claim.created is False
