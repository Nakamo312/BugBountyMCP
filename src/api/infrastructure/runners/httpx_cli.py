from typing import AsyncIterator, List
from api.infrastructure.commands.command_executor import CommandExecutor
from api.infrastructure.schemas.models.process_event import ProcessEvent
import logging

logger = logging.getLogger(__name__)

class HTTPXCliRunner:
    def __init__(self, httpx_path: str, timeout: int = 600):
        self.httpx_path = httpx_path
        self.timeout = timeout

    async def run(self, targets: List[str] | str) -> AsyncIterator[ProcessEvent]:
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
            "-follow-redirects",
            "-filter-duplicates",
            "-s"
        ]

        stdin = None
        if isinstance(targets, str):
            command += ["-u", targets]
        else:
            stdin = "\n".join(targets)

        logger.info("Starting HTTPX command: %s, stdin=%s", " ".join(command), stdin)

        executor = CommandExecutor(command, stdin=stdin, timeout=self.timeout)

        async for event in executor.run():
            if hasattr(event, "payload"):
                logger.debug("HTTPX event payload: %s", event.payload)
            else:
                logger.debug("HTTPX event without payload: %s", event)
            yield event
