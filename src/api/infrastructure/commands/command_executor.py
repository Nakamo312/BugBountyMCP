# api/infrastructure/commands/command_executor.py
import asyncio
import logging
from typing import AsyncIterator, List, Optional

from api.infrastructure.schemas.enums.process_state import ProcessState
from api.infrastructure.schemas.models.process_event import ProcessEvent

logger = logging.getLogger(__name__)


class CommandExecutor:
    """
    Execute CLI command and yield ProcessEvent objects,
    supporting full lifecycle control (state, timeout, cancellation).
    """

    def __init__(
        self,
        command: List[str],
        stdin: Optional[str] = None,
        timeout: int = 600,
    ):
        self.command = command
        self.stdin = stdin
        self.timeout = timeout
        self.state = ProcessState.CREATED
        self.process: Optional[asyncio.subprocess.Process] = None

    async def run(self) -> AsyncIterator[ProcessEvent]:
        self.state = ProcessState.STARTING
        logger.info("Starting process: %s", " ".join(self.command))

        try:
            self.process = await asyncio.create_subprocess_exec(
                *self.command,
                stdin=asyncio.subprocess.PIPE if self.stdin else None,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                limit=1024 * 1024,
            )
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
                        if wait_task.done():
                            break

                    if not wait_task.done():
                        return_code = await wait_task
                    else:
                        return_code = wait_task.result()

                    self.state = ProcessState.TERMINATED
                    yield ProcessEvent(type="terminated")

                    logger.info("Process finished with returncode=%s", return_code)
                finally:
                    if not wait_task.done():
                        wait_task.cancel()
                        try:
                            await wait_task
                        except asyncio.CancelledError:
                            pass

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

    async def _terminate(self):
        if not self.process or self.process.returncode is not None:
            return

        self.state = ProcessState.TERMINATING
        self.process.terminate()
        try:
            await asyncio.wait_for(self.process.wait(), timeout=5)
        except asyncio.TimeoutError:
            self.process.kill()
            await self.process.wait()

    async def _stream_output(self) -> AsyncIterator[ProcessEvent]:
        """Stream stdout and stderr simultaneously."""
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

        while tasks:
            done, _ = await asyncio.wait(
                tasks.values(), return_when=asyncio.FIRST_COMPLETED
            )

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
