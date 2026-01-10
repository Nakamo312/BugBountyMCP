"""asnmap CLI runner for ASN enumeration"""

import json
import logging
from typing import AsyncIterator

from api.infrastructure.commands.command_executor import CommandExecutor
from api.infrastructure.schemas.models.process_event import ProcessEvent

logger = logging.getLogger(__name__)


class ASNMapCliRunner:
    """
    Runs asnmap CLI tool for ASN enumeration and CIDR discovery.

    Supports multiple input modes:
    - Domain: example.com → ASN → CIDR
    - ASN: AS12345 → CIDR
    - Organization: "Company Name" → ASN → CIDR
    - IP: 8.8.8.8 → ASN → CIDR
    """

    def __init__(self, asnmap_path: str, timeout: int = 300):
        self.asnmap_path = asnmap_path
        self.timeout = timeout

    async def run_domain(self, domains: list[str] | str) -> AsyncIterator[ProcessEvent]:
        """
        Enumerate ASN from domain names.

        Args:
            domains: Single domain or list of domains

        Yields:
            ProcessEvent with type="result" and payload=asn_data

        Output format:
        {
            "timestamp": "2026-01-09 13:50:57...",
            "input": "example.com",
            "as_number": "AS15169",
            "as_name": "GOOGLE",
            "as_country": "US",
            "as_range": ["8.8.8.0/24", "8.8.4.0/24"]
        }
        """
        if isinstance(domains, str):
            domains = [domains]

        command = [
            self.asnmap_path,
            "-json",
            "-silent",
        ]

        for domain in domains:
            command.extend(["-d", domain])

        logger.info("Starting asnmap domain enumeration: domains=%d", len(domains))

        executor = CommandExecutor(command, timeout=self.timeout)

        result_count = 0
        async for event in executor.run():
            logger.info("asnmap event: type=%s payload=%r", event.type, event.payload)

            if event.type == "stderr" and event.payload:
                logger.warning("asnmap stderr: %s", event.payload)

            if event.type != "stdout":
                continue

            if not event.payload:
                continue

            try:
                data = json.loads(event.payload)
                result_count += 1
                yield ProcessEvent(type="result", payload=data)
            except json.JSONDecodeError:
                logger.debug("Non-JSON stdout line skipped: %r", event.payload)
                continue

        logger.info("asnmap domain enumeration completed: results=%d", result_count)

    async def run_asn(self, asns: list[str] | str) -> AsyncIterator[ProcessEvent]:
        """
        Get CIDR ranges for ASN numbers.

        Args:
            asns: Single ASN or list of ASNs (e.g., "AS15169", "AS12345")

        Yields:
            ProcessEvent with type="result" and payload=asn_data
        """
        if isinstance(asns, str):
            asns = [asns]

        command = [
            self.asnmap_path,
            "-json",
            "-silent",
        ]

        for asn in asns:
            command.extend(["-a", asn])

        logger.info("Starting asnmap ASN enumeration: asns=%d", len(asns))

        executor = CommandExecutor(command, timeout=self.timeout)

        result_count = 0
        async for event in executor.run():
            logger.info("asnmap event: type=%s payload=%r", event.type, event.payload)

            if event.type == "stderr" and event.payload:
                logger.warning("asnmap stderr: %s", event.payload)

            if event.type != "stdout":
                continue

            if not event.payload:
                continue

            try:
                data = json.loads(event.payload)
                result_count += 1
                yield ProcessEvent(type="result", payload=data)
            except json.JSONDecodeError:
                logger.debug("Non-JSON stdout line skipped: %r", event.payload)
                continue

        logger.info("asnmap ASN enumeration completed: results=%d", result_count)

    async def run_organization(self, organizations: list[str] | str) -> AsyncIterator[ProcessEvent]:
        """
        Enumerate ASN from organization names.

        Args:
            organizations: Single org name or list of organization names

        Yields:
            ProcessEvent with type="result" and payload=asn_data
        """
        if isinstance(organizations, str):
            organizations = [organizations]

        command = [
            self.asnmap_path,
            "-json",
            "-silent",
        ]

        for org in organizations:
            command.extend(["-org", org])

        logger.info("Starting asnmap organization enumeration: orgs=%d", len(organizations))

        executor = CommandExecutor(command, timeout=self.timeout)

        result_count = 0
        async for event in executor.run():
            logger.info("asnmap event: type=%s payload=%r", event.type, event.payload)

            if event.type == "stderr" and event.payload:
                logger.warning("asnmap stderr: %s", event.payload)

            if event.type != "stdout":
                continue

            if not event.payload:
                continue

            try:
                data = json.loads(event.payload)
                result_count += 1
                yield ProcessEvent(type="result", payload=data)
            except json.JSONDecodeError:
                logger.debug("Non-JSON stdout line skipped: %r", event.payload)
                continue

        logger.info("asnmap organization enumeration completed: results=%d", result_count)
