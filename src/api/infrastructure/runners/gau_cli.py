"""GAU CLI runner for URL enumeration"""
import logging
from typing import AsyncIterator

from api.infrastructure.commands.command_executor import CommandExecutor
from api.infrastructure.parsers.line_process_event_parsers import GAUStdoutParser
from api.infrastructure.schemas.models.process_event import ProcessEvent

logger = logging.getLogger(__name__)


class GAUCliRunner:
    """
    Runner for GetAllURLs (gau) CLI tool.
    Executes gau and yields discovered URLs.
    """

    def __init__(self, gau_path: str, timeout: int = 600):
        self.gau_path = gau_path
        self.timeout = timeout

    async def run_raw(self, targets: list[str], include_subs: bool = True) -> AsyncIterator[ProcessEvent]:
        """
        Execute gau for the given domain and yield raw process events.

        Args:
            domain: Target domain for URL enumeration
            include_subs: Include subdomains in results

        Yields:
            Raw ProcessEvent objects from CommandExecutor
        """
        for domain in targets:
            command = [
                self.gau_path,
                "--providers", "wayback,commoncrawl,otx,urlscan",
                "--threads", "5",
                "--blacklist", "png,jpg,jpeg,gif,svg,ico,css,woff,woff2,ttf,eot,otf,mp4,mp3,avi,webm,flv,wav,pdf,zip,tar,gz,rar,7z,exe,dll,bin,dmg,iso",
            ]

            if include_subs:
                command.append("--subs")

            command.append(domain)

            logger.info("Starting GAU command: %s", " ".join(command))

            executor = CommandExecutor(command, stdin=None, timeout=self.timeout)

            async for event in executor.run():
                yield event

    async def run(self, targets: list[str], include_subs: bool = True) -> AsyncIterator[ProcessEvent]:
        """Compatibility wrapper for callers that still expect normalized URL results."""
        parser = GAUStdoutParser()
        async for event in parser.parse_stream(self.run_raw(targets, include_subs=include_subs)):
            yield event
