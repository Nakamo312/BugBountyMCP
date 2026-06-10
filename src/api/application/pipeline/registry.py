"""Node registry for event routing"""
from typing import Any, Dict, Mapping, Set
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from api.application.contracts import ExecutionMode
from api.application.pipeline.fingerprints import (
    build_node_claim_key,
    build_node_input_fingerprint,
    build_node_work_key,
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

        scheduled_nodes = [
            node.node_id
            for node in self._nodes.values()
            if node.execution_mode == ExecutionMode.SCHEDULED
        ]

        logger.debug(
            "Scheduled executor start check: enabled=%s container=%s store=%s scheduled_nodes=%s",
            self.settings.PIPELINE_SCHEDULER_ENABLED,
            self.container is not None,
            self._orchestration_store is not None,
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
                "Scheduled executor not started: enabled=%s container=%s store=%s scheduled_nodes=%s",
                self.settings.PIPELINE_SCHEDULER_ENABLED,
                self.container is not None,
                self._orchestration_store is not None,
                scheduled_nodes,
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

        node = self._nodes[node_id]
        trigger_event_id = UUID(str(event["event_id"]))
        claim_events = self._claim_events_for_node(node, event)
        last_claim = None
        for claim_event in claim_events:
            input_fingerprint = build_node_input_fingerprint(node_id, claim_event)
            target_fingerprint = build_target_fingerprint(claim_event.get("targets", []))
            claim_key = build_node_claim_key(
                trigger_event_id=trigger_event_id,
                node_id=node_id,
                input_fingerprint=input_fingerprint,
            )
            last_claim = await store.claim_node_run(
                claim_key=claim_key,
                job_id=UUID(str(event["job_id"])),
                program_id=UUID(str(event["program_id"])),
                node_id=node_id,
                event_name=event_name,
                trigger_event_id=trigger_event_id,
                input_fingerprint=input_fingerprint,
                target_fingerprint=target_fingerprint,
                execution_mode=node.execution_mode,
                next_run_at=self._scheduled_next_run_at(node_id),
                target_count=self._target_count(claim_event),
                run_payload=self._run_payload_for_event(claim_event),
                work_key=self._work_key_for_event(node, event_name, claim_event),
                coalesced_trigger=(
                    self._coalesced_trigger_for_event(claim_event)
                    if node.execution_mode == ExecutionMode.SCHEDULED
                    else None
                ),
                retry_policy=(
                    dict(node.retry_policy)
                    if node.execution_mode == ExecutionMode.SCHEDULED
                    else None
                ),
            )
            if last_claim.is_terminal and node.execution_mode != ExecutionMode.SCHEDULED:
                return None

        if node.execution_mode == ExecutionMode.SCHEDULED:
            return None

        if last_claim is None or last_claim.is_terminal:
            return None

        claimed_event = dict(claim_events[0])
        claimed_event["run_id"] = str(last_claim.run_id)
        return claimed_event

    def _claim_events_for_node(self, node: Node, event: Dict[str, Any]) -> list[Dict[str, Any]]:
        if node.execution_mode != ExecutionMode.SCHEDULED:
            return [dict(event)]

        max_targets = node.max_targets_per_run
        targets = list(event.get("targets") or [])
        if max_targets is None or max_targets <= 0 or len(targets) <= max_targets:
            return [dict(event)]

        chunks = []
        for offset in range(0, len(targets), max_targets):
            chunk_targets = targets[offset : offset + max_targets]
            chunk_event = dict(event)
            chunk_event["targets"] = chunk_targets
            if chunk_targets:
                chunk_event["target"] = chunk_targets[0]
            chunks.append(chunk_event)
        return chunks

    @staticmethod
    def _target_count(event: Dict[str, Any]) -> int | None:
        targets = event.get("targets")
        if isinstance(targets, list):
            return len(targets)
        return None

    @staticmethod
    def _run_payload_for_event(event: Dict[str, Any]) -> Dict[str, Any]:
        return {
            key: value
            for key, value in event.items()
            if key not in {"event_id", "created_at"}
        }

    def _work_key_for_event(
        self,
        node: Node,
        event_name: str,
        event: Dict[str, Any],
    ) -> str | None:
        if node.execution_mode != ExecutionMode.SCHEDULED:
            return None
        return build_node_work_key(
            program_id=event["program_id"],
            node_id=node.node_id,
            event_name=event_name,
            targets=event.get("targets", []),
            profile=event.get("profile"),
            options=event.get("options") or event.get("payload") or {},
            scan_mode=event.get("scan_mode") or event.get("mode"),
            node_work_identity=self._node_work_identity(node),
        )

    @staticmethod
    def _coalesced_trigger_for_event(event: Dict[str, Any]) -> Dict[str, Any] | None:
        if not event.get("event_id"):
            return None
        metadata = {
            "trigger_event_id": str(event["event_id"]),
            "job_id": str(event["job_id"]) if event.get("job_id") else None,
            "run_id": str(event["run_id"]) if event.get("run_id") else None,
            "correlation_id": (
                str(event["correlation_id"]) if event.get("correlation_id") else None
            ),
            "reason": "scheduled_active_exact_dedup",
        }
        return {key: value for key, value in metadata.items() if value is not None}

    @staticmethod
    def _node_work_identity(node: Node) -> Dict[str, Any]:
        def component_name(value) -> str | None:
            if value is None:
                return None
            return getattr(value, "__name__", str(value))

        identity = {
            "node_class": type(node).__name__,
            "runner": component_name(
                getattr(node, "runner_type", None) or getattr(node, "runner_key", None)
            ),
            "parser": component_name(
                getattr(node, "parser_type", None) or getattr(node, "parser_key", None)
            ),
            "processor": component_name(
                getattr(node, "processor_type", None) or getattr(node, "processor_key", None)
            ),
            "ingestor": component_name(
                getattr(node, "ingestor_type", None)
                or getattr(node, "ingestor_key", None)
                or getattr(node, "host_ingestor_key", None)
            ),
            "target_extractor": component_name(getattr(node, "target_extractor", None)),
            "scope_policy": str(getattr(node, "scope_policy", "")),
            "max_targets_per_run": node.max_targets_per_run,
            "event_out": sorted(
                event.value if hasattr(event, "value") else str(event)
                for event in node.event_out
            ),
        }
        return {key: value for key, value in identity.items() if value not in (None, "")}

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

            local_inflight = sum(
                1
                for task in self._scheduled_node_tasks.get(node_id, set())
                if not task.done()
            )
            durable_inflight = int(active_runs_by_node.get(node_id, 0) or 0)
            inflight = max(local_inflight, durable_inflight)
            available = max(node.max_parallelism - inflight, 0)
            node_limit = min(available, batch_size)
            if node_limit <= 0:
                continue

            limits[node_id] = node_limit

        return limits

    async def _drain_scheduled_node_runs_once(self) -> None:
        store = await self._get_orchestration_store()
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
                    "Leased scheduled run for unknown node: node=%s run_id=%s",
                    leased_run.node_id,
                    leased_run.run_id,
                )
                continue

            self._launch_scheduled_node_task(
                node_id=leased_run.node_id,
                node=node,
                event=leased_run.event,
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
