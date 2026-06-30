from __future__ import annotations

import asyncio
import inspect
import logging
from collections.abc import AsyncIterator, Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol

from api.infrastructure.commands.command_boundary import format_command_for_log, summarize_stdin_for_log
from api.infrastructure.commands.command_executor import CommandExecutor
from api.infrastructure.runners.cli_command import (
    CliCommandError,
    StderrPolicy,
    effective_timeout,
    run_cli_command,
)
from api.application.process_event_contracts import ProcessEvent
from api.application.ports.runners import ToolRunnerRef


class ProcessEventParser(Protocol):
    def parse_stream(
        self,
        stream: AsyncIterator[ProcessEvent],
    ) -> AsyncIterator[ProcessEvent]: ...


class ToolErrorPolicy(str, Enum):
    FAIL = "fail"
    LOG_AND_CONTINUE = "log_and_continue"
    CONTINUE_ON_TIMEOUT = "continue_on_timeout"


@dataclass(frozen=True)
class CliCommandPlan:
    command: Sequence[str]
    stdin: str | None = None
    label: str | None = None
    before_events: tuple[ProcessEvent, ...] = ()
    error_policy: ToolErrorPolicy = ToolErrorPolicy.FAIL


@dataclass(frozen=True)
class CliToolSpec:
    name: str
    executable: str
    build_commands: Callable[..., Iterable[CliCommandPlan]]
    parser_factory: Callable[[], ProcessEventParser]
    timeout: int | float
    stderr_policy: StderrPolicy = StderrPolicy.DEBUG
    variants: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    static_options_from_settings: Callable[[Any], Mapping[str, Any]] | None = None
    option_names: frozenset[str] = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "option_names",
            _build_command_option_names(self.build_commands),
        )

    def variant_options(self, variant: str | None) -> dict[str, Any]:
        if variant is None or variant == "default":
            return {}
        try:
            return dict(self.variants[variant])
        except KeyError as exc:
            supported = ", ".join(sorted(self.variants)) or "default"
            raise ValueError(
                f"Unsupported CLI tool variant: cli_tool:{self.name}:{variant}. "
                f"Known variants: {supported}"
            ) from exc


def _build_command_option_names(build_commands: Callable[..., object]) -> frozenset[str]:
    signature = inspect.signature(build_commands)
    names: set[str] = set()
    for param in signature.parameters.values():
        if param.kind is inspect.Parameter.KEYWORD_ONLY:
            names.add(param.name)
        elif (
            param.kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
            and param.default is not inspect.Parameter.empty
        ):
            raise TypeError(
                f"CLI tool option '{param.name}' in {build_commands.__name__} "
                "must be keyword-only"
            )
    return frozenset(names)


@dataclass(frozen=True)
class CliToolRunnerRef(ToolRunnerRef):
    """Deprecated CLI-specific runner reference.

    New code should use ``api.application.ports.runners.ToolRunnerRef``.
    This subclass keeps the legacy default string form for old callers while
    remaining an instance of the application-level runner reference.
    """

    def __str__(self) -> str:
        return self.label or f"cli_tool:{self.tool_name}"


class GenericCliToolRunner:
    def __init__(
        self,
        spec: CliToolSpec,
        *,
        executable: str | None = None,
        timeout: int | float | None = None,
        logger: logging.Logger,
        executor_cls: type[CommandExecutor] = CommandExecutor,
        **static_options: Any,
    ):
        self.spec = spec
        self.executable = executable or spec.executable
        self.timeout = effective_timeout(spec.timeout, timeout)
        self.logger = logger
        self.executor_cls = executor_cls
        self.static_options = static_options
        self.accepted_option_names = spec.option_names | {"timeout"}

    async def run_raw(self, targets: Any, **options: Any) -> AsyncIterator[ProcessEvent]:
        async for event in self._run_plans(targets, **options):
            yield event

    async def run(self, targets: Any, **options: Any) -> AsyncIterator[ProcessEvent]:
        parser = self.spec.parser_factory()
        async for event in parser.parse_stream(self.run_raw(targets, **options)):
            yield event

    async def _run_plans(self, *args: Any, **options: Any) -> AsyncIterator[ProcessEvent]:
        run_options = dict(self.static_options)
        run_options.update(
            {
                key: value
                for key, value in options.items()
                if key in self.accepted_option_names
            }
        )
        timeout = effective_timeout(self.timeout, run_options.pop("timeout", None))
        for plan in self.spec.build_commands(self.executable, *args, **run_options):
            for event in plan.before_events:
                yield event
            label = plan.label or self.spec.name
            self.logger.info(
                "Starting %s command: %s stdin=%s",
                label,
                format_command_for_log(plan.command),
                summarize_stdin_for_log(plan.stdin),
            )
            try:
                async for event in run_cli_command(
                    plan.command,
                    stdin=plan.stdin,
                    timeout=timeout,
                    logger=self.logger,
                    stderr_label=label,
                    stderr_policy=self.spec.stderr_policy,
                    executor_cls=self.executor_cls,
                ):
                    yield event
            except asyncio.TimeoutError as exc:
                if plan.error_policy is ToolErrorPolicy.CONTINUE_ON_TIMEOUT:
                    self.logger.warning("%s timeout: %s", label, exc)
                    continue
                raise
            except CliCommandError as exc:
                if plan.error_policy is ToolErrorPolicy.LOG_AND_CONTINUE:
                    self.logger.warning("%s execution error: %s", label, exc)
                    continue
                raise
