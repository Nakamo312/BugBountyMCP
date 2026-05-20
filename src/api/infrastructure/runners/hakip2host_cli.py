"""Hakip2host CLI Runner for reverse IP to hostname resolution"""

import logging
from typing import AsyncIterator

from api.infrastructure.commands.command_executor import CommandExecutor, ProcessEvent
from api.infrastructure.parsers.line_process_event_parsers import Hakip2HostStdoutParser

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

    async def run_raw(self, targets: list[str]) -> AsyncIterator[ProcessEvent]:
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

        async for event in executor.run():
            if event.type == "stderr" and event.payload:
                logger.warning(f"hakip2host stderr: {event.payload}")
            yield event

        logger.info("hakip2host completed")

    async def run(self, targets: list[str]) -> AsyncIterator[ProcessEvent]:
        parser = Hakip2HostStdoutParser()
        async for event in parser.parse_stream(self.run_raw(targets)):
            yield event
