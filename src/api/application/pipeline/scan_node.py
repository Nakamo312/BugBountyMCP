"""Generic scan node for CLI tools"""
import asyncio
from typing import Dict, Any, Set, Optional, Callable, List
import logging

from api.application.pipeline.node import Node
from api.application.pipeline.context import PipelineContext
from api.infrastructure.events.event_types import EventType
from api.infrastructure.runners.cli_tool import CliToolRunnerRef
from api.application.pipeline.scope_policy import ScopePolicy
from api.application.pipeline.scan_execution import ScanRuntime, run_scan_execution
from api.application.contracts import (
    ExecutionMode,
    RunnerInvocationContext,
    SafetyLevel,
    ToolInvocation,
)

logger = logging.getLogger(__name__)


class ScanNode(Node):
    legacy_context_fallback = True

    """
    Generic node for CLI scan tools.
    Gets dependencies from DI container on each execution.

    Event Flow:
    1. Receive event from EventBus
    2. Extract targets via target_extractor
    3. Get runner/processor/ingestor from DI (REQUEST scope)
    4. Run: runner → parser → batch processor
    5. Capture raw artifact before parsing
    6. Ingest normalized state
    7. Emit deterministic events from IngestResult
    """

    def __init__(
        self,
        node_id: str,
        event_in: Set[EventType],
        event_out: Dict[EventType, str],
        runner_type: Any | CliToolRunnerRef,
        processor_type: Any,
        parser_type: Optional[Callable[[], Any]] = None,
        ingestor_type: Any = None,
        target_extractor: Optional[Callable[[Dict[str, Any]], List[str]]] = None,
        max_parallelism: int = 1,
        execution_delay: int = 0,
        execution_mode: ExecutionMode = ExecutionMode.INLINE,
        max_targets_per_run: int | None = None,
        cooldown_seconds: int | float = 0,
        max_fanout_per_event: int | None = None,
        max_expansion_depth: int | None = None,
        token_cost: int | float = 1,
        retry_policy: dict | None = None,
        scope_policy=ScopePolicy.NONE,
        runtime: Any | None = None,
        runtime_concurrency: int | None = None,
        requires_execution_context: bool = False,
    ):
        """
        Initialize generic scan node.

        Args:
            node_id: Unique node identifier
            event_in: Set of event types this node accepts
            event_out: Map of event_type → result_key for emitting
            runner_type: Runner class (will be resolved from DI)
            processor_type: Processor class (will be resolved from DI)
            ingestor_type: Optional ingestor class (will be resolved from DI)
            target_extractor: Function to extract targets from event
            max_parallelism: Maximum concurrent executions
            execution_delay: Delay in seconds before executing (default: 0)
        """
        super().__init__(
            node_id=node_id,
            event_in=event_in,
            event_out=set(event_out.keys()),
            max_parallelism=max_parallelism,
            execution_delay=execution_delay,
            execution_mode=execution_mode,
            max_targets_per_run=max_targets_per_run,
            cooldown_seconds=cooldown_seconds,
            max_fanout_per_event=max_fanout_per_event,
            max_expansion_depth=max_expansion_depth,
            token_cost=token_cost,
            retry_policy=retry_policy,
        )
        self.event_out_map = event_out
        self.runner_type = runner_type
        self.runner_key = self._runner_name()
        self.parser_type = parser_type
        self.processor_type = processor_type
        self.ingestor_type = ingestor_type
        self.target_extractor = target_extractor or self._default_target_extractor
        self.scope_policy = scope_policy
        self.runtime_mode = getattr(runtime, "mode", "batch") if runtime is not None else "batch"
        self.target_shape = getattr(runtime, "target_shape", "list") if runtime is not None else "list"
        self.artifact_mode = getattr(runtime, "artifact", "per_run") if runtime is not None else "per_run"
        self.requires_execution_context = requires_execution_context
        self._scan_semaphore = asyncio.Semaphore(runtime_concurrency or max_parallelism)

    async def execute(self, event: Dict[str, Any], ctx: PipelineContext):
        """Execute scan: extract targets → run → parse → ingest → emit."""
        await run_scan_execution(self._scan_runtime(), event, ctx)

    def _scan_runtime(self) -> ScanRuntime:
        return ScanRuntime(
            node_id=self.node_id,
            logger=self.logger,
            event_out_map=self.event_out_map,
            runner_type=self.runner_type,
            processor_type=self.processor_type,
            ingestor_type=self.ingestor_type,
            parser_factory=self.parser_type,
            target_extractor=self.target_extractor,
            runner_name=self.runner_key,
            semaphore=self._scan_semaphore,
            enforce_execution_context=self._enforce_execution_context,
        )

    def _runner_name(self) -> str:
        if isinstance(self.runner_type, CliToolRunnerRef):
            return str(self.runner_type)
        return getattr(self.runner_type, "__name__", str(self.runner_type))

    def _enforce_execution_context(
        self,
        event: Dict[str, Any],
        invocation: ToolInvocation | None,
        runner_context: RunnerInvocationContext | None,
    ) -> None:
        """Fail closed when a controlled scan would run without lineage.

        Direct action events must carry a complete ToolInvocation payload.
        Downstream events may use RunnerInvocationContext, but scoped or
        explicitly context-required nodes still need root action lineage and
        inherited hard ceilings before a runner is invoked.
        """
        if invocation is None and self._has_partial_action_context(event):
            raise RuntimeError(
                f"ScanNode '{self.node_id}' received incomplete action context; "
                "refusing to run without a complete ToolInvocation"
            )

        if not self._requires_control_context(event, runner_context):
            return

        if invocation is not None:
            return

        if runner_context is None:
            raise RuntimeError(
                f"ScanNode '{self.node_id}' requires execution context but none was provided"
            )

        missing: list[str] = []
        if runner_context.root_action_id is None:
            missing.append("root_action_id")
        if runner_context.execution_budget is None:
            missing.append("execution_budget")
        if runner_context.safety_level is None:
            missing.append("safety_level")
        if runner_context.policy_decision_id is None:
            missing.append("policy_decision_id")
        if self.scope_policy is not ScopePolicy.NONE and runner_context.scope_decision_id is None:
            missing.append("scope_decision_id")

        if missing:
            raise RuntimeError(
                f"ScanNode '{self.node_id}' requires complete runner context; "
                f"missing: {', '.join(missing)}"
            )

    def _requires_control_context(
        self,
        event: Dict[str, Any],
        runner_context: RunnerInvocationContext | None,
    ) -> bool:
        if self.requires_execution_context:
            return True
        if self.scope_policy is not ScopePolicy.NONE:
            return True
        safety_level = runner_context.safety_level if runner_context is not None else None
        if safety_level is None:
            safety_level = self._event_safety_level(event)
        return safety_level in {
            SafetyLevel.SAFE_ACTIVE,
            SafetyLevel.ACTIVE,
            SafetyLevel.SENSITIVE,
        }

    @staticmethod
    def _event_safety_level(event: Dict[str, Any]) -> SafetyLevel | None:
        payload = event.get("payload")
        payload = payload if isinstance(payload, dict) else {}
        lineage = payload.get("execution_lineage")
        lineage = lineage if isinstance(lineage, dict) else {}
        value = (
            event.get("safety_level")
            or payload.get("safety_level")
            or lineage.get("root_safety_level")
        )
        if value is None:
            return None
        try:
            return SafetyLevel(str(value))
        except ValueError:
            return None

    @staticmethod
    def _has_partial_action_context(event: Dict[str, Any]) -> bool:
        action_fields = {
            "action_id",
            "capability_id",
            "profile_id",
            "safety_level",
            "policy_decision_id",
            "scope_decision_id",
            "execution_budget",
        }
        return any(event.get(field) is not None for field in action_fields)

    def set_context_factory(self, bus, container, settings, context_factory=None):
        """
        Set dependencies for context creation.
        Called by NodeRegistry after node creation.

        Args:
            bus: EventBus instance
            container: DI container
            settings: Application settings
            context_factory: Optional PipelineContextFactory with explicit ports.
        """
        self._bus = bus
        self._container = container
        self._settings = settings
        self._context_factory = context_factory

    async def _create_context(self) -> PipelineContext:
        """
        Create context with EventBus/DI/Settings injected.

        Returns:
            Pipeline context with all dependencies
        """
        context_factory = getattr(self, '_context_factory', None)
        if context_factory is not None:
            return context_factory.create(
                node_id=self.node_id,
                bus=getattr(self, '_bus', None),
                container=getattr(self, '_container', None),
                settings=getattr(self, '_settings', None),
                scope_policy=self.scope_policy,
            )

        # Legacy-only path for direct ScanNode/NodeRegistry construction in old
        # tests and adapters. Production wiring must pass PipelineContextFactory;
        # this fallback intentionally has no raw capture, run-state, outcome, or
        # scope-filter ports.
        return PipelineContext(
            node_id=self.node_id,
            bus=getattr(self, '_bus', None),
            container=getattr(self, '_container', None),
            settings=getattr(self, '_settings', None),
            scope_policy=self.scope_policy
        )

    @staticmethod
    def _default_target_extractor(event: Dict[str, Any]) -> List[str]:
        """
        Default target extractor - expects 'targets' field.

        Args:
            event: Event payload with 'targets' list

        Returns:
            List of targets (URLs, hosts, IPs, subdomains, etc.)
        """
        return event.get("targets", [])
