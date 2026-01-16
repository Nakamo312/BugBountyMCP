"""Katana CLI runner for web crawling"""
import logging
from typing import AsyncIterator

from api.infrastructure.commands.command_executor import CommandExecutor
from api.infrastructure.schemas.models.process_event import ProcessEvent

logger = logging.getLogger(__name__)


class KatanaCliRunner:
    """
    Runner for Katana CLI tool.
    Executes katana web crawler and yields discovered URLs.
    """

    def __init__(self, katana_path: str, timeout: int = 600):
        self.katana_path = katana_path
        self.timeout = timeout

    async def run(
        self,
        targets: list[str] | str,
        depth: int = 3,
    ) -> AsyncIterator[ProcessEvent]:
        """
        Execute katana crawler for the given targets.

        Args:
            targets: Single target URL or list of target URLs to crawl
            depth: Maximum crawl depth (default: 3)

        Yields:
            ProcessEvent with type="result" and payload=json_data
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
            "-hl",  # Headless mode
            "-aff",  # Automatic form filling
            "-xhr",  # Extract XHR requests
            "-jc",  # JavaScript crawling
            "-time-stable", "10",  # Wait time for page to be stable
            "-mfc", "100",  # Max form count
            "-nos",  # No screenshots
            "-c", "1",  # Concurrency
            "-p", "1",  # Parallelism
            "-j",  # JSON output format with request/response details
            "-tech-detect",
            "-known-files", "sitemapxml",
            "-f", "qurl",
            "-ef", "png,jpg,jpeg,gif,svg,ico,css,woff,woff2,ttf,eot,otf,mp4,mp3,avi,webm,flv,wav,pdf,zip,tar,gz,rar,7z,exe,dll,bin,dmg,iso",
        ]

        logger.info("Starting Katana command for %d targets: %s", len(targets), " ".join(command))

        executor = CommandExecutor(command, stdin=stdin_input, timeout=self.timeout)
        result_count = 0

        async for event in executor.run():
            if event.type != "stdout":
                continue

            if not event.payload:
                continue

            line = event.payload.strip()
            if not line:
                continue

            try:
                import json
                json_data = json.loads(line)
                result_count += 1
                yield ProcessEvent(type="result", payload=json_data)
            except json.JSONDecodeError:
                logger.warning("Non-JSON stdout line skipped: %r", line[:200])

