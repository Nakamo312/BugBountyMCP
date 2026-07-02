# api/infrastructure/commands/command_executor.py
import asyncio
import logging
import os
import signal
from collections.abc import Mapping, Sequence
from typing import AsyncIterator, Optional
import subprocess
from api.infrastructure.commands.command_boundary import (
    CommandInvocation,
    command_invocation,
    summarize_env_for_log,
)
from api.infrastructure.schemas.enums.process_state import ProcessState
from api.application.process_event_contracts import ProcessEvent

logger = logging.getLogger(__name__)

def _normalize_invocation(
    command: Sequence[str] | CommandInvocation,
    *,
    stdin: str | None,
    timeout: int | float,
    env: Mapping[str, str] | None,
) -> CommandInvocation:
    if isinstance(command, CommandInvocation):
        if stdin is not None:
            raise ValueError("stdin must be part of CommandInvocation, not a separate override")
        if timeout != 600:
            raise ValueError("timeout must be part of CommandInvocation, not a separate override")
        if env is not None:
            raise ValueError("env must be part of CommandInvocation, not a separate override")
        return command
    return command_invocation(command, stdin=stdin, timeout=timeout, env=env)


class CommandExecutor:
    """
    Execute CLI command and yield ProcessEvent objects,
    supporting full lifecycle control (state, timeout, cancellation).
    """

    def __init__(
        self,
        command: Sequence[str] | CommandInvocation,
        stdin: Optional[str] = None,
        timeout: int | float = 600,
        env: Mapping[str, str] | None = None,
    ):
        self.invocation = _normalize_invocation(command, stdin=stdin, timeout=timeout, env=env)
        self.command = list(self.invocation.argv)
        self.stdin = self.invocation.stdin
        self.timeout = self.invocation.timeout
        self.env = dict(self.invocation.env)
        self.state = ProcessState.CREATED
        self.process: Optional[asyncio.subprocess.Process] = None
        self.process_group_id: int | None = None

    async def run(self) -> AsyncIterator[ProcessEvent]:
        self.state = ProcessState.STARTING
        logger.info(
            "Starting process: %s env=%s",
            self.invocation.command_for_log,
            summarize_env_for_log(self.invocation.env),
        )

        process_env = self.invocation.process_env(os.environ) if self.invocation.env else None

        try:
            self.process = await asyncio.create_subprocess_exec(
                *self.command,
                stdin=asyncio.subprocess.PIPE if self.stdin else None,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                limit=1024 * 1024,
                start_new_session=True,
                env=process_env,
            )
            if self.process.pid:
                try:
                    self.process_group_id = os.getpgid(self.process.pid)
                except (ProcessLookupError, PermissionError, OSError):
                    self.process_group_id = None
        except Exception as exc:
            self.state = ProcessState.FAILED
            yield ProcessEvent(type="failed", payload=str(exc))
            return

        self.state = ProcessState.RUNNING
        yield ProcessEvent(type="started")

        # write stdin if provided
        if self.stdin and self.process.stdin:
            try:
                self.process.stdin.write(self.stdin.encode())
                await self.process.stdin.drain()
                self.process.stdin.write_eof()
            except Exception as exc:
                logger.warning("Failed to write stdin: %s", exc)

        try:
            async with asyncio.timeout(self.timeout):
                wait_task = asyncio.create_task(self.process.wait())

                try:
                    async for event in self._stream_output():
                        yield event

                    if self.process.returncode is not None:
                        return_code = self.process.returncode
                    elif not wait_task.done():
                        return_code = await wait_task
                    else:
                        return_code = wait_task.result()

                    await self._close_lingering_process_group()

                    self.state = ProcessState.TERMINATED
                    yield ProcessEvent(type="terminated", payload=str(return_code))

                    logger.info("Process finished with returncode=%s", return_code)
                finally:
                    if not wait_task.done():
                        wait_task.cancel()
                        try:
                            await wait_task
                        except asyncio.CancelledError:
                            pass

                    await self._cleanup_process_group()

        except TimeoutError:
            self.state = ProcessState.TIMEOUT
            yield ProcessEvent(type="timeout")
            await self._terminate()

        except asyncio.CancelledError:
            await self._terminate()
            raise

        except Exception as exc:
            self.state = ProcessState.FAILED
            yield ProcessEvent(type="failed", payload=str(exc))
            await self._terminate()

    async def _cleanup_process_group(self):
        """Reap terminated children without changing command outcome."""
        if self.process_group_id is None:
            return

        try:
            subprocess.run(
                ["pkill", "-SIGCHLD", "-g", str(self.process_group_id)],
                capture_output=True,
                timeout=1,
            )
        except (ProcessLookupError, PermissionError, OSError, subprocess.TimeoutExpired):
            pass

    async def _close_lingering_process_group(self) -> None:
        """Close descendants that keep stdout/stderr pipes open after the tool exits."""
        if self.process_group_id is None:
            return
        try:
            os.killpg(self.process_group_id, signal.SIGTERM)
        except (ProcessLookupError, PermissionError, OSError):
            return
        await asyncio.sleep(0)

    async def _terminate(self):
        if not self.process:
            return

        self.state = ProcessState.TERMINATING

        try:
            if self.process_group_id is not None:
                os.killpg(self.process_group_id, signal.SIGTERM)
            else:
                self.process.terminate()
        except (ProcessLookupError, PermissionError, OSError):
            if self.process.returncode is None:
                self.process.terminate()

        try:
            await asyncio.wait_for(self.process.wait(), timeout=5)
        except asyncio.TimeoutError:
            try:
                if self.process_group_id is not None:
                    os.killpg(self.process_group_id, signal.SIGKILL)
                else:
                    self.process.kill()
            except (ProcessLookupError, PermissionError, OSError):
                if self.process.returncode is None:
                    self.process.kill()
            await self.process.wait()

        await self._cleanup_process_group()

    async def _stream_output(self) -> AsyncIterator[ProcessEvent]:
        """Stream stdout and stderr without hanging on inherited pipes."""
        assert self.process is not None

        async def reader(stream, event_type):
            async for line in stream:
                text = line.decode(errors="ignore").strip()
                if not text:
                    continue
                yield ProcessEvent(type=event_type, payload=text)

        sentinel = object()
        stdout_iter = reader(self.process.stdout, "stdout")
        stderr_iter = reader(self.process.stderr, "stderr")

        async def safe_anext(it):
            try:
                return await it.__anext__()
            except StopAsyncIteration:
                return sentinel

        tasks = {
            "stdout": asyncio.create_task(safe_anext(stdout_iter)),
            "stderr": asyncio.create_task(safe_anext(stderr_iter)),
        }

        closed_lingering_group = False
        try:
            while tasks:
                done, _ = await asyncio.wait(
                    set(tasks.values()),
                    timeout=0.1,
                    return_when=asyncio.FIRST_COMPLETED,
                )

                if (
                    not closed_lingering_group
                    and self.process is not None
                    and self.process.returncode is not None
                ):
                    await self._close_lingering_process_group()
                    closed_lingering_group = True

                for finished in done:
                    for name, task in list(tasks.items()):
                        if task is finished:
                            result = task.result()
                            if result is sentinel:
                                tasks.pop(name)
                            else:
                                yield result
                                tasks[name] = asyncio.create_task(
                                    safe_anext(stdout_iter if name == "stdout" else stderr_iter)
                                )
                            break
        finally:
            for task in tasks.values():
                if not task.done():
                    task.cancel()
            if tasks:
                await asyncio.gather(*tasks.values(), return_exceptions=True)
