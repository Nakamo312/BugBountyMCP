import json
import logging
from typing import AsyncIterator

from api.infrastructure.commands.command_executor import CommandExecutor
from api.infrastructure.schemas.models.process_event import ProcessEvent

logger = logging.getLogger(__name__)


class DNSxCliRunner:
    def __init__(self, dnsx_path: str, timeout: int = 600):
        self.dnsx_path = dnsx_path
        self.timeout = timeout

    async def run_deep(self, targets: list[str] | str) -> AsyncIterator[ProcessEvent]:
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

        executor = CommandExecutor(command, stdin=stdin, timeout=self.timeout)

        result_count = 0
        async for event in executor.run():
            if event.type == "stderr" and event.payload:
                logger.warning("DNSx Deep stderr: %s", event.payload)

            if event.type != "stdout":
                continue

            if not event.payload:
                continue

            try:
                data = json.loads(event.payload)
                result_count += 1
            except json.JSONDecodeError:
                logger.debug("Non-JSON stdout line skipped: %r", event.payload)
                continue

            yield ProcessEvent(type="result", payload=data)

        logger.info("DNSx Deep completed: results=%d", result_count)

    async def run_ptr(self, ips: list[str] | str) -> AsyncIterator[ProcessEvent]:
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

        executor = CommandExecutor(command, stdin=stdin, timeout=self.timeout)

        result_count = 0
        async for event in executor.run():
            if event.type == "stderr" and event.payload:
                logger.warning("DNSx PTR stderr: %s", event.payload)

            if event.type != "stdout":
                continue

            if not event.payload:
                continue

            try:
                data = json.loads(event.payload)
                result_count += 1
            except json.JSONDecodeError:
                logger.debug("Non-JSON stdout line skipped: %r", event.payload)
                continue

            yield ProcessEvent(type="result", payload=data)

        logger.info("DNSx PTR completed: results=%d", result_count)
