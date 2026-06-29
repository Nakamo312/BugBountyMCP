import logging
from typing import AsyncIterator, List
from urllib.parse import urlparse

from api.infrastructure.commands.command_boundary import command_invocation
from api.infrastructure.commands.command_executor import CommandExecutor
from api.infrastructure.parsers.line_process_event_parsers import LinkFinderStdoutParser
from api.infrastructure.schemas.models.process_event import ProcessEvent

logger = logging.getLogger(__name__)

class LinkFinderCliRunner:
    def __init__(self, linkfinder_path: str = "linkfinder", timeout: int = 15):
        self.linkfinder_path = linkfinder_path
        self.timeout = timeout

    async def run_raw(self, js_urls: List[str]) -> AsyncIterator[ProcessEvent]:
        for target in js_urls:
            logger.info("Running LinkFinder on: %s", target)

            parsed = urlparse(target)
            host = parsed.hostname or parsed.netloc

            if not host:
                logger.warning("Could not extract host from %s, skipping", target)
                continue
            yield ProcessEvent(type="target", payload={"target": target, "host": host})

            is_domain_scan = not parsed.path or parsed.path == "/" or "*" in target

            command = [
                self.linkfinder_path,
                "-i", target,
            ]

            if is_domain_scan:
                command.append("-d")

            command.extend(["-o", "cli"])

            executor = CommandExecutor(command_invocation(command, timeout=self.timeout))

            try:
                async for event in executor.run():
                    yield event

            except Exception as e:
                logger.warning("LinkFinder timeout/error for %s: %s", target, str(e))
                continue

    async def run(self, js_urls: List[str]) -> AsyncIterator[ProcessEvent]:
        parser = LinkFinderStdoutParser()
        async for event in parser.parse_stream(self.run_raw(js_urls)):
            yield event
