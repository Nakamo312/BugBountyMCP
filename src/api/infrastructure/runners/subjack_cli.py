"""Subjack CLI runner for subdomain takeover detection"""
import logging
import tempfile
from pathlib import Path
from typing import AsyncIterator, Optional

from api.infrastructure.commands.command_boundary import format_command_for_log, summarize_stdin_for_log
from api.infrastructure.commands.command_executor import CommandExecutor
from api.infrastructure.parsers.line_process_event_parsers import SubjackStdoutParser
from api.infrastructure.runners.cli_command import as_list, run_cli_command, stdin_lines
from api.infrastructure.schemas.models.process_event import ProcessEvent

logger = logging.getLogger(__name__)


class SubjackCliRunner:
    """Runner for Subjack CLI tool."""

    def __init__(self, subjack_path: str, fingerprints_path: Optional[str] = None, timeout: int = 300):
        self.subjack_path = subjack_path
        self.fingerprints_path = fingerprints_path
        self.timeout = timeout

    async def run_raw(self, targets: list[str] | str) -> AsyncIterator[ProcessEvent]:
        target_list = as_list(targets)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as tmp:
            tmp.write(stdin_lines(target_list))
            tmp.flush()
            wordlist_path = tmp.name

        try:
            logger.info("Subjack wordlist content: %s", summarize_stdin_for_log(stdin_lines(target_list)))
            command = [self.subjack_path, "-w", wordlist_path, "-t", "100", "-timeout", "30", "-ssl", "-a", "-m"]
            if self.fingerprints_path:
                command.extend(["-c", self.fingerprints_path])

            logger.info(
                "Starting Subjack: targets=%d wordlist=%s command=%s",
                len(target_list),
                wordlist_path,
                format_command_for_log(command),
            )
            async for event in run_cli_command(
                command,
                timeout=self.timeout,
                logger=logger,
                stderr_label="subjack",
                executor_cls=CommandExecutor,
            ):
                yield event
            logger.info("Subjack completed: targets=%d", len(target_list))
        finally:
            Path(wordlist_path).unlink(missing_ok=True)

    async def run(self, targets: list[str] | str) -> AsyncIterator[ProcessEvent]:
        parser = SubjackStdoutParser()
        async for event in parser.parse_stream(self.run_raw(targets)):
            yield event
