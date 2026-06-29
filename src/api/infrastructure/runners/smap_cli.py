"""Smap CLI Runner for fast port scanning"""

import logging
from typing import AsyncIterator

from api.infrastructure.commands.command_boundary import command_invocation
from api.infrastructure.commands.command_executor import CommandExecutor, ProcessEvent
from api.infrastructure.parsers.process_event_parsers import JSONStdoutItemsProcessEventParser

logger = logging.getLogger(__name__)


class SmapCliRunner:
    """
    Runs smap CLI tool for fast port scanning.

    Smap features:
    - Fast TCP/UDP scanning
    - CIDR support via stdin
    - JSON output (-oJ)
    - Banner grabbing
    - Service detection
    """

    def __init__(self, smap_path: str, timeout: int = 600):
        self.smap_path = smap_path
        self.timeout = timeout

    async def run_raw(self, targets: list[str]) -> AsyncIterator[ProcessEvent]:
        """
        Scan CIDR ranges with smap.

        Args:
            targets: List of CIDRs to scan

        Yields:
            Raw ProcessEvent objects from CommandExecutor.

        Output format:
        {
            "ip": "217.12.106.105",
            "hostnames": ["suoext.alfabank.ru"],
            "ports": [
                {"port": 443, "service": "https?", "protocol": "tcp"}
            ],
            "start_time": "2026-01-16T02:34:41.519350018Z",
            "end_time": "2026-01-16T02:34:42.143294138Z"
        }
        """
        command = [
            self.smap_path,
            "-iL", "-",
            "-oJ", "-"
        ]

        stdin = "\n".join(targets)

        logger.info(
            f"Starting smap scan: cidrs={len(targets)} stdin={stdin[:100]}"
        )

        executor = CommandExecutor(command_invocation(command, stdin=stdin, timeout=self.timeout))

        async for event in executor.run():
            if event.type == "stderr" and event.payload:
                logger.warning(f"smap stderr: {event.payload}")
            yield event

        logger.info("smap scan completed")

    async def run(self, targets: list[str]) -> AsyncIterator[ProcessEvent]:
        parser = JSONStdoutItemsProcessEventParser()
        async for event in parser.parse_stream(self.run_raw(targets)):
            yield event
