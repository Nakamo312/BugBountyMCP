from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from api.application.contracts import ExecutionMode, ExecutionStatus, TerminalOutcome
from api.infrastructure.orchestration.run_claim_store import RunClaimStore


class EmptyResult:
    rowcount = 1


class RecordingSession:
    def __init__(self) -> None:
        self.calls = []
        self.statements = []
        self.commits = 0
        self.rollbacks = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, statement, parameters=None):
        self.calls.append((statement, parameters))
        self.statements.append(statement)
        return EmptyResult()

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1


class InsertRaceSession(RecordingSession):
    def __init__(self) -> None:
        super().__init__()
        self.raised_insert_race = False

    async def execute(self, statement, parameters=None):
        self.calls.append((statement, parameters))
        self.statements.append(statement)
        if not self.raised_insert_race and "INSERT INTO runs" in str(statement):
            self.raised_insert_race = True
            raise IntegrityError("duplicate run claim", {}, Exception("duplicate"))
        return EmptyResult()


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
        "target_count": 1,
        "work_key": "work-key",
        "campaign_id": None,
        "expansion_depth": 0,
        "max_expansion_depth": 5,
        "cooldown_seconds": 0,
        "token_cost": 1,
    }
    values.update(overrides)
    return values


def _trigger_params(session: RecordingSession) -> list[dict]:
    return [params for _, params in session.calls if isinstance(params, dict)]


@pytest.mark.asyncio
async def test_retryable_failed_work_claim_appends_coalesced_trigger_without_budget(
    monkeypatch,
) -> None:
    session = RecordingSession()
    store = RunClaimStore(lambda: session)
    existing_id = uuid4()

    async def retryable(*args, **kwargs):
        return {
            "id": existing_id,
            "claim_key": "existing-retry-claim",
            "status": ExecutionStatus.FAILED.value,
            "terminal_outcome": TerminalOutcome.TOOL_FAILED.value,
            "coalesced_triggers": [],
        }

    async def unexpected_budget_lock(*args, **kwargs):
        raise AssertionError("retry reuse must not lock or consume campaign budget")

    monkeypatch.setattr(store, "_select_node_run_claim", _none)
    monkeypatch.setattr(store, "_select_retryable_failed_work_claim", retryable)
    monkeypatch.setattr(store, "_lock_campaign_budget", unexpected_budget_lock)

    claim = await store.claim_node_run(
        **_claim_kwargs(
            coalesced_trigger={"event_id": "new-trigger"},
            retry_policy={
                "max_attempts": 2,
                "terminal_outcomes": [TerminalOutcome.TOOL_FAILED.value],
            },
        )
    )

    assert claim.run_id == existing_id
    assert claim.claim_key == "existing-retry-claim"
    assert claim.status == ExecutionStatus.FAILED
    assert claim.terminal_outcome == TerminalOutcome.TOOL_FAILED
    assert claim.created is False
    assert session.commits == 1
    assert session.rollbacks == 0
    params = _trigger_params(session)
    assert params
    assert params[-1]["run_id"] == existing_id
    assert '"reason":"retryable_failed_work_key"' in params[-1]["trigger_sample"]
    assert '"event_id":"new-trigger"' in params[-1]["trigger_sample"]


@pytest.mark.asyncio
async def test_insert_race_rechecks_claim_before_active_work_fallback_and_coalesces(
    monkeypatch,
) -> None:
    session = InsertRaceSession()
    store = RunClaimStore(lambda: session)
    existing_id = uuid4()
    select_claim_calls = 0
    active_work_calls = 0

    async def select_claim(*args, **kwargs):
        nonlocal select_claim_calls
        select_claim_calls += 1
        return None

    async def active_work(*args, **kwargs):
        nonlocal active_work_calls
        active_work_calls += 1
        return {
            "id": existing_id,
            "claim_key": "active-claim",
            "status": ExecutionStatus.RUNNING.value,
            "terminal_outcome": None,
            "coalesced_triggers": [],
        }

    async def unexpected_budget_lock(*args, **kwargs):
        raise AssertionError("insert-race fallback test should not touch budget")

    monkeypatch.setattr(store, "_select_node_run_claim", select_claim)
    monkeypatch.setattr(store, "_select_active_work_claim", active_work)
    monkeypatch.setattr(store, "_lock_campaign_budget", unexpected_budget_lock)

    claim = await store.claim_node_run(
        **_claim_kwargs(
            coalesced_trigger={"event_id": "racing-trigger"},
        )
    )

    assert session.raised_insert_race is True
    assert session.rollbacks == 1
    assert session.commits == 1
    assert select_claim_calls == 2
    assert active_work_calls == 1
    assert claim.run_id == existing_id
    assert claim.claim_key == "active-claim"
    assert claim.status == ExecutionStatus.RUNNING
    assert claim.created is False
    params = _trigger_params(session)
    assert params
    assert params[-1]["run_id"] == existing_id
    assert '"reason":"running_work_key"' in params[-1]["trigger_sample"]
    assert '"event_id":"racing-trigger"' in params[-1]["trigger_sample"]


@pytest.mark.asyncio
async def test_insert_race_without_existing_claim_or_active_work_reraises(
    monkeypatch,
) -> None:
    session = InsertRaceSession()
    store = RunClaimStore(lambda: session)

    monkeypatch.setattr(store, "_select_node_run_claim", _none)
    monkeypatch.setattr(store, "_select_active_work_claim", _none)

    async def unexpected_budget_lock(*args, **kwargs):
        raise AssertionError("unrecoverable insert-race test should not touch budget")

    monkeypatch.setattr(store, "_lock_campaign_budget", unexpected_budget_lock)

    with pytest.raises(IntegrityError):
        await store.claim_node_run(**_claim_kwargs())

    assert session.raised_insert_race is True
    assert session.rollbacks == 1
    assert session.commits == 0


@pytest.mark.asyncio
async def test_orchestration_store_claim_node_run_remains_compatibility_facade(
    monkeypatch,
) -> None:
    from api.application.contracts import NodeRunClaim
    from api.infrastructure.orchestration.store import OrchestrationStore

    session = RecordingSession()
    store = OrchestrationStore(lambda: session)
    expected = NodeRunClaim(
        run_id=uuid4(),
        claim_key="claim-key",
        status=ExecutionStatus.QUEUED,
        created=True,
    )
    delegated_kwargs = None

    async def delegated_claim_node_run(**kwargs):
        nonlocal delegated_kwargs
        delegated_kwargs = kwargs
        return expected

    monkeypatch.setattr(store.run_claims, "claim_node_run", delegated_claim_node_run)

    claim = await store.claim_node_run(**_claim_kwargs())

    assert claim is expected
    assert delegated_kwargs is not None
    assert delegated_kwargs["claim_key"] == "claim-key"
    assert delegated_kwargs["work_key"] == "work-key"
