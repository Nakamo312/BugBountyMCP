"""Subjack CLI runner for subdomain takeover detection"""
import logging
import tempfile
from pathlib import Path
from typing import AsyncIterator, Optional

from api.infrastructure.commands.command_executor import CommandExecutor
from api.infrastructure.parsers.line_process_event_parsers import SubjackStdoutParser
from api.infrastructure.schemas.models.process_event import ProcessEvent

logger = logging.getLogger(__name__)


class SubjackCliRunner:
    """
    Runner for Subjack CLI tool.
    Detects subdomain takeovers by analyzing CNAME records.
    """

    def __init__(self, subjack_path: str, fingerprints_path: Optional[str] = None, timeout: int = 300):
        self.subjack_path = subjack_path
        self.fingerprints_path = fingerprints_path
        self.timeout = timeout

    async def run_raw(self, targets: list[str] | str) -> AsyncIterator[ProcessEvent]:
        """
        Execute subjack and yield raw process events.

        Args:
            targets: Single domain or list of domains to check

        Yields:
            Raw ProcessEvent objects from CommandExecutor
        """
        if isinstance(targets, str):
            targets = [targets]

        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as tmp:
            tmp.write('\n'.join(targets))
            tmp.flush()
            wordlist_path = tmp.name

        try:
            logger.info("Subjack wordlist content: %s", '\n'.join(targets))

            command = [
                self.subjack_path,
                "-w", wordlist_path,
                "-t", "100",
                "-timeout", "30",
                "-ssl",
                "-a",
                "-m",
            ]

            if self.fingerprints_path:
                command.extend(["-c", self.fingerprints_path])

            logger.info("Starting Subjack: targets=%d wordlist=%s command=%s", len(targets), wordlist_path, ' '.join(command))

            executor = CommandExecutor(command, timeout=self.timeout)

            async for event in executor.run():
                if event.type == "stderr" and event.payload:
                    logger.warning("Subjack stderr: %s", event.payload)
                yield event

            logger.info("Subjack completed: targets=%d", len(targets))
        finally:
            Path(wordlist_path).unlink(missing_ok=True)

    async def run(self, targets: list[str] | str) -> AsyncIterator[ProcessEvent]:
        """Compatibility wrapper for callers that still expect takeover results."""
        parser = SubjackStdoutParser()
        async for event in parser.parse_stream(self.run_raw(targets)):
            yield event
