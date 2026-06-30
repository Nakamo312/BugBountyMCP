import logging
from typing import AsyncIterator, Optional

from api.infrastructure.commands.command_boundary import command_invocation
from api.infrastructure.commands.command_executor import CommandExecutor
from api.infrastructure.parsers.amass_parser import AmassGraphParser
from api.application.process_event_contracts import ProcessEvent

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

    async def run_raw(self, domain: str, active: bool = False) -> AsyncIterator[ProcessEvent]:
        """
        Run Amass enumeration on target domain and yield raw process events.

        Args:
            domain: Target domain (e.g., "example.com")
            active: Enable active enumeration (zone transfers, brute force)

        Yields:
            Raw ProcessEvent objects from CommandExecutor
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

        invocation = command_invocation(command, timeout=self.timeout)
        executor = CommandExecutor(invocation)

        result_count = 0
        async for event in executor.run():
            if event.type == "stderr" and event.payload:
                logger.debug(f"Amass stderr: {event.payload}")

            if event.type == "stdout" and event.payload:
                result_count += 1
            yield event

        logger.info(f"Amass enum completed: domain={domain} lines={result_count}")

    async def run(self, domain: str, active: bool = False) -> AsyncIterator[ProcessEvent]:
        """Compatibility wrapper for callers that still expect normalized facts."""
        parser = AmassGraphParser()
        async for event in parser.parse_stream(self.run_raw(domain, active=active)):
            yield event
