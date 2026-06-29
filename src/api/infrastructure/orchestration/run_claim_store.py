"""Scenario-owned persistence for scheduled node-run claiming."""
from __future__ import annotations

import uuid
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker

from api.application.contracts import ExecutionMode, ExecutionStatus, NodeRunClaim
from api.infrastructure.orchestration.run_claim_models import (
    CampaignBudgetReservation,
    CampaignBudgetSnapshot,
    ExistingWorkClaim,
    RunClaimRequest,
    blocked_node_run_claim,
    campaign_budget_snapshot,
    existing_work_claim,
    refilled_tokens as _refilled_tokens,
    work_dedup_reason,
)
from api.infrastructure.orchestration.run_claim_statements import (
    append_coalesced_trigger_statement as _append_coalesced_trigger_statement,
)
from api.infrastructure.orchestration.run_claim_persistence import (
    append_coalesced_trigger,
    insert_claimed_run,
    lock_campaign_budget,
    persist_refilled_campaign_tokens,
    select_active_work_claim,
    select_node_run_claim,
    select_recent_completed_work,
    select_retryable_failed_work_claim,
)


class RunClaimStore:
    """Durable write scenario for node-run claim/deduplication semantics."""

    def __init__(self, session_factory: async_sessionmaker):
        self.session_factory = session_factory

    async def claim_node_run(
        self,
        *,
        claim_key: str,
        job_id: uuid.UUID,
        program_id: uuid.UUID,
        node_id: str,
        event_name: str,
        trigger_event_id: uuid.UUID,
        input_fingerprint: str,
        target_fingerprint: str,
        execution_mode: ExecutionMode = ExecutionMode.INLINE,
        next_run_at: datetime | None = None,
        target_count: int | None = None,
        run_payload: Mapping[str, Any] | None = None,
        work_key: str | None = None,
        coalesced_trigger: Mapping[str, Any] | None = None,
        retry_policy: dict | None = None,
        campaign_id: uuid.UUID | None = None,
        expansion_depth: int = 0,
        max_expansion_depth: int | None = None,
        cooldown_seconds: int | float = 0,
        token_cost: int | float = 1,
    ) -> NodeRunClaim:
        return await self._claim_node_run(
            RunClaimRequest(
                claim_key=claim_key,
                job_id=job_id,
                program_id=program_id,
                node_id=node_id,
                event_name=event_name,
                trigger_event_id=trigger_event_id,
                input_fingerprint=input_fingerprint,
                target_fingerprint=target_fingerprint,
                execution_mode=execution_mode,
                next_run_at=next_run_at,
                target_count=target_count,
                run_payload=run_payload,
                work_key=work_key,
                coalesced_trigger=coalesced_trigger,
                retry_policy=retry_policy,
                campaign_id=campaign_id,
                expansion_depth=expansion_depth,
                max_expansion_depth=max_expansion_depth,
                cooldown_seconds=cooldown_seconds,
                token_cost=token_cost,
            )
        )

    async def _claim_node_run(self, request: RunClaimRequest) -> NodeRunClaim:
        now = datetime.now(timezone.utc)

        async with self.session_factory() as session:
            existing = await self._select_node_run_claim(session, request.claim_key)
            if existing is not None:
                return existing

            if self._depth_limit_exceeded(
                request.expansion_depth,
                request.max_expansion_depth,
            ):
                return self._blocked_node_run_claim(request.claim_key, "depth_limit")

            reusable = await self._try_reuse_retryable_work(session, request=request, now=now)
            if reusable is not None:
                await session.commit()
                return reusable

            cooldown_block = await self._check_cooldown_block(session, request=request, now=now)
            if cooldown_block is not None:
                return cooldown_block

            budget = await self._reserve_campaign_budget_if_needed(
                session,
                request=request,
                now=now,
            )
            if isinstance(budget, NodeRunClaim):
                return budget

            try:
                run_id = await self._insert_claimed_run(
                    session,
                    request=request,
                    budget=budget,
                    now=now,
                )
                await session.commit()
                return NodeRunClaim(
                    run_id=run_id,
                    claim_key=request.claim_key,
                    status=ExecutionStatus.QUEUED,
                    created=True,
                )
            except IntegrityError as exc:
                return await self._recover_from_insert_race(
                    session,
                    request=request,
                    now=now,
                    insert_error=exc,
                )

    @staticmethod
    def _depth_limit_exceeded(
        expansion_depth: int,
        max_expansion_depth: int | None,
    ) -> bool:
        return max_expansion_depth is not None and expansion_depth > max_expansion_depth

    async def _try_reuse_retryable_work(
        self,
        session,
        *,
        request: RunClaimRequest,
        now: datetime,
    ) -> NodeRunClaim | None:
        if (
            request.execution_mode != ExecutionMode.SCHEDULED
            or not request.work_key
            or not request.retry_policy
        ):
            return None

        existing_work = await self._select_retryable_failed_work_claim(
            session,
            work_key=request.work_key,
            retry_policy=request.retry_policy,
        )
        existing_work = self._existing_work_claim(existing_work)
        if existing_work is None:
            return None

        await self._append_coalesced_trigger(
            session,
            run_id=existing_work.id,
            coalesced_trigger=request.coalesced_trigger,
            now=now,
            reason=self._work_dedup_reason(existing_work.status),
        )
        return existing_work.to_node_run_claim()

    async def _check_cooldown_block(
        self,
        session,
        *,
        request: RunClaimRequest,
        now: datetime,
    ) -> NodeRunClaim | None:
        if (
            request.execution_mode != ExecutionMode.SCHEDULED
            or not request.work_key
            or request.cooldown_seconds <= 0
        ):
            return None

        recent_work = await self._select_recent_completed_work(
            session,
            work_key=request.work_key,
            since=now - timedelta(seconds=float(request.cooldown_seconds)),
        )
        if recent_work is None:
            return None
        return self._blocked_node_run_claim(request.claim_key, "cooldown_active")

    async def _reserve_campaign_budget_if_needed(
        self,
        session,
        *,
        request: RunClaimRequest,
        now: datetime,
    ) -> CampaignBudgetReservation | NodeRunClaim | None:
        if request.execution_mode != ExecutionMode.SCHEDULED or request.campaign_id is None:
            return None

        locked_budget = await self._lock_campaign_budget(
            session,
            campaign_id=request.campaign_id,
        )
        if locked_budget is None:
            return self._blocked_node_run_claim(
                request.claim_key,
                "campaign_budget_missing",
            )

        target_cost = max(int(request.target_count or 0), 0)
        token_cost_value = float(request.token_cost)
        snapshot = self._campaign_budget_snapshot(locked_budget).refilled(now)
        blocked_reason = snapshot.block_reason(
            target_count=target_cost,
            token_cost=token_cost_value,
        )
        if blocked_reason is not None:
            await self._persist_refilled_campaign_tokens(
                session,
                campaign_id=request.campaign_id,
                tokens_available=snapshot.tokens_available,
                now=now,
            )
            await session.commit()
            return self._blocked_node_run_claim(request.claim_key, blocked_reason)

        return CampaignBudgetReservation(
            campaign_id=request.campaign_id,
            snapshot=snapshot,
            target_cost=target_cost,
            token_cost=token_cost_value,
        )

    async def _recover_from_insert_race(
        self,
        session,
        *,
        request: RunClaimRequest,
        now: datetime,
        insert_error: IntegrityError,
    ) -> NodeRunClaim:
        await session.rollback()
        existing = await self._select_node_run_claim(session, request.claim_key)
        if existing is not None:
            return existing

        if request.execution_mode == ExecutionMode.SCHEDULED and request.work_key:
            existing_work = await self._select_active_work_claim(
                session,
                work_key=request.work_key,
            )
            existing_work = self._existing_work_claim(existing_work)
            if existing_work is not None:
                await self._append_coalesced_trigger(
                    session,
                    run_id=existing_work.id,
                    coalesced_trigger=request.coalesced_trigger,
                    now=now,
                    reason=self._work_dedup_reason(existing_work.status),
                )
                await session.commit()
                return existing_work.to_node_run_claim()
        raise insert_error

    @staticmethod
    def _existing_work_claim(
        value: ExistingWorkClaim | Mapping[str, Any] | None,
    ) -> ExistingWorkClaim | None:
        return existing_work_claim(value)

    @staticmethod
    def _campaign_budget_snapshot(
        value: CampaignBudgetSnapshot | Mapping[str, Any],
    ) -> CampaignBudgetSnapshot:
        return campaign_budget_snapshot(value)

    @staticmethod
    def _blocked_node_run_claim(claim_key: str, reason: str) -> NodeRunClaim:
        return blocked_node_run_claim(claim_key, reason)

    @staticmethod
    def _work_dedup_reason(status: str | ExecutionStatus | None) -> str:
        return work_dedup_reason(status)

    @staticmethod
    async def _select_node_run_claim(session, claim_key: str) -> NodeRunClaim | None:
        return await select_node_run_claim(session, claim_key)

    @staticmethod
    async def _select_active_work_claim(session, *, work_key: str):
        return await select_active_work_claim(session, work_key=work_key)

    @staticmethod
    async def _select_recent_completed_work(session, *, work_key: str, since: datetime):
        return await select_recent_completed_work(session, work_key=work_key, since=since)

    @staticmethod
    async def _lock_campaign_budget(
        session,
        *,
        campaign_id: uuid.UUID,
    ) -> CampaignBudgetSnapshot | None:
        return await lock_campaign_budget(session, campaign_id=campaign_id)

    @staticmethod
    async def _select_retryable_failed_work_claim(
        session,
        *,
        work_key: str,
        retry_policy: dict,
    ) -> ExistingWorkClaim | None:
        return await select_retryable_failed_work_claim(
            session,
            work_key=work_key,
            retry_policy=retry_policy,
        )

    @staticmethod
    async def _append_coalesced_trigger(
        session,
        *,
        run_id: uuid.UUID,
        coalesced_trigger: Mapping[str, Any] | None,
        now: datetime,
        reason: str | None = None,
        sample_limit: int = 50,
    ) -> None:
        await append_coalesced_trigger(
            session,
            run_id=run_id,
            coalesced_trigger=coalesced_trigger,
            now=now,
            reason=reason,
            sample_limit=sample_limit,
        )

    @staticmethod
    async def _persist_refilled_campaign_tokens(
        session,
        *,
        campaign_id: uuid.UUID,
        tokens_available: float,
        now: datetime,
    ) -> None:
        await persist_refilled_campaign_tokens(
            session,
            campaign_id=campaign_id,
            tokens_available=tokens_available,
            now=now,
        )

    @staticmethod
    async def _insert_claimed_run(
        session,
        *,
        request: RunClaimRequest,
        budget: CampaignBudgetReservation | None,
        now: datetime,
    ) -> uuid.UUID:
        return await insert_claimed_run(
            session,
            request=request,
            budget=budget,
            now=now,
        )
