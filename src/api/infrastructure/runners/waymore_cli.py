"""Waymore CLI runner for archived URL discovery"""
import logging
from typing import AsyncIterator

from api.infrastructure.commands.command_executor import CommandExecutor
from api.infrastructure.schemas.models.process_event import ProcessEvent

logger = logging.getLogger(__name__)


class WaymoreCliRunner:
    """
    Runner for waymore CLI tool.
    Executes waymore to get URLs from multiple sources:
    - Wayback Machine
    - Common Crawl
    - Alien Vault OTX
    - URLScan
    - Virus Total
    """

    def __init__(self, waymore_path: str = "waymore", timeout: int = 1800):
        self.waymore_path = waymore_path
        self.timeout = timeout

    async def run(
        self,
        targets: list[str] | str,
    ) -> AsyncIterator[ProcessEvent]:
        """
        Execute waymore for given targets.

        Args:
            targets: Single domain or list of domains

        Yields:
            ProcessEvent with type="url" and payload=url_string
        """
        if isinstance(targets, str):
            targets = [targets]

        stdin_input = "\n".join(targets)

        command = [
            self.waymore_path,
            "-i", "-",
            "-mode", "U",
            "-oU", "-",
            "--stream",
            "-xcc",
            "-fc", "404,410,429,500,502,503",
            "-t", "30",
        ]

        logger.info(
            f"Starting Waymore command for {len(targets)} targets: {' '.join(command)}"
        )

        executor = CommandExecutor(
            command=command,
            stdin=stdin_input,
            timeout=self.timeout
        )

        async for event in executor.run():
            if event.type == "stdout" and event.payload:
                url = event.payload.strip()
                if url and url.startswith("http"):
                    yield ProcessEvent(type="result", payload=url)
