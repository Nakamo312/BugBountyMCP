"""Base Node abstraction for pipeline graph"""
from abc import ABC, abstractmethod
from typing import Dict, Any, Set
import asyncio
import logging
import time

from api.application.event_contracts import EventType
from api.application.contracts import ExecutionMode


class Node(ABC):
    """
    Long-lived graph operator that processes events from EventBus.

    Node Lifecycle:
    1. Construction - __init__ (DI injected dependencies)
    2. Registration - register() called by NodeRegistry
    3. Idle - waiting for events from EventBus
    4. Activation - event received via handle_event()
    5. Execution - create execution context, run, emit events
    6. Completion - execution context destroyed
    7. Shutdown - await active executions

    EventBus handles queuing, Node handles backpressure via semaphore.
    """

    def __init__(
        self,
        node_id: str,
        event_in: Set[EventType],
        event_out: Set[EventType],
        max_parallelism: int = 1,
        execution_delay: int = 0,
        execution_mode: ExecutionMode = ExecutionMode.INLINE,
        max_targets_per_run: int | None = None,
        cooldown_seconds: int | float = 0,
        max_fanout_per_event: int | None = None,
        max_expansion_depth: int | None = None,
        token_cost: int | float = 1,
        retry_policy: dict | None = None,
    ):
        """
        Initialize node.

        Args:
            node_id: Unique node identifier
            event_in: Set of event types this node accepts
            event_out: Set of event types this node emits
            max_parallelism: Maximum concurrent executions
            execution_delay: Delay in seconds before executing (default: 0)
        """
        self.node_id = node_id
        self.event_in = event_in
        self.event_out = event_out
        self.max_parallelism = max_parallelism
        self.execution_delay = execution_delay
        self.execution_mode = execution_mode
        self.max_targets_per_run = max_targets_per_run
        self.cooldown_seconds = cooldown_seconds
        self.max_fanout_per_event = max_fanout_per_event
        self.max_expansion_depth = max_expansion_depth
        self.token_cost = token_cost
        self.retry_policy = retry_policy or {
            "max_attempts": 1,
            "backoff_seconds": 0,
            "terminal_outcomes": [],
        }
        self.logger = logging.getLogger(f"node.{node_id}")

        self._semaphore = asyncio.Semaphore(max_parallelism)
        self._tasks: Set[asyncio.Task] = set()
        self._active_executions = 0
        self._last_heartbeat_timestamp_seconds = 0.0

    @abstractmethod
    async def execute(self, event: Dict[str, Any], ctx: "PipelineContext"):
        """
        Execute node logic for a single event.

        Args:
            event: Incoming event data
            ctx: Pipeline context with emit(), DI, settings access
        """
        pass

    async def handle_event(self, event: Dict[str, Any]):
        """
        Handle incoming event from EventBus.
        Called by NodeRegistry when event arrives.

        Args:
            event: Event to process
        """
        task = asyncio.create_task(self._execute_with_semaphore(event))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        await task

    async def stop(self):
        """Stop node and await all active executions"""
        if self._tasks:
            self.logger.info(f"Waiting for {len(self._tasks)} executions to complete...")
            await asyncio.gather(*self._tasks, return_exceptions=True)

        self.logger.info(f"Node stopped: {self.node_id}")

    def heartbeat(self) -> None:
        """Mark this worker node runtime as alive for monitoring."""
        self._last_heartbeat_timestamp_seconds = time.time()

    def runtime_snapshot(self) -> dict[str, int | float | str]:
        """Return low-cardinality runtime metrics for this worker node."""
        return {
            "node_id": self.node_id,
            "configured": 1,
            "capacity": self.max_parallelism,
            "busy": self._active_executions,
            "last_heartbeat_timestamp_seconds": self._last_heartbeat_timestamp_seconds,
        }

    def available_slots(self) -> int:
        """Return how many executions this node can start immediately."""
        return max(self.max_parallelism - self._active_executions, 0)

    async def _execute_with_semaphore(self, event: Dict[str, Any]):
        """
        Execute with semaphore-based backpressure and optional delay.

        Args:
            event: Event to process
        """
        async with self._semaphore:
            self._active_executions += 1
            self.heartbeat()
            ctx = None

            try:
                if self.execution_delay > 0 and not event.get("_skip_execution_delay"):
                    self.logger.debug(f"Delaying execution by {self.execution_delay}s")
                    await asyncio.sleep(self.execution_delay)

                ctx = await self._create_context()
                ctx.retry_policy = self.retry_policy
                ctx.bind_event(event)

                started = await ctx.mark_run_started()
                if not started:
                    reason = (
                        "run start transition was rejected before tool execution: "
                        f"node={self.node_id} run_id={event.get('run_id')} "
                        f"event_type={event.get('_event_type') or event.get('event')}"
                    )
                    self.logger.warning("Skipping node execution because %s", reason)
                    try:
                        if ctx is not None:
                            failed = await ctx.mark_run_failed(RuntimeError(reason))
                            if not failed:
                                await ctx.mark_run_needs_reconcile("start_transition_rejected")
                    except Exception:
                        self.logger.warning(
                            "Failed to mark start-rejected run as failed",
                            exc_info=True,
                        )
                    return

                await self.execute(event, ctx)

                flushing = await ctx.mark_run_flushing()
                if not flushing:
                    self.logger.warning(
                        "Skipping completion because run flushing transition was rejected: "
                        "node=%s run_id=%s event_type=%s",
                        self.node_id,
                        event.get("run_id"),
                        event.get("_event_type") or event.get("event"),
                    )
                    return

                completed = await ctx.mark_run_completed()
                if not completed:
                    self.logger.warning(
                        "Run completion transition was rejected: node=%s run_id=%s event_type=%s",
                        self.node_id,
                        event.get("run_id"),
                        event.get("_event_type") or event.get("event"),
                    )

            except Exception as exc:
                try:
                    if ctx is not None:
                        failed = await ctx.mark_run_failed(exc)
                        if not failed:
                            self.logger.warning(
                                "Run failure transition was rejected: node=%s run_id=%s event_type=%s",
                                self.node_id,
                                event.get("run_id"),
                                event.get("_event_type") or event.get("event"),
                            )
                except Exception:
                    self.logger.warning("Failed to mark run as failed", exc_info=True)

                self.logger.error(
                    f"Execution failed for event type={event.get('_event_type')}: {exc}",
                    exc_info=True,
                )
            finally:
                self._active_executions -= 1

    async def _create_context(self) -> "PipelineContext":
        """
        Create execution context. Override to inject node-specific dependencies.

        Returns:
            Pipeline context
        """
        from api.application.pipeline.context import PipelineContext
        return PipelineContext(node_id=self.node_id)
