import logging
from typing import AsyncIterator

from api.infrastructure.commands.command_executor import CommandExecutor
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

    async def run(self, target_url: str) -> AsyncIterator[ProcessEvent]:
        """
        Run FFUF fuzzing on target URL.

        Args:
            target_url: Base URL to fuzz (e.g., "https://example.com")

        Yields:
            ProcessEvent objects with stdout/stderr/state
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
            "-rate", str(self.rate_limit),
            "-timeout", "1",
        ]

        executor = CommandExecutor(command=command, timeout=self.timeout)

        async for event in executor.run():
            yield event
