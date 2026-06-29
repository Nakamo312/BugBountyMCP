from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from api.application.action_experience_proposals import (
    ActionExperienceProposalAcceptRequest,
    ActionExperienceProposalAcceptanceService,
    ActionExperienceProposalNotActionable,
    ActionExperienceProposalRecord,
    ActionExperienceProposalReviewDecision,
    ActionExperienceProposalReviewRequest,
    ActionExperienceProposalReviewService,
    ActionExperienceProposalStateError,
    ActionExperienceProposalStatus,
)
from api.application.contracts import ActionStatus, ActionSubmission, PolicyDecision, PolicyDecisionStatus


def _proposal(
    *,
    status: ActionExperienceProposalStatus = ActionExperienceProposalStatus.PENDING,
    explanation: dict | None = None,
) -> ActionExperienceProposalRecord:
    return ActionExperienceProposalRecord(
        proposal_id=uuid4(),
        proposal_run_id=uuid4(),
        program_id=uuid4(),
        campaign_id=uuid4(),
        source_outcome_id=uuid4(),
        source_action_id=uuid4(),
        source_job_id=uuid4(),
        source_run_id=uuid4(),
        proposal_key="experience-proposal:key",
        status=status,
        rank=2,
        capability_id="katana",
        profile_id="safe-crawl",
        utility_score=6.5,
        sample_count=4,
        avg_similarity=0.42,
        avg_information_gain_score=3.7,
        human_positive_rate=0.25,
        human_stop_rate=0.0,
        explanation=explanation or {"source": "neo4j-jaccard-surface-component"},
        produced_by="action-experience-proposal-worker",
    )


class FakeStore:
    def __init__(self, proposal: ActionExperienceProposalRecord | None) -> None:
        self.proposal = proposal
        self.claim_acceptance_calls: list[dict[str, object]] = []
        self.retry_acceptance_calls: list[dict[str, object]] = []
        self.mark_accepted_calls: list[dict[str, object]] = []
        self.mark_accept_failed_calls: list[dict[str, object]] = []
        self.mark_reviewed_calls: list[dict[str, object]] = []

    async def get_proposal(self, proposal_id: UUID) -> ActionExperienceProposalRecord | None:
        if self.proposal is None or proposal_id != self.proposal.proposal_id:
            return None
        return self.proposal

    async def claim_acceptance(self, **kwargs) -> ActionExperienceProposalRecord | None:
        self.claim_acceptance_calls.append(kwargs)
        if self.proposal is None or self.proposal.status is not ActionExperienceProposalStatus.PENDING:
            return None
        self.proposal = self._with_acceptance_payload(ActionExperienceProposalStatus.ACCEPTING, kwargs)
        return self.proposal

    async def retry_acceptance(self, **kwargs) -> ActionExperienceProposalRecord | None:
        self.retry_acceptance_calls.append(kwargs)
        if self.proposal is None or self.proposal.status is not ActionExperienceProposalStatus.ACCEPT_FAILED:
            return None
        self.proposal = self._with_acceptance_payload(ActionExperienceProposalStatus.ACCEPTING, kwargs)
        return self.proposal

    async def mark_accepted(self, **kwargs) -> ActionExperienceProposalRecord | None:
        self.mark_accepted_calls.append(kwargs)
        if self.proposal is None or self.proposal.status is not ActionExperienceProposalStatus.ACCEPTING:
            return None
        self.proposal = self._with_acceptance_payload(ActionExperienceProposalStatus.ACCEPTED, kwargs)
        return self.proposal

    async def mark_accept_failed(self, **kwargs) -> ActionExperienceProposalRecord | None:
        self.mark_accept_failed_calls.append(kwargs)
        if self.proposal is None or self.proposal.status is not ActionExperienceProposalStatus.ACCEPTING:
            return None
        self.proposal = self._with_acceptance_payload(ActionExperienceProposalStatus.ACCEPT_FAILED, kwargs)
        return self.proposal

    def _with_acceptance_payload(self, status: ActionExperienceProposalStatus, payload: dict[str, object]):
        assert self.proposal is not None
        explanation = dict(self.proposal.explanation)
        metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
        explanation["acceptance"] = {
            "accepted_action_id": str(payload.get("action_id")),
            "actor": payload.get("accepted_by"),
            "reason": payload.get("reason"),
            "confidence": payload.get("confidence"),
            "metadata": metadata,
            "accepted_at": "2026-06-29T00:00:00+00:00",
        }
        return self.proposal.model_copy(update={"status": status, "explanation": explanation})

    async def mark_reviewed(self, **kwargs) -> ActionExperienceProposalRecord | None:
        self.mark_reviewed_calls.append(kwargs)
        if self.proposal is None:
            return None
        self.proposal = self.proposal.model_copy(update={"status": ActionExperienceProposalStatus(kwargs["status"].value)})
        return self.proposal


class FakeCatalog:
    def __init__(self) -> None:
        self.detail = SimpleNamespace(id=uuid4())
        self.calls: list[dict[str, str]] = []

    async def find_detail(self, *, capability: str, profile: str):
        self.calls.append({"capability": capability, "profile": profile})
        return self.detail


class FakeActionService:
    def __init__(self) -> None:
        self.calls: list[tuple[object, float]] = []
        self.existing_submissions: dict[UUID, ActionSubmission] = {}

    async def get_action_submission(self, action_id: UUID) -> ActionSubmission | None:
        return self.existing_submissions.get(action_id)

    async def request_action(self, action, *, confidence: float = 0.5) -> ActionSubmission:
        self.calls.append((action, confidence))
        submission = ActionSubmission(
            action_id=action.action_id,
            status=ActionStatus.QUEUED,
            message="queued",
            campaign_id=action.campaign_id,
            correlation_id=action.correlation_id,
            policy_decision=PolicyDecision(
                action_id=action.action_id,
                status=PolicyDecisionStatus.ALLOWED,
            ),
        )
        self.existing_submissions[action.action_id] = submission
        return submission


@pytest.mark.asyncio
async def test_accept_experience_proposal_submits_action_through_action_service() -> None:
    proposal = _proposal()
    store = FakeStore(proposal)
    catalog = FakeCatalog()
    action_service = FakeActionService()
    service = ActionExperienceProposalAcceptanceService(
        store=store,
        action_service=action_service,
        catalog_service=catalog,
    )

    result = await service.accept_as_action(
        proposal_id=proposal.proposal_id,
        request=ActionExperienceProposalAcceptRequest(
            accepted_by="operator",
            reason="component candidate looks useful",
            confidence=0.8,
            targets=["https://example.test"],
            options={"depth": 1},
            metadata={"ticket": "T-1"},
        ),
    )

    assert result.proposal.status is ActionExperienceProposalStatus.ACCEPTED
    assert result.action_submission.status is ActionStatus.QUEUED
    assert catalog.calls == [{"capability": "katana", "profile": "safe-crawl"}]
    assert len(action_service.calls) == 1
    action, confidence = action_service.calls[0]
    assert confidence == 0.8
    assert action.catalog_id == catalog.detail.id
    assert action.program_id == proposal.program_id
    assert action.campaign_id == proposal.campaign_id
    assert action.targets == ["https://example.test"]
    assert action.options == {"depth": 1}
    assert action.action_id == result.action_submission.action_id
    assert action.metadata["source"] == "action_experience_proposal_accept"
    assert action.metadata["action_experience_proposal"]["proposal_id"] == str(proposal.proposal_id)
    assert action.metadata["acceptance"]["accepted_action_id"] == str(action.action_id)
    assert action.metadata["acceptance"]["boundary"]["submitted_through_action_service"] is True
    assert store.claim_acceptance_calls[0]["action_id"] == result.action_submission.action_id
    assert store.mark_accepted_calls[0]["action_id"] == result.action_submission.action_id


@pytest.mark.asyncio
async def test_accept_experience_proposal_does_not_submit_action_when_claim_loses() -> None:
    class LosingClaimStore(FakeStore):
        async def claim_acceptance(self, **kwargs) -> ActionExperienceProposalRecord | None:
            self.claim_acceptance_calls.append(kwargs)
            return None

    proposal = _proposal()
    store = LosingClaimStore(proposal)
    action_service = FakeActionService()
    catalog = FakeCatalog()
    service = ActionExperienceProposalAcceptanceService(
        store=store,
        action_service=action_service,
        catalog_service=catalog,
    )

    with pytest.raises(ActionExperienceProposalStateError, match="could not be claimed"):
        await service.accept_as_action(
            proposal_id=proposal.proposal_id,
            request=ActionExperienceProposalAcceptRequest(targets=["https://example.test"]),
        )

    assert store.claim_acceptance_calls
    assert catalog.calls == []
    assert action_service.calls == []


@pytest.mark.asyncio
async def test_accept_experience_proposal_marks_accept_failed_when_action_submission_fails() -> None:
    class FailingActionService(FakeActionService):
        async def request_action(self, action, *, confidence: float = 0.5) -> ActionSubmission:
            self.calls.append((action, confidence))
            raise RuntimeError("queue unavailable")

    proposal = _proposal()
    store = FakeStore(proposal)
    action_service = FailingActionService()
    service = ActionExperienceProposalAcceptanceService(
        store=store,
        action_service=action_service,
        catalog_service=FakeCatalog(),
    )

    with pytest.raises(RuntimeError, match="queue unavailable"):
        await service.accept_as_action(
            proposal_id=proposal.proposal_id,
            request=ActionExperienceProposalAcceptRequest(targets=["https://example.test"]),
        )

    assert len(action_service.calls) == 1
    assert len(store.claim_acceptance_calls) == 1
    assert len(store.mark_accept_failed_calls) == 1
    assert store.proposal is not None
    assert store.proposal.status is ActionExperienceProposalStatus.ACCEPT_FAILED


@pytest.mark.asyncio
async def test_accepting_proposal_recovers_existing_action_submission() -> None:
    action_id = uuid4()
    proposal = _proposal(
        status=ActionExperienceProposalStatus.ACCEPTING,
        explanation={
            "acceptance": {
                "accepted_action_id": str(action_id),
                "metadata": {"acceptance": {"targets": ["https://stored.example"]}},
            }
        },
    )
    store = FakeStore(proposal)
    action_service = FakeActionService()
    action_service.existing_submissions[action_id] = ActionSubmission(
        action_id=action_id,
        status=ActionStatus.QUEUED,
        message="existing",
        policy_decision=PolicyDecision(action_id=action_id, status=PolicyDecisionStatus.ALLOWED),
    )
    service = ActionExperienceProposalAcceptanceService(
        store=store,
        action_service=action_service,
        catalog_service=FakeCatalog(),
    )

    result = await service.accept_as_action(
        proposal_id=proposal.proposal_id,
        request=ActionExperienceProposalAcceptRequest(targets=[]),
    )

    assert result.proposal.status is ActionExperienceProposalStatus.ACCEPTED
    assert result.action_submission.action_id == action_id
    assert action_service.calls == []
    assert store.claim_acceptance_calls == []
    assert store.mark_accepted_calls[0]["action_id"] == action_id


@pytest.mark.asyncio
async def test_accepting_resume_rejects_mismatched_new_targets() -> None:
    action_id = uuid4()
    proposal = _proposal(
        status=ActionExperienceProposalStatus.ACCEPTING,
        explanation={
            "acceptance": {
                "accepted_action_id": str(action_id),
                "metadata": {
                    "acceptance": {
                        "accepted_action_id": str(action_id),
                        "accepted_by": "operator",
                        "targets": ["https://stored.example"],
                        "options": {"depth": 1},
                        "budget": None,
                        "confidence": 0.8,
                    }
                },
                "accepted_at": "2026-06-29T00:00:00+00:00",
            }
        },
    )
    store = FakeStore(proposal)
    action_service = FakeActionService()
    service = ActionExperienceProposalAcceptanceService(
        store=store,
        action_service=action_service,
        catalog_service=FakeCatalog(),
    )

    with pytest.raises(ActionExperienceProposalStateError, match="different targets"):
        await service.accept_as_action(
            proposal_id=proposal.proposal_id,
            request=ActionExperienceProposalAcceptRequest(
                targets=["https://new.example"],
                options={"depth": 1},
            ),
        )

    assert action_service.calls == []
    assert store.mark_accepted_calls == []


@pytest.mark.asyncio
async def test_accepting_resume_without_visible_submission_waits_instead_of_resubmitting() -> None:
    action_id = uuid4()
    proposal = _proposal(
        status=ActionExperienceProposalStatus.ACCEPTING,
        explanation={
            "acceptance": {
                "accepted_action_id": str(action_id),
                "metadata": {
                    "acceptance": {
                        "accepted_action_id": str(action_id),
                        "accepted_by": "operator",
                        "targets": ["https://stored.example"],
                        "options": {},
                        "budget": None,
                        "confidence": 0.8,
                    }
                },
                "accepted_at": "2999-01-01T00:00:00+00:00",
            }
        },
    )
    store = FakeStore(proposal)
    action_service = FakeActionService()
    service = ActionExperienceProposalAcceptanceService(
        store=store,
        action_service=action_service,
        catalog_service=FakeCatalog(),
    )

    with pytest.raises(ActionExperienceProposalStateError, match="already in progress"):
        await service.accept_as_action(
            proposal_id=proposal.proposal_id,
            request=ActionExperienceProposalAcceptRequest(targets=[]),
        )

    assert action_service.calls == []
    assert store.mark_accept_failed_calls == []


@pytest.mark.asyncio
async def test_accept_failed_proposal_can_be_retried() -> None:
    proposal = _proposal(status=ActionExperienceProposalStatus.ACCEPT_FAILED)
    store = FakeStore(proposal)
    action_service = FakeActionService()
    service = ActionExperienceProposalAcceptanceService(
        store=store,
        action_service=action_service,
        catalog_service=FakeCatalog(),
    )

    result = await service.retry_accept_failed_as_action(
        proposal_id=proposal.proposal_id,
        request=ActionExperienceProposalAcceptRequest(targets=["https://retry.example"]),
    )

    assert result.proposal.status is ActionExperienceProposalStatus.ACCEPTED
    assert len(store.retry_acceptance_calls) == 1
    assert len(action_service.calls) == 1


@pytest.mark.asyncio
async def test_accept_failed_cannot_be_retried_through_accept_command() -> None:
    proposal = _proposal(status=ActionExperienceProposalStatus.ACCEPT_FAILED)
    store = FakeStore(proposal)
    service = ActionExperienceProposalAcceptanceService(
        store=store,
        action_service=FakeActionService(),
        catalog_service=FakeCatalog(),
    )

    with pytest.raises(ActionExperienceProposalStateError, match="retry-accept"):
        await service.accept_as_action(
            proposal_id=proposal.proposal_id,
            request=ActionExperienceProposalAcceptRequest(targets=["https://retry.example"]),
        )

    assert store.retry_acceptance_calls == []


@pytest.mark.asyncio
async def test_accept_experience_proposal_requires_explicit_targets() -> None:
    proposal = _proposal()
    service = ActionExperienceProposalAcceptanceService(
        store=FakeStore(proposal),
        action_service=FakeActionService(),
        catalog_service=FakeCatalog(),
    )

    with pytest.raises(ActionExperienceProposalNotActionable, match="explicit targets"):
        await service.accept_as_action(
            proposal_id=proposal.proposal_id,
            request=ActionExperienceProposalAcceptRequest(targets=[]),
        )


@pytest.mark.asyncio
async def test_accept_experience_proposal_rejects_non_pending_state() -> None:
    proposal = _proposal(status=ActionExperienceProposalStatus.SUPPRESSED)
    service = ActionExperienceProposalAcceptanceService(
        store=FakeStore(proposal),
        action_service=FakeActionService(),
        catalog_service=FakeCatalog(),
    )

    with pytest.raises(ActionExperienceProposalStateError, match="not acceptable"):
        await service.accept_as_action(
            proposal_id=proposal.proposal_id,
            request=ActionExperienceProposalAcceptRequest(targets=["https://example.test"]),
        )


@pytest.mark.asyncio
async def test_reject_experience_proposal_records_review_without_action_submission() -> None:
    proposal = _proposal()
    store = FakeStore(proposal)
    action_service = FakeActionService()
    service = ActionExperienceProposalReviewService(store=store)

    result = await service.review(
        proposal_id=proposal.proposal_id,
        decision=ActionExperienceProposalReviewDecision.REJECTED,
        request=ActionExperienceProposalReviewRequest(
            reviewed_by="operator",
            reason="not useful for this branch",
            confidence=0.7,
            metadata={"ticket": "R-1"},
        ),
    )

    assert result.proposal.status is ActionExperienceProposalStatus.REJECTED
    assert result.boundary["proposal_direct_execution"] is False
    assert result.boundary["source_outcome_rewritten"] is False
    assert action_service.calls == []
    assert store.mark_reviewed_calls[0]["status"] is ActionExperienceProposalReviewDecision.REJECTED
    assert store.mark_reviewed_calls[0]["metadata"]["review"]["boundary"]["consumed_by_review_priors"] is True


@pytest.mark.asyncio
async def test_suppress_experience_proposal_rejects_non_pending_state() -> None:
    proposal = _proposal(status=ActionExperienceProposalStatus.ACCEPTED)
    service = ActionExperienceProposalReviewService(store=FakeStore(proposal))

    with pytest.raises(ActionExperienceProposalStateError, match="not pending"):
        await service.review(
            proposal_id=proposal.proposal_id,
            decision=ActionExperienceProposalReviewDecision.SUPPRESSED,
            request=ActionExperienceProposalReviewRequest(),
        )


def test_action_experience_proposal_route_is_registered() -> None:
    source = __import__("pathlib").Path("src/api/presentation/rest/routes/__init__.py").read_text(encoding="utf-8")
    assert "action_experience_proposals_router" in source
    assert "/api/v1/action-experience-proposals" in source
