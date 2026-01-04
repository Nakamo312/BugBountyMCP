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

    async def run_basic(self, targets: list[str] | str) -> AsyncIterator[ProcessEvent]:
        """
        Basic DNS enumeration (A, AAAA, CNAME) with wildcard filtering.
        Used after subdomain discovery, before HTTP probing.
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
            "-resp-only",
            "-wildcard-threshold", "5",
            "-t", str(thread_count),
        ]

        stdin = None
        if isinstance(targets, str):
            stdin = targets
        else:
            stdin = "\n".join(targets)

        logger.info("Starting DNSx Basic: targets=%d threads=%d", target_count, thread_count)

        executor = CommandExecutor(command, stdin=stdin, timeout=self.timeout)

        async for event in executor.run():
            if event.type != "stdout":
                continue

            if not event.payload:
                continue

            try:
                data = json.loads(event.payload)
            except json.JSONDecodeError:
                logger.debug("Non-JSON stdout line skipped: %r", event.payload)
                continue

            yield ProcessEvent(type="result", payload=data)

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

        async for event in executor.run():
            if event.type != "stdout":
                continue

            if not event.payload:
                continue

            try:
                data = json.loads(event.payload)
            except json.JSONDecodeError:
                logger.debug("Non-JSON stdout line skipped: %r", event.payload)
                continue

            yield ProcessEvent(type="result", payload=data)
