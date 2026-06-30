import logging
from typing import AsyncIterator

from api.infrastructure.commands.command_boundary import command_invocation
from api.infrastructure.commands.command_executor import CommandExecutor
from api.infrastructure.parsers.process_event_parsers import JSONStdoutProcessEventParser
from api.application.process_event_contracts import ProcessEvent

logger = logging.getLogger(__name__)


class DNSxCliRunner:
    def __init__(self, dnsx_path: str, timeout: int = 600):
        self.dnsx_path = dnsx_path
        self.timeout = timeout

    async def run_deep_raw(self, targets: list[str] | str) -> AsyncIterator[ProcessEvent]:
        """
        Deep DNS enumeration (A, AAAA, CNAME, MX, TXT, NS, SOA).
        Used after HTTP probing for live hosts analysis.
        """
        target_count = 1 if isinstance(targets, str) else len(targets)
        thread_count = min(target_count, 100)

        command = [
            self.dnsx_path,
            "-json",
            "-silent",
            "-a",
            "-aaaa",
            "-cname",
            "-mx",
            "-txt",
            "-ns",
            "-soa",
            "-resp-only",
            "-t", str(thread_count),
        ]

        stdin = None
        if isinstance(targets, str):
            stdin = targets
        else:
            stdin = "\n".join(targets)

        logger.info("Starting DNSx Deep: targets=%d threads=%d", target_count, thread_count)

        executor = CommandExecutor(command_invocation(command, stdin=stdin, timeout=self.timeout))

        async for event in executor.run():
            if event.type == "stderr" and event.payload:
                logger.warning("DNSx Deep stderr: %s", event.payload)
            yield event

        logger.info("DNSx Deep completed")

    async def run_deep(self, targets: list[str] | str) -> AsyncIterator[ProcessEvent]:
        parser = JSONStdoutProcessEventParser()
        async for event in parser.parse_stream(self.run_deep_raw(targets)):
            yield event

    async def run_ptr_raw(self, ips: list[str] | str) -> AsyncIterator[ProcessEvent]:
        """
        Reverse DNS lookup (PTR records).
        Used for CIDR blocks IP enumeration to discover hostnames.

        Args:
            ips: Single IP or list of IP addresses

        Yields:
            ProcessEvent with type="result" and payload=dns_data
        """
        ip_count = 1 if isinstance(ips, str) else len(ips)
        thread_count = min(ip_count, 100)

        command = [
            self.dnsx_path,
            "-json",
            "-silent",
            "-ptr",
            "-resp-only",
            "-t", str(thread_count),
        ]

        stdin = None
        if isinstance(ips, str):
            stdin = ips
        else:
            stdin = "\n".join(ips)

        logger.info("Starting DNSx PTR: ips=%d threads=%d", ip_count, thread_count)

        executor = CommandExecutor(command_invocation(command, stdin=stdin, timeout=self.timeout))

        async for event in executor.run():
            if event.type == "stderr" and event.payload:
                logger.warning("DNSx PTR stderr: %s", event.payload)
            yield event

        logger.info("DNSx PTR completed")

    async def run_ptr(self, ips: list[str] | str) -> AsyncIterator[ProcessEvent]:
        parser = JSONStdoutProcessEventParser()
        async for event in parser.parse_stream(self.run_ptr_raw(ips)):
            yield event
