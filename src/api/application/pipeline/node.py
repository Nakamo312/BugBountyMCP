"""Base Node abstraction for pipeline graph"""
from abc import ABC, abstractmethod
from typing import Dict, Any, Set
import asyncio
import logging
import time

from api.infrastructure.events.event_types import EventType
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

    async def _execute_with_semaphore(self, event: Dict[str, Any]):
        """
        Execute with semaphore-based backpressure and optional delay.

        Args:
            event: Event to process
        """
        async with self._semaphore:
            self._active_executions += 1
            self.heartbeat()
            try:
                if self.execution_delay > 0:
                    self.logger.debug(f"Delaying execution by {self.execution_delay}s")
                    await asyncio.sleep(self.execution_delay)

                ctx = await self._create_context()
                ctx.retry_policy = self.retry_policy
                ctx.bind_event(event)
                await ctx.mark_run_started()
                await self.execute(event, ctx)
                await ctx.mark_run_completed()
            except Exception as exc:
                try:
                    if "ctx" in locals():
                        await ctx.mark_run_failed(exc)
                except Exception:
                    self.logger.warning("Failed to mark run as failed", exc_info=True)
                self.logger.error(
                    f"Execution failed for event type={event.get('_event_type')}: {exc}",
                    exc_info=True
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
