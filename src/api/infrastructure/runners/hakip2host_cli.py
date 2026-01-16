"""Hakip2host CLI Runner for reverse IP to hostname resolution"""

import json
import logging
from typing import AsyncIterator

from api.infrastructure.commands.command_executor import CommandExecutor, ProcessEvent

logger = logging.getLogger(__name__)


class Hakip2HostCliRunner:
    """
    Runs hakip2host CLI tool for reverse DNS and SSL certificate enumeration.

    Hakip2host features:
    - Reverse DNS (PTR records)
    - SSL/TLS certificate SAN/CN enumeration
    - IPv4 input via stdin
    - Line-delimited output: [METHOD] IP hostname

    Output format:
    [DNS-PTR] 91.194.226.30 example.com
    [SSL-SAN] 91.194.226.20 *.tinkoff.ru
    [SSL-CN] 91.194.226.20 *.tinkoff.ru
    """

    def __init__(self, hakip2host_path: str, timeout: int = 300):
        self.hakip2host_path = hakip2host_path
        self.timeout = timeout

    async def run(self, targets: list[str]) -> AsyncIterator[ProcessEvent]:
        """
        Resolve IPs to hostnames via PTR and SSL certificates.

        Args:
            targets: List of IPv4 addresses

        Yields:
            ProcessEvent with type="result" and payload={"ip": str, "hostname": str, "method": str}
        """
        command = [self.hakip2host_path]
        stdin = "\n".join(targets)

        logger.info(
            f"Starting hakip2host: ips={len(targets)} stdin={stdin[:100]}"
        )

        executor = CommandExecutor(command, stdin=stdin, timeout=self.timeout)

        result_count = 0
        async for event in executor.run():
            if event.type == "stderr" and event.payload:
                logger.warning(f"hakip2host stderr: {event.payload}")

            if event.type != "stdout" or not event.payload:
                continue

            line = event.payload.strip()
            if not line or not line.startswith("["):
                continue

            # Parse: [METHOD] IP hostname
            try:
                parts = line.split(maxsplit=2)
                if len(parts) != 3:
                    continue

                method = parts[0].strip("[]")
                ip = parts[1]
                hostname = parts[2]

                result_count += 1
                yield ProcessEvent(
                    type="result",
                    payload={
                        "ip": ip,
                        "hostname": hostname,
                        "method": method
                    }
                )
            except Exception as exc:
                logger.debug(f"Failed to parse hakip2host line: {line} - {exc}")
                continue

        logger.info(f"hakip2host completed: results={result_count}")
