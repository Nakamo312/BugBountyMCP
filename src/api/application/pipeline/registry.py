"""Node registry for event routing"""
from __future__ import annotations
from collections.abc import Sequence
from typing import Any, Dict, Set
import asyncio
import logging
from uuid import uuid4

from api.application.contracts import ExecutionMode
from api.application.ports.orchestration import (
    NodeRunClaimPort,
    PipelineRunStatePort,
    ScheduledLeasePort,
    ScheduledRecoveryPort,
    ScheduledRetryPort,
)
from api.application.pipeline.node import Node
from api.application.pipeline.registry_claiming import NodeRegistryClaimingMixin
from api.application.pipeline.registry_scheduling import NodeRegistrySchedulingMixin
from api.application.pipeline.context_factory import PipelineContextFactory
from api.application.ports.events import EventBusPort
from api.config import Settings

logger = logging.getLogger(__name__)


class NodeRegistry(NodeRegistryClaimingMixin, NodeRegistrySchedulingMixin):
    """
    Thin dispatcher that routes events to registered nodes.
    Replaces monolithic Orchestrator with declarative subscription model.

    Subscribes to fixed queues (discovery, enumeration, validation, analysis)
    and routes events to nodes based on event type strings.
    """

    def __init__(
        self,
        bus: EventBusPort,
        settings: Settings,
        container=None,
        node_run_claims: NodeRunClaimPort | None = None,
        scheduled_leases: ScheduledLeasePort | None = None,
        scheduled_recovery: ScheduledRecoveryPort | None = None,
        scheduled_retries: ScheduledRetryPort | None = None,
        run_states: PipelineRunStatePort | None = None,
        context_factory: PipelineContextFactory | None = None,
        subscription_queues: Sequence[str] | None = None,
    ):
        """
        Initialize node registry.

        Args:
            bus: EventBusPort for pub/sub
            settings: Application settings
            container: Optional DI container for node context
        """
        self.bus = bus
        self.settings = settings
        self.container = container
        self._node_run_claims = node_run_claims
        self._scheduled_leases = scheduled_leases
        self._scheduled_recovery = scheduled_recovery
        self._scheduled_retries = scheduled_retries
        self._run_states = run_states
        self.context_factory = context_factory
        self.subscription_queues = tuple(subscription_queues or ())
        self._nodes: Dict[str, Node] = {}
        self._event_to_nodes: Dict[str, Set[str]] = {}
        self._subscription_tasks: Set[asyncio.Task] = set()
        self._scheduled_node_tasks: dict[str, set[asyncio.Task]] = {}
        self._scheduled_executor_task: asyncio.Task | None = None
        self._worker_heartbeat_task: asyncio.Task | None = None
        self._scheduler_lease_owner = f"scheduler-{uuid4()}"

    def register(self, node: Node):
        """
        Register node and subscribe to its input events.

        Args:
            node: Node instance to register

        Raises:
            ValueError: If node already registered
        """
        if node.node_id in self._nodes:
            raise ValueError(f"Node already registered: {node.node_id}")

        if hasattr(node, 'set_context_factory'):
            node.set_context_factory(self.bus, self.container, self.settings, self.context_factory)

        self._nodes[node.node_id] = node

        for event_type in node.event_in:
            event_str = event_type.value if hasattr(event_type, 'value') else str(event_type)
            if event_str not in self._event_to_nodes:
                self._event_to_nodes[event_str] = set()
            self._event_to_nodes[event_str].add(node.node_id)

        event_in_str = [e.value if hasattr(e, 'value') else str(e) for e in node.event_in]
        event_out_str = [e.value if hasattr(e, 'value') else str(e) for e in node.event_out]

        logger.info(
            f"Registered node: {node.node_id} "
            f"(in={event_in_str}, out={event_out_str})"
        )

    async def start(self):
        """Start EventBus subscriptions for infrastructure-provided queues."""
        if not self.subscription_queues:
            raise RuntimeError(
                "NodeRegistry requires subscription queues from infrastructure wiring"
            )

        await self.bus.connect()

        for queue_name in self.subscription_queues:
            task = asyncio.create_task(self.bus.subscribe(queue_name, self._dispatch_event))
            self._subscription_tasks.add(task)
            task.add_done_callback(self._subscription_tasks.discard)

        self._heartbeat_workers()
        self._worker_heartbeat_task = asyncio.create_task(self._run_worker_heartbeat())

        scheduled_nodes = [
            node.node_id
            for node in self._nodes.values()
            if node.execution_mode == ExecutionMode.SCHEDULED
        ]

        logger.debug(
            "Scheduled executor start check: enabled=%s container=%s runtime_ports=%s scheduled_nodes=%s",
            self.settings.PIPELINE_SCHEDULER_ENABLED,
            self.container is not None,
            self._has_scheduled_runtime_ports(),
            scheduled_nodes,
        )

        if self._should_start_scheduled_executor():
            logger.info(
                "Starting scheduled executor: poll_seconds=%s batch_size=%s",
                self.settings.PIPELINE_SCHEDULED_EXECUTOR_POLL_SECONDS,
                self.settings.PIPELINE_SCHEDULED_EXECUTOR_BATCH_SIZE,
            )
            self._scheduled_executor_task = asyncio.create_task(
                self._run_scheduled_executor()
            )
            self._scheduled_executor_task.add_done_callback(
                self._log_scheduled_executor_done
            )
        else:
            logger.warning(
                "Scheduled executor not started: enabled=%s container=%s runtime_ports=%s scheduled_nodes=%s",
                self.settings.PIPELINE_SCHEDULER_ENABLED,
                self.container is not None,
                self._has_scheduled_runtime_ports(),
                scheduled_nodes,
            )

        logger.info(
            f"NodeRegistry started: {len(self._nodes)} nodes, "
            f"{len(self._event_to_nodes)} event types, "
            f"{len(self.subscription_queues)} queues"
        )
        logger.info(f"Registered nodes: {list(self._nodes.keys())}")
        logger.info(f"Event mappings: {dict(self._event_to_nodes)}")

    async def stop(self):
        """Stop all nodes and await their completion"""
        logger.info("Stopping NodeRegistry...")

        if self._scheduled_executor_task is not None:
            self._scheduled_executor_task.cancel()
            await asyncio.gather(self._scheduled_executor_task, return_exceptions=True)
            self._scheduled_executor_task = None

        if self._worker_heartbeat_task is not None:
            self._worker_heartbeat_task.cancel()
            await asyncio.gather(self._worker_heartbeat_task, return_exceptions=True)
            self._worker_heartbeat_task = None

        if self._subscription_tasks:
            for task in self._subscription_tasks:
                task.cancel()
            await asyncio.gather(*self._subscription_tasks, return_exceptions=True)
            self._subscription_tasks.clear()

        scheduled_tasks = [
            task
            for tasks in self._scheduled_node_tasks.values()
            for task in tasks
        ]
        if scheduled_tasks:
            await asyncio.gather(*scheduled_tasks, return_exceptions=True)
            self._scheduled_node_tasks.clear()

        stop_tasks = [node.stop() for node in self._nodes.values()]
        await asyncio.gather(*stop_tasks, return_exceptions=True)

        logger.info("NodeRegistry stopped")

    def _log_scheduled_executor_done(self, task: asyncio.Task) -> None:
        if task.cancelled():
            logger.info("Scheduled executor task cancelled")
            return

        exc = task.exception()
        if exc is not None:
            logger.error(
                "Scheduled executor task stopped with exception: %s",
                exc,
                exc_info=(type(exc), exc, exc.__traceback__),
            )
            return

        logger.warning("Scheduled executor task stopped without exception")

    async def _dispatch_event(self, event: Dict[str, Any]):
        """
        Dispatch event to all nodes subscribed to its type.

        Event format:
        {
            "event": "host_discovered",
            "target": "admin.example.com",
            "source": "dnsx",
            "confidence": 0.7,
            "program_id": 42
        }

        Args:
            event: Event dictionary
        """
        event_name = event.get("event")
        if not event_name:
            logger.warning("Event missing 'event' field")
            return

        logger.info(f"Received event: {event_name}, targets={len(event.get('targets', []))}")

        node_ids = self._event_to_nodes.get(event_name, set())
        if not node_ids:
            logger.info(f"No nodes registered for event: {event_name}")
            return

        logger.info(f"Dispatching {event_name} to nodes: {node_ids}")

        node_tasks = []
        for node_id in sorted(node_ids):
            node = self._nodes[node_id]
            claimed_event = await self._claim_event_for_node(node_id, event_name, event)
            if claimed_event is None and node.execution_mode == ExecutionMode.SCHEDULED:
                logger.info(
                    "Processed scheduled node event: node=%s event=%s",
                    node_id,
                    event_name,
                )
                continue
            if claimed_event is None:
                logger.info(
                    "Skipping terminal node run: node=%s event=%s",
                    node_id,
                    event_name,
                )
                continue
            node_tasks.append((node_id, asyncio.create_task(node.handle_event(claimed_event))))

        if not node_tasks:
            return

        results = await asyncio.gather(
            *(task for _, task in node_tasks),
            return_exceptions=True,
        )
        for (node_id, _), result in zip(node_tasks, results):
            if isinstance(result, Exception):
                logger.error(
                    f"Failed to dispatch event to node {node_id}: {result}",
                    exc_info=(type(result), result, result.__traceback__),
                )

    async def _run_worker_heartbeat(self) -> None:
        while True:
            try:
                self._heartbeat_workers()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Worker heartbeat tick failed")
            await asyncio.sleep(15)

    def _heartbeat_workers(self) -> None:
        for node in self._nodes.values():
            node.heartbeat()

    def worker_snapshots(self) -> list[dict[str, int | float | str]]:
        return [node.runtime_snapshot() for node in self._nodes.values()]

    async def _get_node_run_claims(self) -> NodeRunClaimPort | None:
        if self._node_run_claims is not None:
            return self._node_run_claims
        if self.container is None:
            return None

        async with self.container() as request_container:
            return await request_container.get(NodeRunClaimPort)

    async def _get_scheduled_runtime_ports(
        self,
    ) -> tuple[
        ScheduledLeasePort,
        ScheduledRecoveryPort,
        ScheduledRetryPort,
        PipelineRunStatePort,
    ] | None:
        if self._scheduled_runtime_ports_are_injected():
            return (
                self._scheduled_leases,
                self._scheduled_recovery,
                self._scheduled_retries,
                self._run_states,
            )
        if self.container is None:
            return None

        async with self.container() as request_container:
            scheduled_leases = self._scheduled_leases or await request_container.get(
                ScheduledLeasePort
            )
            scheduled_recovery = self._scheduled_recovery or await request_container.get(
                ScheduledRecoveryPort
            )
            scheduled_retries = self._scheduled_retries or await request_container.get(
                ScheduledRetryPort
            )
            run_states = self._run_states or await request_container.get(PipelineRunStatePort)
            return scheduled_leases, scheduled_recovery, scheduled_retries, run_states

    def _scheduled_runtime_ports_are_injected(self) -> bool:
        return (
            self._scheduled_leases is not None
            and self._scheduled_recovery is not None
            and self._scheduled_retries is not None
            and self._run_states is not None
        )

    def _has_scheduled_runtime_ports(self) -> bool:
        if self._scheduled_runtime_ports_are_injected():
            return True
        return self.container is not None

    def get_graph(self) -> Dict[str, Any]:
        """
        Get pipeline graph structure for visualization.

        Returns:
            Graph representation with nodes and edges
        """
        nodes = []
        edges = []

        for node_id, node in self._nodes.items():
            event_in_str = [e.value if hasattr(e, 'value') else str(e) for e in node.event_in]
            event_out_str = [e.value if hasattr(e, 'value') else str(e) for e in node.event_out]

            nodes.append({
                "id": node_id,
                "event_in": event_in_str,
                "event_out": event_out_str,
                "max_parallelism": node.max_parallelism,
            })

            for out_event in node.event_out:
                out_event_str = out_event.value if hasattr(out_event, 'value') else str(out_event)
                target_nodes = self._event_to_nodes.get(out_event_str, set())
                for target_id in target_nodes:
                    edges.append({
                        "from": node_id,
                        "to": target_id,
                        "event": out_event_str,
                    })

        return {"nodes": nodes, "edges": edges}
