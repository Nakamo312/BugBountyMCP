"""Execution helpers for ScanNode."""
from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Dict, List
from uuid import UUID, uuid4

from api.application.contracts import RunnerInvocationContext, ToolInvocation
from api.application.pipeline.context import PipelineContext
from api.application.pipeline.ingestion import ingest_with_optional_context
from api.application.pipeline.extractors import normalize_targets
from api.application.pipeline.invocation import (
    build_invocation,
    build_runner_context,
    metadata,
    run_raw,
)
from api.application.event_contracts import EventType
from api.application.process_event_contracts import ProcessEvent
from api.application.ports.runners import ToolRunnerFactoryPort, ToolRunnerRef


@dataclass(slots=True)
class ScanRuntime:
    """Public execution contract consumed by scan helpers.

    The helpers no longer reach back into private ``ScanNode`` state. ``ScanNode``
    builds this contract from its own internals and the executor receives only
    the fields/functions it needs for one scan run.
    """

    node_id: str
    logger: Any
    event_out_map: Mapping[EventType, str]
    runner_type: Any | ToolRunnerRef
    processor_type: Any
    ingestor_type: Any
    parser_factory: Callable[[], Any] | None
    target_extractor: Callable[[Dict[str, Any]], List[str]]
    runner_name: str
    semaphore: Any
    enforce_execution_context: Callable[
        [Dict[str, Any], ToolInvocation | None, RunnerInvocationContext | None],
        None,
    ]
    target_shape: str = "list"


@dataclass(slots=True)
class ProcessEventSummary:
    stdout: int = 0
    stderr: int = 0
    started: int = 0
    terminated: int = 0
    failed: int = 0
    timeout: int = 0
    returncode: int | None = None
    first_failure: str | None = None

    def observe(self, event: ProcessEvent) -> None:
        if event.type == "stdout":
            self.stdout += 1
        elif event.type == "stderr":
            self.stderr += 1
        elif event.type == "started":
            self.started += 1
        elif event.type == "terminated":
            self.terminated += 1
            self.returncode = _parse_returncode(event.payload)
        elif event.type == "failed":
            self.failed += 1
            if self.first_failure is None:
                self.first_failure = str(event.payload or "process failed")
        elif event.type == "timeout":
            self.timeout += 1
            if self.first_failure is None:
                self.first_failure = "process timeout"

    @property
    def has_stdout(self) -> bool:
        return self.stdout > 0


@dataclass(slots=True)
class ScanExecutionContext:
    """Resolved runtime inputs for one ScanNode event."""

    program_id: UUID
    job_id: UUID | None
    run_id: UUID | None
    targets: list[str]
    runner: Any
    processor: Any | None
    ingestor: Any | None
    parser: Any
    parser_name: str
    parser_version: str
    invocation: ToolInvocation | None
    runner_context: RunnerInvocationContext | None
    raw_artifact_id: UUID
    ingest_context: Any | None = None
    process_summary: ProcessEventSummary = field(default_factory=ProcessEventSummary)


async def run_scan_execution(
    runtime: ScanRuntime,
    event: Dict[str, Any],
    ctx: PipelineContext,
) -> int | None:
    """Execute one scan event through explicit runtime functions."""
    execution = await prepare_scan_execution(runtime, event, ctx)
    if execution is None:
        return None

    try:
        batch_count = await run_scan_stream(runtime, event, ctx, execution)
        runtime.logger.info(
            f"Scan completed: node={runtime.node_id} program={execution.program_id} batches={batch_count}"
        )
        return batch_count
    except Exception as exc:
        runtime.logger.error(
            f"Scan failed: node={runtime.node_id} program={execution.program_id} error={exc}",
            exc_info=True,
        )
        raise


async def prepare_scan_execution(
    runtime: ScanRuntime,
    event: Dict[str, Any],
    ctx: PipelineContext,
) -> ScanExecutionContext | None:
    """Resolve ids, targets, runner, parser, and execution lineage."""
    program_id = UUID(event["program_id"])
    job_id = UUID(event["job_id"]) if event.get("job_id") else None
    run_id = UUID(event["run_id"]) if event.get("run_id") else None
    targets = normalize_targets(runtime.target_extractor(event))

    if not targets:
        event_name = event.get("_event_type") or event.get("event") or runtime.node_id
        raise RuntimeError(
            f"ScanNode '{runtime.node_id}' cannot run {event_name}: no targets extracted"
        )

    runtime.logger.info(
        f"Starting scan: node={runtime.node_id} program={program_id} targets={len(targets)}"
    )

    runner, processor, ingestor = await resolve_scan_dependencies(runtime, ctx)
    validate_runner_contract(runtime, runner)

    parser = runtime.parser_factory()
    parser_name, parser_version = parser_metadata(parser)
    invocation = build_invocation(event, targets)
    runner_context = build_runner_context(event, targets, node_id=runtime.node_id)
    runtime.enforce_execution_context(event, invocation, runner_context)

    return ScanExecutionContext(
        program_id=program_id,
        job_id=job_id,
        run_id=run_id,
        targets=targets,
        runner=runner,
        processor=processor,
        ingestor=ingestor,
        parser=parser,
        parser_name=parser_name,
        parser_version=parser_version,
        invocation=invocation,
        runner_context=runner_context,
        raw_artifact_id=uuid4(),
    )


async def run_scan_stream(
    runtime: ScanRuntime,
    event: Dict[str, Any],
    ctx: PipelineContext,
    execution: ScanExecutionContext,
) -> int:
    """Capture runner output, parse it, batch it when configured, then ingest."""
    stream = capture_raw_artifact(runtime, event, ctx, execution)
    batch_count = 0
    item_count = 0
    if execution.processor is not None:
        async for batch in execution.processor.batch_stream(stream):
            if not batch:
                continue
            batch_count += 1
            item_count += len(batch)
            await ingest_and_emit(
                runtime,
                ctx=ctx,
                execution=execution,
                items=batch,
                allow_passthrough=True,
            )
        await report_empty_parse_if_needed(runtime, ctx, execution, item_count)
        return batch_count

    results = []
    async for parsed_event in stream:
        if parsed_event.type == "result" and parsed_event.payload:
            results.append(parsed_event.payload)
    item_count = len(results)
    if not results:
        await report_empty_parse_if_needed(runtime, ctx, execution, item_count)
        return 0

    await ingest_and_emit(
        runtime,
        ctx=ctx,
        execution=execution,
        items=results,
        allow_passthrough=False,
    )
    await report_empty_parse_if_needed(runtime, ctx, execution, item_count)
    return 1


async def resolve_scan_dependencies(
    runtime: ScanRuntime,
    ctx: PipelineContext,
) -> tuple[Any, Any | None, Any | None]:
    runner = await resolve_runner(runtime, ctx)
    processor = None
    if runtime.processor_type is not None and runtime.processor_type is not type(None):
        processor = await ctx.get_service(runtime.processor_type)
    ingestor = None
    if runtime.ingestor_type is not None and runtime.ingestor_type is not type(None):
        ingestor = await ctx.get_service(runtime.ingestor_type)
    return runner, processor, ingestor


def validate_runner_contract(runtime: ScanRuntime, runner: Any) -> None:
    if runtime.parser_factory is None:
        raise RuntimeError(f"ScanNode '{runtime.node_id}' requires an explicit parser")
    if not hasattr(runner, "run_raw"):
        raise RuntimeError(
            f"Runner '{runtime.runner_name}' used by ScanNode '{runtime.node_id}' "
            "must expose run_raw()"
        )


def parser_metadata(parser: Any) -> tuple[str, str]:
    return (
        type(parser).__name__,
        str(getattr(parser, "parser_version", getattr(parser, "PARSER_VERSION", "1"))),
    )


def capture_raw_artifact(
    runtime: ScanRuntime,
    event: Dict[str, Any],
    ctx: PipelineContext,
    execution: ScanExecutionContext,
):
    effective_context = execution.invocation or execution.runner_context
    stream = run_raw_with_runtime_limit(
        runtime.semaphore,
        execution.runner,
        execution.targets,
        effective_context,
        target_shape=runtime.target_shape,
    )

    if isinstance(ctx, PipelineContext):
        ctx.set_downstream_parent_artifact(execution.raw_artifact_id)
        if execution.runner_context is not None:
            ctx.set_current_runner_context(execution.runner_context)
        stream = ctx.capture_raw_stream(
            stream,
            program_id=execution.program_id,
            event_name=event.get("event", runtime.node_id),
            targets=execution.targets,
            job_id=execution.job_id,
            run_id=execution.run_id,
            artifact_id=execution.raw_artifact_id,
            metadata={
                "runner": runtime.runner_name,
                **metadata(execution.invocation, execution.runner_context),
            },
            parser_name=execution.parser_name,
            parser_version=execution.parser_version,
            scope_decision_id=context_value(execution, "scope_decision_id"),
            parent_artifact_id=context_value(execution, "parent_artifact_id"),
        )
        execution.ingest_context = ctx.ingest_context(execution.raw_artifact_id)

    return execution.parser.parse_stream(checked_process_stream(stream, execution))



async def checked_process_stream(
    stream,
    execution: ScanExecutionContext,
):
    async for event in stream:
        execution.process_summary.observe(event)
        failure = process_event_failure(event)
        if failure is not None:
            raise RuntimeError(failure)
        yield event


def process_event_failure(event: ProcessEvent) -> str | None:
    if event.type == "failed":
        return f"process failed: {event.payload or 'unknown error'}"
    if event.type == "timeout":
        return "process timed out"
    if event.type == "terminated":
        returncode = _parse_returncode(event.payload)
        if returncode is not None and returncode != 0:
            return f"process exited with returncode={returncode}"
    return None


def _parse_returncode(value: object) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


async def report_empty_parse_if_needed(
    runtime: ScanRuntime,
    ctx: PipelineContext,
    execution: ScanExecutionContext,
    item_count: int,
) -> None:
    if item_count > 0:
        return
    summary = execution.process_summary
    if summary.has_stdout:
        reason = "parser_produced_no_records_from_stdout"
        runtime.logger.warning(
            "Parser produced no records from non-empty stdout: "
            "node=%s program=%s stdout_events=%s stderr_events=%s returncode=%s parser=%s",
            runtime.node_id,
            execution.program_id,
            summary.stdout,
            summary.stderr,
            summary.returncode,
            execution.parser_name,
        )
        if isinstance(ctx, PipelineContext):
            await ctx.mark_run_needs_reconcile(reason)


def context_value(execution: ScanExecutionContext, name: str):
    if execution.invocation is not None:
        return getattr(execution.invocation, name)
    if execution.runner_context is not None:
        return getattr(execution.runner_context, name)
    return None


async def ingest_and_emit(
    runtime: ScanRuntime,
    *,
    ctx: PipelineContext,
    execution: ScanExecutionContext,
    items: list[Any],
    allow_passthrough: bool,
) -> None:
    if execution.ingestor is None:
        if allow_passthrough:
            await emit_items(runtime, ctx, execution.program_id, items, confidence=0.9)
        return

    ingest_result = await ingest_with_optional_context(
        execution.ingestor,
        execution.program_id,
        items,
        execution.ingest_context,
    )
    await emit_ingest_result(runtime, ctx, execution.program_id, ingest_result)


async def emit_ingest_result(
    runtime: ScanRuntime,
    ctx: PipelineContext,
    program_id: UUID,
    ingest_result: Any,
) -> None:
    for event_type, result_key in runtime.event_out_map.items():
        data = getattr(ingest_result, result_key, [])
        if data:
            await emit_event(runtime, ctx, event_type, data, program_id, confidence=0.7)


async def emit_items(
    runtime: ScanRuntime,
    ctx: PipelineContext,
    program_id: UUID,
    items: list[Any],
    *,
    confidence: float,
) -> None:
    for event_type in runtime.event_out_map:
        if items:
            await emit_event(runtime, ctx, event_type, items, program_id, confidence=confidence)


async def emit_event(
    runtime: ScanRuntime,
    ctx: PipelineContext,
    event_type: EventType,
    targets: list[Any],
    program_id: UUID,
    *,
    confidence: float,
) -> None:
    event_name = event_type.value if hasattr(event_type, "value") else str(event_type)
    await ctx.emit(
        event=event_name,
        targets=targets,
        program_id=program_id,
        confidence=confidence,
    )
    runtime.logger.debug(f"Emitted {event_name}: {len(targets)} items")


async def resolve_runner(runtime: ScanRuntime, ctx: PipelineContext) -> Any:
    if isinstance(runtime.runner_type, ToolRunnerRef):
        factory = await ctx.get_service(ToolRunnerFactoryPort)
        return factory.create(
            runtime.runner_type.tool_name,
            **dict(runtime.runner_type.default_options),
        )
    return await ctx.get_service(runtime.runner_type)


def run_raw_with_runtime_limit(
    semaphore: Any,
    runner: Any,
    targets: List[str],
    context: ToolInvocation | RunnerInvocationContext | None,
    *,
    target_shape: str = "list",
):
    """Run the CLI runner while honoring manifest runtime target shape."""

    async def limited_stream():
        async with semaphore:
            if target_shape == "scalar":
                for target in targets:
                    stream = run_raw(runner, target, context)
                    async for item in stream:
                        yield item
                return

            stream = run_raw(runner, targets, context)
            async for item in stream:
                yield item

    return limited_stream()
