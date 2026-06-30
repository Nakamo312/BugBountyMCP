"""Katana CLI runner for web crawling"""
import logging
from typing import AsyncIterator

from api.infrastructure.commands.command_boundary import command_invocation
from api.infrastructure.commands.command_executor import CommandExecutor
from api.infrastructure.parsers.process_event_parsers import JSONStdoutProcessEventParser
from api.application.process_event_contracts import ProcessEvent

logger = logging.getLogger(__name__)


class KatanaCliRunner:
    """
    Runner for Katana CLI tool.
    Executes katana web crawler and yields discovered URLs.
    """

    def __init__(self, katana_path: str, timeout: int = 600):
        self.katana_path = katana_path
        self.timeout = timeout

    async def run_raw(
        self,
        targets: list[str] | str,
        depth: int = 3,
        js_crawl: bool = True,
        headless: bool = True,
        timeout: int | float | None = None,
        concurrency: int = 1,
    ) -> AsyncIterator[ProcessEvent]:
        """
        Execute katana crawler for the given targets.

        Args:
            targets: Single target URL or list of target URLs to crawl
            depth: Maximum crawl depth (default: 3)

        Yields:
            Raw ProcessEvent objects from CommandExecutor.
        """
        if isinstance(targets, str):
            targets = [targets]

        stdin_input = "\n".join(targets)

        command = [
            self.katana_path,
            "-list", "-",
            "-d", str(depth),
            "-silent",
            "-jsonl",
            "-aff",  # Automatic form filling
            "-xhr",  # Extract XHR requests
            "-time-stable", "10",  # Wait time for page to be stable
            "-mfc", "100",  # Max form count
            "-nos",  # No screenshots
            "-c", str(concurrency),  # Concurrency
            "-p", str(concurrency),  # Parallelism
            "-j",  # JSON output format with request/response details
            "-tech-detect",
            "-known-files", "sitemapxml",
            "-f", "qurl",
            "-ef", "png,jpg,jpeg,gif,svg,ico,css,woff,woff2,ttf,eot,otf,mp4,mp3,avi,webm,flv,wav,pdf,zip,tar,gz,rar,7z,exe,dll,bin,dmg,iso",
        ]
        if headless:
            command.append("-hl")
        if js_crawl:
            command.append("-jc")

        logger.info("Starting Katana command for %d targets: %s", len(targets), " ".join(command))

        executor = CommandExecutor(command_invocation(command, stdin=stdin_input, timeout=self.timeout if timeout is None else timeout))

        async for event in executor.run():
            yield event

    async def run(
        self,
        targets: list[str] | str,
        depth: int = 3,
        js_crawl: bool = True,
        headless: bool = True,
        timeout: int | float | None = None,
        concurrency: int = 1,
    ) -> AsyncIterator[ProcessEvent]:
        parser = JSONStdoutProcessEventParser()
        async for event in parser.parse_stream(
            self.run_raw(
                targets,
                depth=depth,
                js_crawl=js_crawl,
                headless=headless,
                timeout=timeout,
                concurrency=concurrency,
            )
        ):
            yield event
