"""Recoverable acceptance saga for action-experience proposals."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from api.application.contracts import ActionKind, ActionRequest, ActionSubmission
from api.application.research.sanitizer import sanitize_json

from .action_experience_proposals import (
    ACTION_EXPERIENCE_PROPOSAL_ACCEPT_SCHEMA_VERSION,
    ActionCatalogResolver,
    ActionExperienceProposalAcceptRequest,
    ActionExperienceProposalAcceptResult,
    ActionExperienceProposalNotActionable,
    ActionExperienceProposalNotFound,
    ActionExperienceProposalRecord,
    ActionExperienceProposalStateError,
    ActionExperienceProposalStatus,
    ActionExperienceProposalStore,
    ActionRequestSubmitter,
)

_ACCEPTANCE_STALE_AFTER = timedelta(minutes=5)


class ActionExperienceProposalAcceptanceService:
    """Accept graph-experience proposals by submitting canonical ActionRequests.

    Acceptance is a recoverable saga. Pending proposals are first claimed with a
    deterministic action id and a stored acceptance command. If the process dies
    while the proposal is ``accepting``, later calls resume from the stored
    command instead of rebuilding audit metadata from a new request.
    """

    def __init__(
        self,
        *,
        store: ActionExperienceProposalStore,
        action_service: ActionRequestSubmitter,
        catalog_service: ActionCatalogResolver,
    ) -> None:
        self.store = store
        self.action_service = action_service
        self.catalog_service = catalog_service

    async def accept_as_action(
        self,
        *,
        proposal_id: UUID,
        request: ActionExperienceProposalAcceptRequest,
    ) -> ActionExperienceProposalAcceptResult:
        proposal = await self._load_accept_or_resume_proposal(proposal_id)
        if proposal.status is ActionExperienceProposalStatus.ACCEPT_FAILED:
            raise ActionExperienceProposalStateError(
                f"Action experience proposal {proposal_id} is accept_failed; use retry-accept"
            )
        return await self._accept_or_resume(proposal=proposal, request=request, retry_failed=False)

    async def retry_accept_failed_as_action(
        self,
        *,
        proposal_id: UUID,
        request: ActionExperienceProposalAcceptRequest,
    ) -> ActionExperienceProposalAcceptResult:
        """Explicit retry command for proposals left in ``accept_failed``."""

        proposal = await self.store.get_proposal(proposal_id)
        if proposal is None:
            raise ActionExperienceProposalNotFound(f"Action experience proposal not found: {proposal_id}")
        if proposal.status is not ActionExperienceProposalStatus.ACCEPT_FAILED:
            raise ActionExperienceProposalStateError(
                f"Action experience proposal {proposal_id} is not accept_failed: {proposal.status.value}"
            )
        return await self._accept_or_resume(proposal=proposal, request=request, retry_failed=True)

    async def _accept_or_resume(
        self,
        *,
        proposal: ActionExperienceProposalRecord,
        request: ActionExperienceProposalAcceptRequest,
        retry_failed: bool,
    ) -> ActionExperienceProposalAcceptResult:
        command = self._acceptance_command(proposal, request, retry_failed=retry_failed)
        claimed, owns_submission = await self._claim_or_resume(
            proposal, command, request=request, retry_failed=retry_failed
        )
        submission = await self._existing_submission(command.action_id)
        if submission is None:
            submission = await self._submit_or_wait(
                claimed, command, request=request, owns_submission=owns_submission
            )
        accepted = await self._mark_accepted_or_recover(claimed, command, submission)
        return ActionExperienceProposalAcceptResult(proposal=accepted, action_submission=submission)

    async def _load_accept_or_resume_proposal(self, proposal_id: UUID) -> ActionExperienceProposalRecord:
        proposal = await self.store.get_proposal(proposal_id)
        if proposal is None:
            raise ActionExperienceProposalNotFound(f"Action experience proposal not found: {proposal_id}")
        if proposal.status not in {
            ActionExperienceProposalStatus.PENDING,
            ActionExperienceProposalStatus.ACCEPTING,
            ActionExperienceProposalStatus.ACCEPT_FAILED,
        }:
            raise ActionExperienceProposalStateError(
                f"Action experience proposal {proposal_id} is not acceptable: {proposal.status.value}"
            )
        return proposal

    async def _claim_or_resume(
        self,
        proposal: ActionExperienceProposalRecord,
        command: "AcceptanceCommand",
        *,
        request: ActionExperienceProposalAcceptRequest,
        retry_failed: bool,
    ) -> tuple[ActionExperienceProposalRecord, bool]:
        if proposal.status is ActionExperienceProposalStatus.ACCEPTING:
            self._validate_resume_request(proposal, command, request)
            return proposal, False
        claim = self.store.retry_acceptance if retry_failed else self.store.claim_acceptance
        claimed = await claim(
            proposal_id=proposal.proposal_id,
            action_id=command.action_id,
            accepted_by=command.accepted_by,
            reason=command.reason,
            confidence=command.confidence,
            metadata=command.metadata,
        )
        if claimed is None:
            raise ActionExperienceProposalStateError(
                f"Action experience proposal {proposal.proposal_id} could not be claimed for acceptance"
            )
        return claimed, True

    async def _submit_or_wait(
        self,
        proposal: ActionExperienceProposalRecord,
        command: "AcceptanceCommand",
        *,
        request: ActionExperienceProposalAcceptRequest,
        owns_submission: bool,
    ) -> ActionSubmission:
        if not owns_submission and proposal.status is ActionExperienceProposalStatus.ACCEPTING and not self._acceptance_is_stale(proposal):
            raise ActionExperienceProposalStateError(
                f"Action experience proposal {proposal.proposal_id} acceptance is already in progress; retry later"
            )
        try:
            return await self._submit_action(proposal, command)
        except Exception as exc:
            recovered = await self._existing_submission(command.action_id)
            if recovered is not None:
                return recovered
            await self.store.mark_accept_failed(
                proposal_id=proposal.proposal_id,
                action_id=command.action_id,
                accepted_by=command.accepted_by,
                reason=command.reason,
                confidence=command.confidence,
                metadata=command.metadata,
                error=str(exc),
            )
            raise

    async def _submit_action(
        self,
        proposal: ActionExperienceProposalRecord,
        command: "AcceptanceCommand",
    ) -> ActionSubmission:
        detail = await self.catalog_service.find_detail(
            capability=proposal.capability_id,
            profile=proposal.profile_id,
        )
        action = ActionRequest(
            action_id=command.action_id,
            kind=ActionKind.SCAN,
            program_id=proposal.program_id,
            catalog_id=detail.id,
            targets=command.targets,
            options=dict(command.options),
            budget=command.budget,
            requested_by=command.accepted_by,
            campaign_id=proposal.campaign_id or self._deterministic_campaign_id(proposal),
            metadata=command.metadata,
        )
        return await self.action_service.request_action(action, confidence=command.confidence)

    async def _existing_submission(self, action_id: UUID) -> ActionSubmission | None:
        get_submission = getattr(self.action_service, "get_action_submission", None)
        if get_submission is None:
            return None
        return await get_submission(action_id)

    async def _mark_accepted_or_recover(
        self,
        proposal: ActionExperienceProposalRecord,
        command: "AcceptanceCommand",
        submission: ActionSubmission,
    ) -> ActionExperienceProposalRecord:
        accepted = await self.store.mark_accepted(
            proposal_id=proposal.proposal_id,
            action_id=submission.action_id,
            accepted_by=command.accepted_by,
            reason=command.reason,
            confidence=command.confidence,
            metadata=command.metadata,
        )
        if accepted is not None:
            return accepted
        current = await self.store.get_proposal(proposal.proposal_id)
        if current and current.status is ActionExperienceProposalStatus.ACCEPTED:
            return current
        raise ActionExperienceProposalStateError(
            f"Action experience proposal {proposal.proposal_id} could not be marked accepted"
        )

    def _acceptance_command(
        self,
        proposal: ActionExperienceProposalRecord,
        request: ActionExperienceProposalAcceptRequest,
        *,
        retry_failed: bool,
    ) -> "AcceptanceCommand":
        if proposal.status is ActionExperienceProposalStatus.ACCEPTING:
            stored = self._stored_acceptance_command(proposal)
            if stored is None:
                raise ActionExperienceProposalStateError(
                    f"Action experience proposal {proposal.proposal_id} is accepting without stored acceptance metadata"
                )
            return stored
        action_id = self._acceptance_action_id(proposal, retry_failed=retry_failed)
        targets = list(request.targets)
        if not targets:
            raise ActionExperienceProposalNotActionable(
                "action experience proposal acceptance requires explicit targets"
            )
        metadata = self._acceptance_metadata(proposal, request, action_id=action_id, targets=targets)
        return AcceptanceCommand(
            action_id=action_id,
            targets=targets,
            options=dict(request.options),
            budget=self._budget_payload(request.budget),
            accepted_by=request.accepted_by,
            reason=request.reason,
            confidence=request.confidence,
            metadata=metadata,
        )

    @staticmethod
    def _stored_acceptance_command(proposal: ActionExperienceProposalRecord) -> "AcceptanceCommand | None":
        payload = proposal.explanation.get("acceptance") if isinstance(proposal.explanation, dict) else None
        metadata = payload.get("metadata") if isinstance(payload, dict) else None
        acceptance = metadata.get("acceptance") if isinstance(metadata, dict) else None
        if not isinstance(acceptance, dict):
            return None
        action_id_value = acceptance.get("accepted_action_id") or payload.get("accepted_action_id")
        try:
            action_id = UUID(str(action_id_value))
        except (TypeError, ValueError):
            return None
        targets = acceptance.get("targets")
        if not isinstance(targets, list):
            return None
        options = acceptance.get("options")
        budget = acceptance.get("budget")
        return AcceptanceCommand(
            action_id=action_id,
            targets=[str(target).strip() for target in targets if str(target).strip()],
            options=dict(options) if isinstance(options, dict) else {},
            budget=budget if isinstance(budget, dict) else None,
            accepted_by=str(acceptance.get("accepted_by") or payload.get("actor") or "human"),
            reason=acceptance.get("reason") if isinstance(acceptance.get("reason"), str) else None,
            confidence=float(acceptance.get("confidence") if acceptance.get("confidence") is not None else payload.get("confidence") or 1.0),
            metadata=dict(metadata),
        )

    @staticmethod
    def _validate_resume_request(
        proposal: ActionExperienceProposalRecord,
        command: "AcceptanceCommand",
        request: ActionExperienceProposalAcceptRequest,
    ) -> None:
        if request.targets and list(request.targets) != command.targets:
            raise ActionExperienceProposalStateError(
                f"Action experience proposal {proposal.proposal_id} is already accepting different targets"
            )
        if request.options and dict(request.options) != command.options:
            raise ActionExperienceProposalStateError(
                f"Action experience proposal {proposal.proposal_id} is already accepting different options"
            )
        if request.budget is not None and ActionExperienceProposalAcceptanceService._budget_payload(request.budget) != command.budget:
            raise ActionExperienceProposalStateError(
                f"Action experience proposal {proposal.proposal_id} is already accepting a different budget"
            )

    @staticmethod
    def _acceptance_is_stale(proposal: ActionExperienceProposalRecord) -> bool:
        payload = proposal.explanation.get("acceptance") if isinstance(proposal.explanation, dict) else None
        timestamp = payload.get("accepted_at") if isinstance(payload, dict) else None
        if not isinstance(timestamp, str):
            return False
        try:
            accepted_at = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        except ValueError:
            return False
        if accepted_at.tzinfo is None:
            accepted_at = accepted_at.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) - accepted_at >= _ACCEPTANCE_STALE_AFTER

    @classmethod
    def _acceptance_action_id(cls, proposal: ActionExperienceProposalRecord, *, retry_failed: bool) -> UUID:
        payload = proposal.explanation.get("acceptance") if isinstance(proposal.explanation, dict) else None
        if isinstance(payload, dict):
            value = payload.get("accepted_action_id")
            if value:
                try:
                    return UUID(str(value))
                except ValueError:
                    pass
        suffix = "retry" if retry_failed else "accept"
        return uuid5(NAMESPACE_URL, f"action-experience-proposal:{proposal.proposal_id}:{suffix}")

    @staticmethod
    def _deterministic_campaign_id(proposal: ActionExperienceProposalRecord) -> UUID:
        return uuid5(NAMESPACE_URL, f"action-experience-proposal:{proposal.proposal_id}:campaign")

    @staticmethod
    def _acceptance_metadata(
        proposal: ActionExperienceProposalRecord,
        request: ActionExperienceProposalAcceptRequest,
        *,
        action_id: UUID,
        targets: list[str],
    ) -> dict[str, Any]:
        return sanitize_json(
            {
                **request.metadata,
                "schema_version": ACTION_EXPERIENCE_PROPOSAL_ACCEPT_SCHEMA_VERSION,
                "source": "action_experience_proposal_accept",
                "action_experience_proposal": {
                    "proposal_id": str(proposal.proposal_id),
                    "proposal_run_id": str(proposal.proposal_run_id),
                    "source_outcome_id": str(proposal.source_outcome_id),
                    "source_action_id": str(proposal.source_action_id),
                    "source_job_id": str(proposal.source_job_id),
                    "source_run_id": str(proposal.source_run_id),
                    "proposal_key": proposal.proposal_key,
                    "capability_id": proposal.capability_id,
                    "profile_id": proposal.profile_id,
                    "rank": proposal.rank,
                    "utility_score": proposal.utility_score,
                    "sample_count": proposal.sample_count,
                    "produced_by": proposal.produced_by,
                },
                "acceptance": {
                    "accepted_by": request.accepted_by,
                    "accepted_action_id": str(action_id),
                    "targets": targets,
                    "options": dict(request.options),
                    "budget": ActionExperienceProposalAcceptanceService._budget_payload(request.budget),
                    "reason": request.reason,
                    "confidence": request.confidence,
                    "boundary": {
                        "proposal_direct_execution": False,
                        "submitted_through_action_service": True,
                        "policy_scope_approval_budget_required": True,
                    },
                },
            }
        )

    @staticmethod
    def _budget_payload(value: Any) -> dict[str, Any] | None:
        if value is None:
            return None
        if hasattr(value, "model_dump"):
            return value.model_dump(mode="json")
        return dict(value) if isinstance(value, dict) else None


class AcceptanceCommand:
    def __init__(
        self,
        *,
        action_id: UUID,
        targets: list[str],
        options: dict[str, Any],
        budget: dict[str, Any] | None,
        accepted_by: str,
        reason: str | None,
        confidence: float,
        metadata: dict[str, Any],
    ) -> None:
        self.action_id = action_id
        self.targets = targets
        self.options = options
        self.budget = budget
        self.accepted_by = accepted_by
        self.reason = reason
        self.confidence = max(0.0, min(1.0, float(confidence)))
        self.metadata = metadata
