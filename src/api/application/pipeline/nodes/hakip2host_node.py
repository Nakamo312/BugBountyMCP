"""Hakip2host Node - reverse IP to hostname resolution"""

import logging
from typing import Dict, Any, Set, Type
from uuid import UUID, uuid4

from api.application.pipeline.node import Node
from api.application.pipeline.context import PipelineContext
from api.infrastructure.events.event_types import EventType
from api.application.pipeline.scope_policy import ScopePolicy
from api.application.pipeline.ingestion import ingest_with_optional_context
from api.application.contracts import ExecutionMode

logger = logging.getLogger(__name__)


class Hakip2HostNode(Node):
    """
    Hakip2host reverse resolution node.

    Input events: IPS_EXPANDED
    Output events:
      - SUBDOMAIN_DISCOVERED (hostnames from PTR/SSL-SAN/SSL-CN)
    """

    def __init__(
        self,
        node_id: str,
        event_in: Set[EventType],
        runner_key: Type[Any],
        parser_key: Type[Any],
        processor_key: Type[Any],
        host_ingestor_key: Type[Any],
        event_out: Set[EventType] | None = None,
        max_parallelism: int = 1,
        execution_mode: ExecutionMode = ExecutionMode.INLINE,
        retry_policy: dict | None = None,
        scope_policy=ScopePolicy.NONE
    ):
        event_out = event_out or {
            EventType.RAW_DOMAINS_DISCOVERED
        }
        super().__init__(
            node_id=node_id,
            event_in=event_in,
            event_out=event_out,
            max_parallelism=max_parallelism,
            execution_mode=execution_mode,
            retry_policy=retry_policy,
        )
        self.logger = logging.getLogger(f"node.{node_id}")
        self.runner_key = runner_key
        self.parser_key = parser_key
        self.processor_key = processor_key
        self.host_ingestor_key = host_ingestor_key
        self.scope_policy = scope_policy

    def set_context_factory(self, bus, container, settings):
        """
        Set dependencies for context creation.
        Called by NodeRegistry after node creation.
        """
        self._bus = bus
        self._container = container
        self._settings = settings

    async def _create_context(self) -> PipelineContext:
        """Create context with EventBus/DI/Settings injected."""
        return PipelineContext(
            node_id=self.node_id,
            bus=getattr(self, '_bus', None),
            container=getattr(self, '_container', None),
            settings=getattr(self, '_settings', None),
            scope_policy=self.scope_policy
        )

    async def execute(self, event: Dict[str, Any], ctx: PipelineContext):
        """
        Execute hakip2host reverse resolution on IPs.

        Args:
            event: Event with 'targets' field containing IPv4 addresses
            ctx: Node execution context
        """
        program_id = UUID(event["program_id"])
        job_id = UUID(event["job_id"]) if event.get("job_id") else None
        run_id = UUID(event["run_id"]) if event.get("run_id") else None
        targets = event.get("targets", [])

        if not targets:
            self.logger.warning("No targets in event")
            return

        self.logger.info(
            f"Starting reverse resolution: node={self.node_id} program={program_id} ips={len(targets)}"
        )

        runner = await ctx.get_service(self.runner_key)
        parser = self.parser_key()
        processor = await ctx.get_service(self.processor_key)
        host_ingestor = await ctx.get_service(self.host_ingestor_key)

        batch_count = 0
        total_hostnames = 0
        discovered_hostnames = []

        try:
            stream = runner.run_raw(targets)
            raw_artifact_id = uuid4()
            if isinstance(ctx, PipelineContext):
                stream = ctx.capture_raw_stream(
                    stream,
                    program_id=program_id,
                    event_name=event.get("event", self.node_id),
                    targets=targets,
                    job_id=job_id,
                    run_id=run_id,
                    artifact_id=raw_artifact_id,
                    metadata={"runner": self.runner_key.__name__},
                )
            stream = parser.parse_stream(stream)
            ingest_context = ctx.ingest_context(raw_artifact_id) if isinstance(ctx, PipelineContext) else None

            async for batch in processor.batch_stream(stream):
                if not batch:
                    continue

                batch_count += 1

                batch_data = []
                for result in batch:
                    hostname = result.get("hostname")
                    method = result.get("method", "unknown")

                    if not hostname:
                        continue

                    total_hostnames += 1
                    discovered_hostnames.append(hostname)
                    batch_data.append({"host": hostname})
                    self.logger.debug(
                        f"Resolved: {result.get('ip')} -> {hostname} via {method}"
                    )

                if batch_data:
                    await ingest_with_optional_context(
                        host_ingestor,
                        program_id,
                        batch_data,
                        ingest_context,
                    )

            if discovered_hostnames:
                await ctx.emit(
                    event=EventType.RAW_DOMAINS_DISCOVERED.value,
                    targets=discovered_hostnames,
                    program_id=program_id,
                    confidence=0.85
                )
                self.logger.debug(
                    f"Emitted RAW_DOMAINS_DISCOVERED: {len(discovered_hostnames)} hostnames"
                )

            self.logger.info(
                f"Reverse resolution completed: node={self.node_id} program={program_id} "
                f"batches={batch_count} hostnames={total_hostnames}"
            )

        except Exception as exc:
            self.logger.error(
                f"Execution failed for event type={event.get('event')}: {exc}",
                exc_info=True
            )
            raise
