from typing import AsyncIterator, List
from api.infrastructure.commands.command_boundary import command_invocation
from api.infrastructure.commands.command_executor import CommandExecutor
from api.infrastructure.schemas.models.process_event import ProcessEvent
from api.infrastructure.parsers.httpx_parser import HTTPXProcessEventParser
import logging

logger = logging.getLogger(__name__)

class HTTPXCliRunner:
    def __init__(self, httpx_path: str, timeout: int = 600):
        self.httpx_path = httpx_path
        self.timeout = timeout

    async def run_raw(
        self,
        targets: List[str] | str,
        timeout: int | float | None = None,
        concurrency: int | None = None,
    ) -> AsyncIterator[ProcessEvent]:
        target_count = 1 if isinstance(targets, str) else len(targets)
        thread_count = min(target_count, 20, concurrency or 20)

        command = [
            self.httpx_path,
            "-json",
            "-silent",
            "-status-code",
            "-tech-detect",
            "-title",
            "-ip",
            "-cdn",
            "-asn",
            "-favicon",
            "-method",
            "-cname",
            "-websocket",
            "-extract-fqdn",
            "-follow-redirects",
            "-filter-duplicates",
            "-t", str(thread_count),
            "-s"
        ]

        stdin = None
        if isinstance(targets, str):
            command += ["-u", targets]
        else:
            stdin = "\n".join(targets)

        logger.info("Starting HTTPX command: %s, stdin=%s", " ".join(command), stdin)

        executor = CommandExecutor(command_invocation(command, stdin=stdin, timeout=self.timeout if timeout is None else timeout))

        async for event in executor.run():
            yield event

    async def run(
        self,
        targets: List[str] | str,
        timeout: int | float | None = None,
        concurrency: int | None = None,
    ) -> AsyncIterator[ProcessEvent]:
        parser = HTTPXProcessEventParser()
        async for event in parser.parse_stream(
            self.run_raw(
                targets,
                timeout=timeout,
                concurrency=concurrency,
            )
        ):
            yield event
