from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy.dialects import postgresql

from api.application.agent_action_proposals import (
    AgentActionProposalDraft,
    AgentActionProposalFeedbackSignal,
    AgentActionProposalRecord,
    AgentActionProposalReviewDecision,
    AgentActionProposalReviewRequest,
    AgentActionProposalReviewService,
    AgentActionProposalService,
    AgentActionProposalStatus,
    AgentActionProposalType,
    proposal_record_ref,
)
from api.infrastructure.adapters.orm import metadata
from api.infrastructure.agent_action_proposals import AgentActionProposalStore


class RecordingProposalStore:
    def __init__(self) -> None:
        self.calls = []

    async def create_from_agent_task(self, *, proposal):
        self.calls.append(proposal)
        now = datetime.now(timezone.utc)
        from api.application.agent_action_proposals import AgentActionProposalRecord

        return AgentActionProposalRecord(
            proposal_id=proposal.proposal_id,
            program_id=proposal.program_id,
            campaign_id=proposal.campaign_id,
            task_id=proposal.task_id,
            source_message_id=proposal.source_message_id,
            agent_key=proposal.agent_key,
            proposal_key=proposal.proposal_key,
            proposal_type=proposal.draft.proposal_type,
            status=AgentActionProposalStatus.PENDING,
            title=proposal.title,
            summary=proposal.summary,
            rationale=proposal.rationale,
            capability_id=proposal.draft.capability_id,
            profile_id=proposal.draft.profile_id,
            priority=proposal.draft.priority,
            risk_level=proposal.draft.risk_level,
            expected_gain=proposal.draft.expected_gain or "",
            action_intent=proposal.draft.action_intent or "",
            action_params=proposal.draft.action_params,
            context_refs=proposal.context_refs,
            metadata={**proposal.metadata, "created_at_for_test": now.isoformat()},
            produced_by="test",
        )


@pytest.mark.asyncio
async def test_agent_action_proposal_service_sanitizes_and_preserves_boundary() -> None:
    store = RecordingProposalStore()
    service = AgentActionProposalService(store)
    program_id = uuid4()
    task_id = uuid4()
    message_id = uuid4()

    records = await service.write_agent_task_proposals(
        program_id=program_id,
        campaign_id=None,
        task_id=task_id,
        source_message_id=message_id,
        agent_key="Coordinator Agent",
        drafts=(
            AgentActionProposalDraft(
                proposal_type=AgentActionProposalType.INVESTIGATION_TASK,
                title="Проверить JS",
                summary="Сохранить предложение. Authorization: Bearer super-secret-token",
                rationale="Не запускать инструмент напрямую",
                context_refs=[{"kind": "artifact", "secret": "must-redact"}],
                metadata={"api_key": "secret-value"},
            ),
        ),
    )

    assert len(records) == 1
    record = records[0]
    assert record.status is AgentActionProposalStatus.PENDING
    assert record.proposal_type is AgentActionProposalType.INVESTIGATION_TASK
    assert record.agent_key == "coordinator-agent"
    assert "super-secret-token" not in record.summary
    assert record.context_refs[0]["secret"] == "[redacted]"
    assert record.metadata["api_key"] == "[redacted]"
    assert record.metadata["proposal_boundary"]["action_service_required"] is True
    ref = proposal_record_ref(record)
    assert ref["kind"] == "agent_action_proposal"
    assert ref["approval"] == "required_via_action_service"


class FeedbackAwareProposalStore(RecordingProposalStore):
    def __init__(self, signals):
        super().__init__()
        self.signals = tuple(signals)
        self.feedback_calls = []

    async def list_recent_review_feedback(self, *, program_id, campaign_id, agent_key, limit=50):
        self.feedback_calls.append((program_id, campaign_id, agent_key, limit))
        return self.signals


def _feedback_signal_for_test(*, feedback_type, confidence=0.95, **overrides):
    values = dict(
        proposal_id=uuid4(),
        campaign_id=uuid4(),
        agent_key="surface",
        proposal_type=AgentActionProposalType.INVESTIGATION_TASK,
        feedback_type=feedback_type,
        confidence=confidence,
        title="Разобрать изменения поверхности",
        capability_id=None,
        profile_id=None,
        action_intent="review_surface_delta",
        context_refs=({"kind": "surface", "id": "cluster-1"},),
        feedback_tags=("duplicate",),
        reason="already noise",
        created_at=datetime.now(timezone.utc),
    )
    values.update(overrides)
    return AgentActionProposalFeedbackSignal(**values)


@pytest.mark.asyncio
async def test_agent_action_proposal_service_suppresses_similar_prior_suppressed_feedback() -> None:
    campaign_id = uuid4()
    signal = _feedback_signal_for_test(
        feedback_type=AgentActionProposalReviewDecision.SUPPRESSED,
        campaign_id=campaign_id,
    )
    store = FeedbackAwareProposalStore([signal])
    service = AgentActionProposalService(store)

    records = await service.write_agent_task_proposals(
        program_id=uuid4(),
        campaign_id=campaign_id,
        task_id=uuid4(),
        source_message_id=uuid4(),
        agent_key="surface",
        drafts=(
            AgentActionProposalDraft(
                title="Разобрать изменения поверхности",
                summary="Повторно разобрать тот же surface delta",
                action_intent="review_surface_delta",
                context_refs=[{"kind": "surface", "id": "cluster-1"}],
            ),
        ),
    )

    assert records == ()
    assert store.calls == []
    assert store.feedback_calls[0][2] == "surface"


@pytest.mark.asyncio
async def test_agent_action_proposal_service_downranks_similar_prior_rejection() -> None:
    campaign_id = uuid4()
    signal = _feedback_signal_for_test(
        feedback_type=AgentActionProposalReviewDecision.REJECTED,
        confidence=0.9,
        campaign_id=campaign_id,
        reason="low gain",
        feedback_tags=("low-gain",),
    )
    store = FeedbackAwareProposalStore([signal])
    service = AgentActionProposalService(store)

    records = await service.write_agent_task_proposals(
        program_id=uuid4(),
        campaign_id=campaign_id,
        task_id=uuid4(),
        source_message_id=uuid4(),
        agent_key="surface",
        drafts=(
            AgentActionProposalDraft(
                title="Разобрать изменения поверхности",
                summary="Разобрать похожие surface changes",
                priority="high",
                action_intent="review_surface_delta",
                context_refs=[{"kind": "surface", "id": "cluster-2"}],
            ),
        ),
    )

    assert len(records) == 1
    record = records[0]
    assert record.priority == "medium"
    assert record.metadata["feedback_policy"]["decision"] == "down_ranked_due_to_prior_rejection"
    assert record.metadata["feedback_policy"]["matched_feedback_type"] == "rejected"
    assert store.calls[0].draft.priority == "medium"


def test_agent_action_proposal_table_declared_with_safe_constraints() -> None:
    assert "agent_action_proposals" in metadata.tables
    table = metadata.tables["agent_action_proposals"]
    for column in (
        "program_id",
        "campaign_id",
        "task_id",
        "source_message_id",
        "agent_key",
        "proposal_key",
        "proposal_type",
        "status",
        "title",
        "summary",
        "capability_id",
        "profile_id",
        "action_params",
        "context_refs",
        "metadata",
        "reviewed_by",
        "review_reason",
        "review_feedback",
        "reviewed_at",
    ):
        assert column in table.c
    assert "idx_agent_action_proposals_program_status_created" in {index.name for index in table.indexes}
    assert "idx_agent_action_proposals_task_status_created" in {index.name for index in table.indexes}
    assert "agent_action_proposal_feedback_events" in metadata.tables
    feedback_table = metadata.tables["agent_action_proposal_feedback_events"]
    for column in ("proposal_id", "program_id", "task_id", "feedback_type", "actor", "confidence", "feedback_tags"):
        assert column in feedback_table.c


def test_agent_action_proposal_migration_extends_live_thread_head() -> None:
    source = Path("alembic/versions/q2r3s4t5u6v7_add_agent_action_proposals.py").read_text(encoding="utf-8")
    assert 'down_revision = "p1q2r3s4t5u6"' in source
    assert '"agent_action_proposals"' in source
    assert '"agent_task_messages.id"' in source
    assert "ck_agent_action_proposals_status_valid" in source


class FakeMappingResult:
    def __init__(self, row):
        self.row = row

    def mappings(self):
        return self

    def one(self):
        return self.row


class FakeMappingListResult:
    def __init__(self, rows):
        self.rows = rows

    def mappings(self):
        return self

    def all(self):
        return self.rows


class FakeSession:
    def __init__(self) -> None:
        self.statements = []
        self.committed = False
        self.now = datetime.now(timezone.utc)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    async def execute(self, statement):
        self.statements.append(statement)
        params = statement.compile(dialect=postgresql.dialect()).params
        if "id" not in params:
            return FakeMappingListResult([])
        return FakeMappingResult(
            {
                "id": params["id"],
                "program_id": params["program_id"],
                "campaign_id": params["campaign_id"],
                "task_id": params["task_id"],
                "source_message_id": params["source_message_id"],
                "agent_key": params["agent_key"],
                "proposal_key": params["proposal_key"],
                "proposal_type": params["proposal_type"],
                "status": "pending",
                "title": params["title"],
                "summary": params["summary"],
                "rationale": params["rationale"],
                "capability_id": params["capability_id"],
                "profile_id": params["profile_id"],
                "priority": params["priority"],
                "risk_level": params["risk_level"],
                "expected_gain": params["expected_gain"],
                "action_intent": params["action_intent"],
                "action_params": params["action_params"],
                "context_refs": params["context_refs"],
                "metadata": params["metadata"],
                "produced_by": params["produced_by"],
            }
        )

    async def commit(self):
        self.committed = True


class FakeSessionFactory:
    def __init__(self, session: FakeSession) -> None:
        self.session = session

    def __call__(self):
        return self.session


@pytest.mark.asyncio
async def test_agent_action_proposal_store_uses_upsert_and_returns_record() -> None:
    from api.application.agent_action_proposals import AgentActionProposalService

    session = FakeSession()
    store = AgentActionProposalStore(FakeSessionFactory(session))
    service = AgentActionProposalService(store)

    records = await service.write_agent_task_proposals(
        program_id=uuid4(),
        campaign_id=uuid4(),
        task_id=uuid4(),
        source_message_id=uuid4(),
        agent_key="coordinator",
        drafts=(AgentActionProposalDraft(title="Next", summary="Save proposal"),),
    )

    assert session.committed is True
    assert records[0].title == "Next"
    compiled = str(session.statements[-1].compile(dialect=postgresql.dialect()))
    assert "INSERT INTO agent_action_proposals" in compiled
    assert "ON CONFLICT (proposal_key) DO UPDATE" in compiled

from api.application.action_catalog import CatalogDetail
from api.application.agent_action_proposals import (
    AgentActionProposalAcceptanceService,
    AgentActionProposalAcceptRequest,
    AgentActionProposalNotActionable,
    AgentActionProposalStateError,
)
from api.application.contracts import ActionStatus, ActionSubmission, PolicyDecision, PolicyDecisionStatus
from api.application.execution_limits import ExecutionBudget


class ProposalAcceptStore:
    def __init__(self, record):
        self.record = record
        self.accepted_calls = []

    async def create_from_agent_task(self, *, proposal):  # pragma: no cover
        raise AssertionError("not used")

    async def get_proposal(self, proposal_id):
        return self.record if self.record.proposal_id == proposal_id else None

    async def mark_accepted(self, *, proposal_id, action_id, accepted_by, reason):
        self.accepted_calls.append((proposal_id, action_id, accepted_by, reason))
        return self.record.model_copy(
            update={
                "status": AgentActionProposalStatus.ACCEPTED,
                "accepted_action_id": action_id,
                "accepted_by": accepted_by,
                "accepted_reason": reason,
            }
        )


class RecordingActionService:
    def __init__(self):
        self.requests = []

    async def request_action(self, action, *, confidence=0.5):
        self.requests.append((action, confidence))
        return ActionSubmission(
            action_id=action.action_id,
            status=ActionStatus.QUEUED,
            message="queued",
            campaign_id=action.campaign_id,
            correlation_id=action.correlation_id,
            policy_decision=PolicyDecision(
                action_id=action.action_id,
                status=PolicyDecisionStatus.ALLOWED,
                allowed_targets=action.targets,
            ),
        )


class ProposalCatalogService:
    def __init__(self):
        self.item_id = uuid4()
        self.calls = []

    async def find_detail(self, *, capability, profile):
        self.calls.append((capability, profile))
        return CatalogDetail(
            id=self.item_id,
            snapshot_id=uuid4(),
            capability=capability,
            profile=profile,
            capability_label=capability,
            profile_label=profile,
            safety_level="passive",
            requires_approval=False,
            mode="routed",
            queue="analysis",
            request_event=f"{capability}_scan_requested",
            default_profile=profile,
            scope_policy="confidence",
            execution_budget=ExecutionBudget(),
        )


def _proposal_record_for_accept(**overrides):
    now = datetime.now(timezone.utc)
    values = dict(
        proposal_id=uuid4(),
        program_id=uuid4(),
        campaign_id=uuid4(),
        task_id=uuid4(),
        source_message_id=uuid4(),
        agent_key="coordinator",
        proposal_key="agent-task:key",
        proposal_type=AgentActionProposalType.TOOL_ACTION,
        status=AgentActionProposalStatus.PENDING,
        title="Run linkfinder",
        summary="Check JS paths",
        rationale="New JS paths appeared",
        capability_id="linkfinder",
        profile_id="js-analysis",
        priority="medium",
        risk_level="low",
        expected_gain="hidden paths",
        action_intent="analyze-js",
        action_params={"targets": ["https://example.com/app.js"], "options": {"timeout": 5}},
        context_refs=[],
        metadata={"created_at_for_test": now.isoformat()},
        produced_by="test",
    )
    values.update(overrides)
    return AgentActionProposalRecord(**values)


@pytest.mark.asyncio
async def test_accept_agent_action_proposal_submits_canonical_action_request() -> None:
    record = _proposal_record_for_accept()
    store = ProposalAcceptStore(record)
    action_service = RecordingActionService()
    catalog = ProposalCatalogService()
    service = AgentActionProposalAcceptanceService(
        store=store,
        action_service=action_service,  # type: ignore[arg-type]
        catalog_service=catalog,  # type: ignore[arg-type]
    )

    result = await service.accept_as_action(
        proposal_id=record.proposal_id,
        request=AgentActionProposalAcceptRequest(
            accepted_by="alex",
            reason="looks useful",
            confidence=0.8,
            options={"timeout": 10},
        ),
    )

    assert result.proposal.status is AgentActionProposalStatus.ACCEPTED
    assert result.proposal.accepted_action_id == result.action_submission.action_id
    assert catalog.calls == [("linkfinder", "js-analysis")]
    action, confidence = action_service.requests[0]
    assert confidence == 0.8
    assert action.program_id == record.program_id
    assert action.campaign_id == record.campaign_id
    assert action.catalog_id == catalog.item_id
    assert action.targets == ["https://example.com/app.js"]
    assert action.options == {"timeout": 10}
    assert action.requested_by == "alex"
    assert action.metadata["agent_action_proposal"]["proposal_id"] == str(record.proposal_id)
    assert action.metadata["acceptance"]["boundary"]["submitted_through_action_service"] is True
    assert store.accepted_calls == [(record.proposal_id, action.action_id, "alex", "looks useful")]


@pytest.mark.asyncio
async def test_accept_agent_action_proposal_requires_concrete_capability_profile_and_targets() -> None:
    record = _proposal_record_for_accept(
        capability_id=None,
        profile_id=None,
        action_params={},
    )
    service = AgentActionProposalAcceptanceService(
        store=ProposalAcceptStore(record),
        action_service=RecordingActionService(),  # type: ignore[arg-type]
        catalog_service=ProposalCatalogService(),  # type: ignore[arg-type]
    )

    with pytest.raises(AgentActionProposalNotActionable):
        await service.accept_as_action(
            proposal_id=record.proposal_id,
            request=AgentActionProposalAcceptRequest(accepted_by="alex"),
        )

    with pytest.raises(AgentActionProposalNotActionable):
        await service.accept_as_action(
            proposal_id=record.proposal_id,
            request=AgentActionProposalAcceptRequest(
                accepted_by="alex",
                capability_id="httpx",
                profile_id="safe-web-probe",
            ),
        )


@pytest.mark.asyncio
async def test_accept_agent_action_proposal_rejects_non_pending_state() -> None:
    record = _proposal_record_for_accept(status=AgentActionProposalStatus.ACCEPTED)
    service = AgentActionProposalAcceptanceService(
        store=ProposalAcceptStore(record),
        action_service=RecordingActionService(),  # type: ignore[arg-type]
        catalog_service=ProposalCatalogService(),  # type: ignore[arg-type]
    )

    with pytest.raises(AgentActionProposalStateError):
        await service.accept_as_action(
            proposal_id=record.proposal_id,
            request=AgentActionProposalAcceptRequest(accepted_by="alex"),
        )


def test_agent_action_proposal_acceptance_route_is_registered() -> None:
    routes = open("src/api/presentation/rest/routes/__init__.py", encoding="utf-8").read()
    source = open("src/api/presentation/rest/routes/agent_action_proposals.py", encoding="utf-8").read()

    assert 'prefix="/api/v1/agent-action-proposals"' in routes
    assert '@router.post(\n    "/{proposal_id}/accept"' in source
    assert "AgentActionProposalAcceptanceService" in source
    service_source = open("src/api/application/agent_action_proposals.py", encoding="utf-8").read()
    assert "ActionRequestSubmitter" in service_source
    assert "forbidden_from_agent_proposal" in service_source
    assert '@router.post(\n    "/{proposal_id}/reject"' in source
    assert '@router.post(\n    "/{proposal_id}/suppress"' in source
    assert "AgentActionProposalReviewService" in source


class ProposalReviewStore:
    def __init__(self, record):
        self.record = record
        self.reviewed_calls = []

    async def create_from_agent_task(self, *, proposal):  # pragma: no cover
        raise AssertionError("not used")

    async def get_proposal(self, proposal_id):
        return self.record if self.record.proposal_id == proposal_id else None

    async def mark_accepted(self, *, proposal_id, action_id, accepted_by, reason):  # pragma: no cover
        raise AssertionError("not used")

    async def mark_reviewed(
        self,
        *,
        proposal_id,
        decision,
        reviewed_by,
        reason,
        confidence,
        feedback_tags,
        metadata,
    ):
        self.reviewed_calls.append(
            (proposal_id, decision, reviewed_by, reason, confidence, feedback_tags, metadata)
        )
        return self.record.model_copy(
            update={
                "status": AgentActionProposalStatus(decision.value),
                "reviewed_by": reviewed_by,
                "review_reason": reason,
                "review_feedback": metadata,
                "reviewed_at": datetime.now(timezone.utc),
            }
        )


@pytest.mark.asyncio
async def test_review_agent_action_proposal_records_rejection_feedback() -> None:
    record = _proposal_record_for_accept()
    store = ProposalReviewStore(record)
    service = AgentActionProposalReviewService(store=store)  # type: ignore[arg-type]

    result = await service.review(
        proposal_id=record.proposal_id,
        decision=AgentActionProposalReviewDecision.REJECTED,
        request=AgentActionProposalReviewRequest(
            reviewed_by="alex",
            reason="noise",
            confidence=0.9,
            feedback_tags=["duplicate", "low gain", "duplicate"],
            metadata={"ui": "proposal-card"},
        ),
    )

    assert result.proposal.status is AgentActionProposalStatus.REJECTED
    assert result.proposal.reviewed_by == "alex"
    assert result.proposal.review_reason == "noise"
    assert store.reviewed_calls[0][1] is AgentActionProposalReviewDecision.REJECTED
    assert store.reviewed_calls[0][5] == ["duplicate", "low-gain"]
    assert store.reviewed_calls[0][6]["feedback_boundary"]["feeds_future_ranking"] is True


@pytest.mark.asyncio
async def test_review_agent_action_proposal_suppresses_pending_only() -> None:
    record = _proposal_record_for_accept(status=AgentActionProposalStatus.ACCEPTED)
    service = AgentActionProposalReviewService(store=ProposalReviewStore(record))  # type: ignore[arg-type]

    with pytest.raises(AgentActionProposalStateError):
        await service.review(
            proposal_id=record.proposal_id,
            decision=AgentActionProposalReviewDecision.SUPPRESSED,
            request=AgentActionProposalReviewRequest(reviewed_by="alex"),
        )

class RecordingTaskThread:
    def __init__(self):
        self.replies = []

    async def append_agent_reply(self, *, task_id, request):
        self.replies.append((task_id, request))
        return None


@pytest.mark.asyncio
async def test_accept_agent_action_proposal_appends_visible_thread_decision() -> None:
    record = _proposal_record_for_accept()
    store = ProposalAcceptStore(record)
    action_service = RecordingActionService()
    catalog = ProposalCatalogService()
    thread = RecordingTaskThread()
    service = AgentActionProposalAcceptanceService(
        store=store,
        action_service=action_service,  # type: ignore[arg-type]
        catalog_service=catalog,  # type: ignore[arg-type]
        task_thread=thread,  # type: ignore[arg-type]
    )

    result = await service.accept_as_action(
        proposal_id=record.proposal_id,
        request=AgentActionProposalAcceptRequest(accepted_by="alex", reason="good next step"),
    )

    assert result.proposal.status is AgentActionProposalStatus.ACCEPTED
    assert len(thread.replies) == 1
    task_id, reply = thread.replies[0]
    assert task_id == record.task_id
    assert reply.agent_key == "proposal-feedback"
    assert reply.message_kind.value == "decision"
    assert "Предложение принято" in reply.body
    assert reply.proposal_refs[0]["proposal_id"] == str(record.proposal_id)
    assert reply.action_refs[0]["action_id"] == str(result.action_submission.action_id)
    assert reply.decision_refs[0]["decision"] == "accepted"
    assert reply.metadata["feedback_visible_in_live_thread"] is True
    assert reply.metadata["boundary"]["submitted_through_action_service"] is True


@pytest.mark.asyncio
async def test_review_agent_action_proposal_appends_visible_suppress_event() -> None:
    record = _proposal_record_for_accept()
    store = ProposalReviewStore(record)
    thread = RecordingTaskThread()
    service = AgentActionProposalReviewService(store=store, task_thread=thread)  # type: ignore[arg-type]

    result = await service.review(
        proposal_id=record.proposal_id,
        decision=AgentActionProposalReviewDecision.SUPPRESSED,
        request=AgentActionProposalReviewRequest(
            reviewed_by="alex",
            reason="повторяет шум",
            confidence=0.95,
            feedback_tags=["noise"],
        ),
    )

    assert result.proposal.status is AgentActionProposalStatus.SUPPRESSED
    assert len(thread.replies) == 1
    task_id, reply = thread.replies[0]
    assert task_id == record.task_id
    assert reply.agent_key == "proposal-feedback"
    assert reply.message_kind.value == "decision"
    assert "Предложение подавлено" in reply.body
    assert "повторяет шум" in reply.body
    assert reply.proposal_refs[0]["proposal_id"] == str(record.proposal_id)
    assert reply.decision_refs[0]["decision"] == "suppressed"
    assert reply.decision_refs[0]["feedback_tags"] == ["noise"]
    assert reply.metadata["feedback_boundary"]["feeds_future_ranking"] is True
