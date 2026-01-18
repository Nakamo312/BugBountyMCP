"""Playwright CLI runner for interactive web crawling"""
import logging
from typing import AsyncIterator
from pathlib import Path

from api.infrastructure.commands.command_executor import CommandExecutor
from api.infrastructure.schemas.models.process_event import ProcessEvent

logger = logging.getLogger(__name__)


class PlaywrightCliRunner:
    """
    Runner for Playwright scanner.
    Executes interactive web crawler and yields discovered requests.
    """

    def __init__(self, timeout: int = 600):
        self.timeout = timeout
        self.scanner_script = Path(__file__).parent / "playwright_scanner.py"

    async def run(
        self,
        targets: list[str] | str,
        depth: int = 2,
    ) -> AsyncIterator[ProcessEvent]:
        """
        Execute playwright scanner for given targets.

        Args:
            targets: Single target URL or list of target URLs to crawl
            depth: Maximum crawl depth (default: 2)

        Yields:
            ProcessEvent with type="result" and payload=json_data
        """
        if isinstance(targets, str):
            targets = [targets]

        # Process one target at a time
        for target in targets:
            command = [
                "python",
                str(self.scanner_script),
                target,
                str(depth),
            ]

            logger.info(f"Starting Playwright scanner for {target}: {' '.join(command)}")

            executor = CommandExecutor(command=command, timeout=self.timeout)
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

            logger.info(f"Playwright scanner completed for {target}: {result_count} requests")
