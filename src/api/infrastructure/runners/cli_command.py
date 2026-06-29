from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Callable, Iterable, Sequence
from enum import Enum
from typing import Any

from api.infrastructure.commands.command_boundary import command_invocation
from api.infrastructure.commands.command_executor import CommandExecutor
from api.infrastructure.schemas.models.process_event import ProcessEvent


class CliCommandError(RuntimeError):
    """Base error raised by generic CLI command helpers."""


class CliStderrError(CliCommandError):
    """Raised when stderr_policy=FAIL receives stderr payload."""


class StderrPolicy(str, Enum):
    DEBUG = "debug"
    WARNING = "warning"
    IGNORE = "ignore"
    AS_EVENT = "as_event"
    FAIL = "fail"


def as_list(values: str | Iterable[str]) -> list[str]:
    return [values] if isinstance(values, str) else list(values)


def stdin_lines(values: Iterable[str]) -> str:
    return "\n".join(values)


def effective_timeout(default_timeout: int | float, timeout: int | float | None = None) -> int | float:
    return default_timeout if timeout is None else timeout


async def run_cli_command(
    command: Sequence[str],
    *,
    stdin: str | None = None,
    timeout: int | float,
    logger: logging.Logger,
    stderr_label: str,
    executor_cls: type[CommandExecutor] = CommandExecutor,
    stderr_policy: StderrPolicy = StderrPolicy.WARNING,
) -> AsyncIterator[ProcessEvent]:
    invocation = command_invocation(command, stdin=stdin, timeout=timeout)
    executor = executor_cls(invocation)

    async for event in executor.run():
        if event.type == "stderr" and event.payload:
            if stderr_policy is StderrPolicy.DEBUG:
                logger.debug("%s stderr: %s", stderr_label, event.payload)
            elif stderr_policy is StderrPolicy.WARNING:
                logger.warning("%s stderr: %s", stderr_label, event.payload)
            elif stderr_policy is StderrPolicy.IGNORE:
                continue
            elif stderr_policy is StderrPolicy.AS_EVENT:
                pass
            elif stderr_policy is StderrPolicy.FAIL:
                raise CliStderrError(f"{stderr_label} stderr: {event.payload}")
        yield event


async def run_cli_stdout_results(
    command: Sequence[str],
    *,
    stdin: str | None = None,
    timeout: int | float,
    logger: logging.Logger,
    stderr_label: str,
    transform: Callable[[str], Any] | None = None,
    executor_cls: type[CommandExecutor] = CommandExecutor,
    stderr_policy: StderrPolicy = StderrPolicy.WARNING,
) -> AsyncIterator[ProcessEvent]:
    async for event in run_cli_command(
        command,
        stdin=stdin,
        timeout=timeout,
        logger=logger,
        stderr_label=stderr_label,
        executor_cls=executor_cls,
        stderr_policy=stderr_policy,
    ):
        if event.type != "stdout" or not event.payload:
            continue
        payload = event.payload.strip()
        if not payload:
            continue
        yield ProcessEvent(type="result", payload=transform(payload) if transform else payload)
