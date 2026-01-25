import logging
from typing import AsyncIterator, Optional

from api.infrastructure.commands.command_executor import CommandExecutor
from api.infrastructure.schemas.models.process_event import ProcessEvent

logger = logging.getLogger(__name__)


class AmassCliRunner:
    """
    CLI runner for OWASP Amass subdomain enumeration tool.
    Runs amass enum with configurable active mode and wordlist for brute forcing.
    """

    def __init__(
        self,
        amass_path: str = "amass",
        wordlist: Optional[str] = None,
        timeout: int = 1800,
    ):
        self.amass_path = amass_path
        self.wordlist = wordlist
        self.timeout = timeout

    async def run(self, domain: str, active: bool = False) -> AsyncIterator[ProcessEvent]:
        """
        Run Amass enumeration on target domain.

        Args:
            domain: Target domain (e.g., "example.com")
            active: Enable active enumeration (zone transfers, brute force)

        Yields:
            ProcessEvent with type="stdout" and payload=graph line
        """
        logger.info(f"Running Amass enum on domain: {domain} active={active}")

        command = [
            self.amass_path,
            "enum",
            "-d", domain,
        ]

        if active:
            command.append("-active")

            if self.wordlist:
                command.extend(["-brute", "-w", self.wordlist])
                logger.info(f"Using wordlist: {self.wordlist}")

        executor = CommandExecutor(command=command, timeout=self.timeout)

        result_count = 0
        async for event in executor.run():
            if event.type == "stderr" and event.payload:
                logger.debug(f"Amass stderr: {event.payload}")

            if event.type == "stdout" and event.payload:
                result_count += 1
                yield event

        logger.info(f"Amass enum completed: domain={domain} lines={result_count}")
