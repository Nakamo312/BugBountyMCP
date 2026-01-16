"""Smap CLI Runner for fast port scanning"""

import json
import logging
from typing import AsyncIterator

from api.infrastructure.commands.command_executor import CommandExecutor, ProcessEvent

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

    async def run(self, targets: list[str]) -> AsyncIterator[ProcessEvent]:
        """
        Scan CIDR ranges with smap.

        Args:
            targets: List of CIDRs to scan

        Yields:
            ProcessEvent with type="result" and payload=dict with smap JSON output

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
            "-oJ -"
        ]

        stdin = "\n".join(targets)

        logger.info(
            f"Starting smap scan: cidrs={len(targets)} stdin={stdin[:100]}"
        )

        executor = CommandExecutor(command, stdin=stdin, timeout=self.timeout)

        result_count = 0
        async for event in executor.run():
            if event.type == "stderr" and event.payload:
                logger.warning(f"smap stderr: {event.payload}")

            if event.type != "stdout" or not event.payload:
                continue

            try:
                data = json.loads(event.payload)
                result_count += 1
                yield ProcessEvent(type="result", payload=data)
            except json.JSONDecodeError:
                logger.debug(f"Non-JSON stdout line skipped: {event.payload}")
                continue

        logger.info(f"smap scan completed: results={result_count}")
