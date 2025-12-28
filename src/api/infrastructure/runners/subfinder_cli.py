"""Subfinder CLI runner for subdomain enumeration"""
import logging
from typing import AsyncIterator

from api.infrastructure.commands.command_executor import CommandExecutor
from api.infrastructure.schemas.models.process_event import ProcessEvent

logger = logging.getLogger(__name__)


class SubfinderCliRunner:
    """
    Runner for Subfinder CLI tool.
    Executes subfinder and yields discovered subdomains.
    """

    def __init__(self, subfinder_path: str, timeout: int = 600):
        self.subfinder_path = subfinder_path
        self.timeout = timeout

    async def run(self, domain: str) -> AsyncIterator[ProcessEvent]:
        """
        Execute subfinder for the given domain.

        Args:
            domain: Target domain for subdomain enumeration

        Yields:
            ProcessEvent with type="subdomain" and payload=discovered_subdomain
        """
        command = [
            self.subfinder_path,
            "-d", domain,
            "-silent",
            "-all"
        ]

        logger.info("Starting Subfinder command: %s", " ".join(command))

        executor = CommandExecutor(command, stdin=None, timeout=self.timeout)

        async for event in executor.run():
            if event.type != "stdout":
                continue

            if not event.payload:
                continue

            subdomain = event.payload.strip()
            if subdomain:
                yield ProcessEvent(type="subdomain", payload=subdomain)
