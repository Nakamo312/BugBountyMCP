"""Node registry for event routing"""
from typing import Dict, Set, Any
import asyncio
import logging
from uuid import UUID

from api.application.contracts import ExecutionMode
from api.application.pipeline.fingerprints import (
    build_node_claim_key,
    build_node_input_fingerprint,
    build_target_fingerprint,
)
from api.infrastructure.events.event_bus import EventBus
from api.infrastructure.events.queue_config import QueueConfig
from api.application.pipeline.node import Node
from api.config import Settings

logger = logging.getLogger(__name__)


class NodeRegistry:
    """
    Thin dispatcher that routes events to registered nodes.
    Replaces monolithic Orchestrator with declarative subscription model.

    Subscribes to fixed queues (discovery, enumeration, validation, analysis)
    and routes events to nodes based on event type strings.
    """

    def __init__(
        self,
        bus: EventBus,
        settings: Settings,
        container=None,
        orchestration_store=None,
    ):
        """
        Initialize node registry.

        Args:
            bus: EventBus for pub/sub
            settings: Application settings
            container: Optional DI container for node context
        """
        self.bus = bus
        self.settings = settings
        self.container = container
        self._orchestration_store = orchestration_store
        self._nodes: Dict[str, Node] = {}
        self._event_to_nodes: Dict[str, Set[str]] = {}
        self._subscription_tasks: Set[asyncio.Task] = set()
        self._scheduled_executor_task: asyncio.Task | None = None
        self._worker_heartbeat_task: asyncio.Task | None = None

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
            node.set_context_factory(self.bus, self.container, self.settings)

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
        """Start EventBus subscriptions for all fixed queues"""
        await self.bus.connect()

        for queue_name in QueueConfig.get_all_queues():
            task = asyncio.create_task(self.bus.subscribe(queue_name, self._dispatch_event))
            self._subscription_tasks.add(task)
            task.add_done_callback(self._subscription_tasks.discard)

        self._heartbeat_workers()
        self._worker_heartbeat_task = asyncio.create_task(self._run_worker_heartbeat())

        if self._should_start_scheduled_executor():
            self._scheduled_executor_task = asyncio.create_task(
                self._run_scheduled_executor()
            )

        logger.info(
            f"NodeRegistry started: {len(self._nodes)} nodes, "
            f"{len(self._event_to_nodes)} event types, "
            f"{len(QueueConfig.get_all_queues())} queues"
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

        stop_tasks = [node.stop() for node in self._nodes.values()]
        await asyncio.gather(*stop_tasks, return_exceptions=True)

        logger.info("NodeRegistry stopped")

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
                    "Claimed scheduled node run: node=%s event=%s",
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

    async def _claim_event_for_node(
        self,
        node_id: str,
        event_name: str,
        event: Dict[str, Any],
    ) -> Dict[str, Any] | None:
        store = await self._get_orchestration_store()
        if store is None:
            return dict(event)

        trigger_event_id = UUID(str(event["event_id"]))
        input_fingerprint = build_node_input_fingerprint(node_id, event)
        target_fingerprint = build_target_fingerprint(event.get("targets", []))
        claim_key = build_node_claim_key(
            trigger_event_id=trigger_event_id,
            node_id=node_id,
            input_fingerprint=input_fingerprint,
        )
        claim = await store.claim_node_run(
            claim_key=claim_key,
            job_id=UUID(str(event["job_id"])),
            program_id=UUID(str(event["program_id"])),
            node_id=node_id,
            event_name=event_name,
            trigger_event_id=trigger_event_id,
            input_fingerprint=input_fingerprint,
            target_fingerprint=target_fingerprint,
            execution_mode=self._nodes[node_id].execution_mode,
        )
        if claim.is_terminal:
            return None

        if self._nodes[node_id].execution_mode == ExecutionMode.SCHEDULED:
            return None

        claimed_event = dict(event)
        claimed_event["run_id"] = str(claim.run_id)
        return claimed_event

    def _should_start_scheduled_executor(self) -> bool:
        if not self.settings.PIPELINE_SCHEDULED_EXECUTOR_ENABLED:
            return False
        if self.container is None and self._orchestration_store is None:
            return False
        return any(
            node.execution_mode == ExecutionMode.SCHEDULED
            for node in self._nodes.values()
        )

    async def _run_scheduled_executor(self) -> None:
        while True:
            try:
                await self._drain_scheduled_node_runs_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Scheduled node executor tick failed")
            await asyncio.sleep(self.settings.PIPELINE_SCHEDULED_EXECUTOR_POLL_SECONDS)

    async def _drain_scheduled_node_runs_once(self) -> None:
        store = await self._get_orchestration_store()
        if store is None:
            return

        await store.requeue_retryable_node_runs(
            retry_policies=self._retry_policies_by_node(),
        )
        leased_runs = await store.lease_scheduled_node_runs(
            limit=self.settings.PIPELINE_SCHEDULED_EXECUTOR_BATCH_SIZE,
        )
        if not leased_runs:
            return

        tasks = []
        for leased_run in leased_runs:
            node = self._nodes.get(leased_run.node_id)
            if node is None:
                logger.error(
                    "Leased scheduled run for unknown node: node=%s run_id=%s",
                    leased_run.node_id,
                    leased_run.run_id,
                )
                continue
            tasks.append(
                (
                    leased_run.node_id,
                    asyncio.create_task(node.handle_event(leased_run.event)),
                )
            )

        if not tasks:
            return

        results = await asyncio.gather(
            *(task for _, task in tasks),
            return_exceptions=True,
        )
        for (node_id, _), result in zip(tasks, results):
            if isinstance(result, Exception):
                logger.error(
                    "Scheduled node run failed: node=%s error=%s",
                    node_id,
                    result,
                    exc_info=(type(result), result, result.__traceback__),
                )

    def _retry_policies_by_node(self) -> dict[str, dict[str, Any]]:
        return {
            node_id: dict(node.retry_policy)
            for node_id, node in self._nodes.items()
            if node.execution_mode == ExecutionMode.SCHEDULED
        }

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

    async def _get_orchestration_store(self):
        if self._orchestration_store is not None:
            return self._orchestration_store
        if self.container is None:
            return None

        from api.infrastructure.orchestration.store import OrchestrationStore

        async with self.container() as request_container:
            return await request_container.get(OrchestrationStore)

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
