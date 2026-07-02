"""Operator action control transitions."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import and_, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker

from api.application.action_control_contracts import ActionCancelResult
from api.infrastructure.adapters.orm import (
    action_requests,
    event_dispatches,
    event_store,
    jobs,
    runs,
)

_STARTED_RUN_STATUSES = {"leased", "running", "flushing"}
_CANCELABLE_ACTION_STATUSES = {"allowed", "queued", "requires_approval"}
_CANCELABLE_RUN_STATUSES = {"queued", "failed", "dead"}
_CANCELABLE_JOB_STATUSES = {"queued", "failed"}
_CANCELABLE_DISPATCH_STATUSES = {"pending", "locked", "failed"}


class ActionControlStore:
    """Persist explicit human controls for action queue entries."""

    def __init__(self, session_factory: async_sessionmaker) -> None:
        self.session_factory = session_factory

    async def cancel_action(
        self,
        *,
        action_id: UUID,
        cancelled_by: str,
        reason: str | None = None,
    ) -> ActionCancelResult | None:
        now = datetime.now(timezone.utc)
        async with self.session_factory() as session:
            action_row = await session.execute(
                select(action_requests).where(action_requests.c.id == action_id)
            )
            action = action_row.mappings().first()
            if action is None:
                return None

            status = str(action["status"])
            if status not in _CANCELABLE_ACTION_STATUSES:
                return _not_cancelled(
                    action,
                    f"Action {action_id} cannot be cancelled from status {status}.",
                )

            run_rows = await session.execute(
                select(runs.c.id, runs.c.status)
                .select_from(jobs.join(runs, runs.c.job_id == jobs.c.id))
                .where(jobs.c.action_id == action_id)
            )
            run_states = [dict(row) for row in run_rows.mappings().all()]
            active = [row for row in run_states if row["status"] in _STARTED_RUN_STATUSES]
            if active:
                active_statuses = ", ".join(sorted({str(row["status"]) for row in active}))
                return _not_cancelled(
                    action,
                    f"Action {action_id} already reached worker state {active_statuses}; queued cancellation cannot stop a live runner.",
                )

            cancel_note = {
                "cancelled": True,
                "cancelled_by": cancelled_by,
                "cancelled_at": now.isoformat(),
                "reason": reason or "Cancelled from action queue UI",
            }
            metadata = dict(action.get("metadata") or {})
            metadata["operator_cancellation"] = cancel_note

            await session.execute(
                update(action_requests)
                .where(action_requests.c.id == action_id)
                .where(action_requests.c.status.in_(list(_CANCELABLE_ACTION_STATUSES)))
                .values(status="rejected", metadata=metadata, updated_at=now)
            )
            await session.execute(
                update(jobs)
                .where(jobs.c.action_id == action_id)
                .where(jobs.c.status.in_(list(_CANCELABLE_JOB_STATUSES)))
                .values(status="cancelled", updated_at=now)
            )
            await session.execute(
                update(runs)
                .where(
                    runs.c.job_id.in_(
                        select(jobs.c.id).where(jobs.c.action_id == action_id)
                    )
                )
                .where(runs.c.status.in_(list(_CANCELABLE_RUN_STATUSES)))
                .values(
                    status="cancelled",
                    finished_at=now,
                    updated_at=now,
                    error=reason or "Cancelled from action queue UI",
                    next_retry_at=None,
                    needs_reconcile=False,
                    reconcile_reason=None,
                )
            )
            await session.execute(
                update(event_dispatches)
                .where(
                    event_dispatches.c.event_id.in_(
                        select(event_store.c.event_id)
                        .select_from(event_store.join(runs, runs.c.id == event_store.c.run_id).join(jobs, jobs.c.id == runs.c.job_id))
                        .where(jobs.c.action_id == action_id)
                    )
                )
                .where(event_dispatches.c.status.in_(list(_CANCELABLE_DISPATCH_STATUSES)))
                .values(
                    status="dead",
                    locked_by=None,
                    locked_until=None,
                    last_error=reason or "Cancelled from action queue UI",
                    updated_at=now,
                )
            )
            await session.commit()

        return ActionCancelResult(
            action_id=action_id,
            cancelled=True,
            message=f"Action {action_id} cancelled before worker execution.",
            campaign_id=action.get("campaign_id"),
            correlation_id=action.get("correlation_id"),
            workflow_id=action.get("workflow_id"),
        )


def _not_cancelled(action, message: str) -> ActionCancelResult:
    return ActionCancelResult(
        action_id=action["id"],
        cancelled=False,
        message=message,
        campaign_id=action.get("campaign_id"),
        correlation_id=action.get("correlation_id"),
        workflow_id=action.get("workflow_id"),
    )
