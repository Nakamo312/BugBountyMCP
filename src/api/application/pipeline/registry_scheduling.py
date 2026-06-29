"""Scheduled executor helpers for :mod:`api.application.pipeline.registry`."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

from api.application.contracts import ExecutionMode, ExecutionStatus, TerminalOutcome
from api.application.pipeline.node import Node

logger = logging.getLogger(__name__)


class NodeRegistrySchedulingMixin:
    def _should_start_scheduled_executor(self) -> bool:
        if not self.settings.PIPELINE_SCHEDULER_ENABLED:
            return False
        if self.container is None and self._orchestration_store is None:
            return False
        return any(
            node.execution_mode == ExecutionMode.SCHEDULED
            for node in self._nodes.values()
        )

    async def _run_scheduled_executor(self) -> None:
        logger.info(
            "Scheduled executor loop started: poll_seconds=%s batch_size=%s",
            self.settings.PIPELINE_SCHEDULED_EXECUTOR_POLL_SECONDS,
            self.settings.PIPELINE_SCHEDULED_EXECUTOR_BATCH_SIZE,
        )
        while True:
            try:
                await self._drain_scheduled_node_runs_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Scheduled executor tick failed")
            await asyncio.sleep(self.settings.PIPELINE_SCHEDULED_EXECUTOR_POLL_SECONDS)

    def _scheduled_node_available_slot_limits(
        self,
        batch_size: int,
        active_runs_by_node: Mapping[str, int] | None = None,
    ) -> dict[str, int]:
        if batch_size <= 0:
            return {}

        active_runs_by_node = active_runs_by_node or {}
        limits: dict[str, int] = {}
        for node_id, node in sorted(self._nodes.items()):
            if node.execution_mode != ExecutionMode.SCHEDULED:
                continue

            local_available = node.available_slots()
            durable_inflight = int(active_runs_by_node.get(node_id, 0) or 0)
            durable_available = max(node.max_parallelism - durable_inflight, 0)
            available = min(local_available, durable_available)
            node_limit = min(available, batch_size)
            if node_limit <= 0:
                continue

            limits[node_id] = node_limit

        return limits

    async def _drain_scheduled_node_runs_once(self) -> None:
        store = await self._get_pipeline_orchestration_store()
        if store is None:
            logger.warning("Scheduled executor tick skipped: orchestration store is missing")
            return

        recovered_leases = await store.recover_stale_leases()
        if recovered_leases:
            logger.warning(
                "Recovered stale scheduled leases: count=%s",
                recovered_leases,
            )

        stale_failed = await store.fail_stale_scheduled_active_runs(
            running_timeout_seconds=self.settings.PIPELINE_SCHEDULER_RUNNING_TIMEOUT_SECONDS,
            flushing_timeout_seconds=self.settings.PIPELINE_SCHEDULER_FLUSHING_TIMEOUT_SECONDS,
        )
        if stale_failed:
            logger.warning(
                "Marked stale scheduled active runs as failed: count=%s",
                stale_failed,
            )

        requeued = await store.requeue_retryable_node_runs(
            retry_policies=self._retry_policies_by_node(),
            max_requeues_per_node=self.settings.PIPELINE_RETRY_REQUEUE_LIMIT_PER_NODE,
            retry_jitter_seconds=self.settings.PIPELINE_RETRY_REQUEUE_JITTER_SECONDS,
        )
        if requeued:
            logger.info("Requeued retryable scheduled runs: count=%s", requeued)

        active_counter = getattr(store, "count_scheduled_active_runs_by_node", None)
        active_runs_by_node = await active_counter() if active_counter else {}
        node_limits = self._scheduled_node_available_slot_limits(
            self.settings.PIPELINE_SCHEDULED_EXECUTOR_BATCH_SIZE,
            active_runs_by_node=active_runs_by_node,
        )
        if not node_limits:
            logger.debug("Scheduled executor tick skipped: no available node slots")
            return

        leased_runs = await store.lease_ready_scheduled_node_runs(
            node_limits=node_limits,
            lease_owner=self._scheduler_lease_owner,
            lease_ttl_seconds=self.settings.PIPELINE_SCHEDULER_LEASE_TTL_SECONDS,
        )
        if not leased_runs:
            logger.debug("Scheduled executor tick leased no runs")
            return

        logger.info(
            "Scheduled executor leased runs: count=%s nodes=%s",
            len(leased_runs),
            [leased_run.node_id for leased_run in leased_runs],
        )

        for leased_run in leased_runs:
            node = self._nodes.get(leased_run.node_id)
            if node is None:
                logger.error(
                    "Leased scheduled run for unknown node; cancelling run: node=%s run_id=%s",
                    leased_run.node_id,
                    leased_run.run_id,
                )
                await self._cancel_unknown_scheduled_node_run(
                    store=store,
                    node_id=leased_run.node_id,
                    run_id=leased_run.run_id,
                )
                continue

            self._launch_scheduled_node_task(
                node_id=leased_run.node_id,
                node=node,
                event=leased_run.event,
            )

    async def _cancel_unknown_scheduled_node_run(
        self,
        *,
        store,
        node_id: str,
        run_id,
    ) -> None:
        try:
            cancelled = await store.mark_run_finished(
                run_id=run_id,
                status=ExecutionStatus.CANCELLED,
                error=f"Cancelled: leased scheduled run for unknown node {node_id}",
                terminal_outcome=TerminalOutcome.SKIPPED,
            )
        except Exception:
            logger.exception(
                "Failed to cancel leased scheduled run for unknown node: node=%s run_id=%s",
                node_id,
                run_id,
            )
            return

        if not cancelled:
            logger.warning(
                "Unknown scheduled node run cancellation transition was rejected: node=%s run_id=%s",
                node_id,
                run_id,
            )

    def _launch_scheduled_node_task(
        self,
        node_id: str,
        node: Node,
        event: dict[str, Any],
    ) -> None:
        task = asyncio.create_task(node.handle_event(event))
        node_tasks = self._scheduled_node_tasks.setdefault(node_id, set())
        node_tasks.add(task)

        def _discard_scheduled_task(completed: asyncio.Task) -> None:
            node_tasks.discard(completed)
            if not node_tasks:
                self._scheduled_node_tasks.pop(node_id, None)
            try:
                result = completed.result()
            except asyncio.CancelledError:
                return
            except Exception:
                logger.exception("Scheduled node run failed: node=%s", node_id)
                return
            if isinstance(result, Exception):
                logger.error("Scheduled node run failed: node=%s error=%s", node_id, result)

        task.add_done_callback(_discard_scheduled_task)

    def _scheduled_next_run_at(self, node_id: str) -> datetime | None:
        node = self._nodes[node_id]
        if node.execution_mode != ExecutionMode.SCHEDULED or node.execution_delay <= 0:
            return None
        return datetime.now(timezone.utc) + timedelta(seconds=node.execution_delay)

    def _retry_policies_by_node(self) -> dict[str, dict[str, Any]]:
        return {
            node_id: dict(node.retry_policy)
            for node_id, node in self._nodes.items()
            if node.execution_mode == ExecutionMode.SCHEDULED
        }
