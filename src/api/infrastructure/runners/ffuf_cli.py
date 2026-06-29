import logging
from typing import AsyncIterator

from api.infrastructure.commands.command_boundary import command_invocation
from api.infrastructure.commands.command_executor import CommandExecutor
from api.infrastructure.parsers.line_process_event_parsers import FFUFStdoutParser
from api.infrastructure.schemas.models.process_event import ProcessEvent

logger = logging.getLogger(__name__)


class FFUFCliRunner:
    """
    CLI runner for FFUF (Fuzz Faster U Fool) directory/file fuzzing tool.
    Runs ffuf with recursion and JSON output for endpoint discovery.
    """

    def __init__(
        self,
        ffuf_path: str = "ffuf",
        wordlist: str = "/usr/share/seclists/Discovery/Web-Content/raft-medium-directories.txt",
        rate_limit: int = 10,
        timeout: int = 600,
    ):
        self.ffuf_path = ffuf_path
        self.wordlist = wordlist
        self.rate_limit = rate_limit
        self.timeout = timeout

    async def run_raw(
        self,
        target_url: str,
        timeout: int | float | None = None,
        rate: int | float | None = None,
        concurrency: int | None = None,
    ) -> AsyncIterator[ProcessEvent]:
        """
        Run FFUF fuzzing on target URL.

        Args:
            target_url: Base URL to fuzz (e.g., "https://example.com")

        Yields:
            ProcessEvent with type="result" and payload=ffuf JSON result
        """
        logger.info(f"Running FFUF on target: {target_url}")

        command = [
            self.ffuf_path,
            "-u", f"{target_url}/FUZZ",
            "-w", self.wordlist,
            "-recursion",
            "-json",
            "-p", "0.1-0.3",
            "-se",
            "-sf",
            "-ac",
            "-rate", _number_arg(self.rate_limit if rate is None else rate),
        ]
        if concurrency is not None:
            command.extend(["-t", str(concurrency)])

        executor = CommandExecutor(command_invocation(command, timeout=self.timeout if timeout is None else timeout))

        async for event in executor.run():
            yield event

    async def run(
        self,
        target_url: str,
        timeout: int | float | None = None,
        rate: int | float | None = None,
        concurrency: int | None = None,
    ) -> AsyncIterator[ProcessEvent]:
        parser = FFUFStdoutParser()
        async for event in parser.parse_stream(
            self.run_raw(
                target_url,
                timeout=timeout,
                rate=rate,
                concurrency=concurrency,
            )
        ):
            yield event


def _number_arg(value: int | float) -> str:
    number = float(value)
    return str(int(number)) if number.is_integer() else str(number)
