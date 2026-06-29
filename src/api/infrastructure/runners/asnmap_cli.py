"""asnmap CLI runner for ASN enumeration"""

import logging
from typing import AsyncIterator

from api.infrastructure.commands.command_boundary import command_invocation
from api.infrastructure.commands.command_executor import CommandExecutor
from api.infrastructure.parsers.process_event_parsers import JSONStdoutProcessEventParser
from api.infrastructure.schemas.models.process_event import ProcessEvent

logger = logging.getLogger(__name__)


class ASNMapCliRunner:
    """
    Runs asnmap CLI tool for ASN enumeration and CIDR discovery.

    Supports multiple input modes:
    - Domain: example.com в†’ ASN в†’ CIDR
    - ASN: AS12345 в†’ CIDR
    - Organization: "Company Name" в†’ ASN в†’ CIDR
    - IP: 8.8.8.8 в†’ ASN в†’ CIDR
    """

    def __init__(self, asnmap_path: str, timeout: int = 300):
        self.asnmap_path = asnmap_path
        self.timeout = timeout

    async def run(self, targets: list[str] | str) -> AsyncIterator[ProcessEvent]:
        """
        Auto-detect target type and run appropriate method.

        Args:
            targets: Single target or list of targets (domain, ASN, org, IP)

        Yields:
            ProcessEvent with type="result" and payload=asn_data
        """
        parser = JSONStdoutProcessEventParser()
        async for event in parser.parse_stream(self.run_raw(targets)):
            yield event

    async def run_raw(self, targets: list[str] | str) -> AsyncIterator[ProcessEvent]:
        """Auto-detect target type and yield raw process events."""
        if isinstance(targets, str):
            targets = [targets]

        for target in targets:
            if target.startswith("AS"):
                async for event in self.run_asn_raw(target):
                    yield event
            else:
                async for event in self.run_domain_raw(target):
                    yield event

    async def run_domain_raw(self, domains: list[str] | str) -> AsyncIterator[ProcessEvent]:
        """
        Enumerate ASN from domain names.

        Args:
            domains: Single domain or list of domains

        Yields:
            Raw ProcessEvent objects from CommandExecutor.

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
            "-duc",
        ]

        for domain in domains:
            command.extend(["-d", domain])

        logger.info("Starting asnmap domain enumeration: domains=%d", len(domains))

        executor = CommandExecutor(command_invocation(command, timeout=self.timeout))

        async for event in executor.run():
            if event.type == "stderr" and event.payload:
                logger.warning("asnmap stderr: %s", event.payload)
            yield event

        logger.info("asnmap domain enumeration completed")

    async def run_domain(self, domains: list[str] | str) -> AsyncIterator[ProcessEvent]:
        parser = JSONStdoutProcessEventParser()
        async for event in parser.parse_stream(self.run_domain_raw(domains)):
            yield event

    async def run_asn_raw(self, asns: list[str] | str) -> AsyncIterator[ProcessEvent]:
        """
        Get CIDR ranges for ASN numbers.

        Args:
            asns: Single ASN or list of ASNs (e.g., "AS15169", "AS12345")

        Yields:
            Raw ProcessEvent objects from CommandExecutor.
        """
        if isinstance(asns, str):
            asns = [asns]

        command = [
            self.asnmap_path,
            "-json",
            "-silent",
            "-duc",
        ]

        for asn in asns:
            command.extend(["-a", asn])

        logger.info("Starting asnmap ASN enumeration: asns=%d", len(asns))

        executor = CommandExecutor(command_invocation(command, timeout=self.timeout))

        async for event in executor.run():
            if event.type == "stderr" and event.payload:
                logger.warning("asnmap stderr: %s", event.payload)
            yield event

        logger.info("asnmap ASN enumeration completed")

    async def run_asn(self, asns: list[str] | str) -> AsyncIterator[ProcessEvent]:
        parser = JSONStdoutProcessEventParser()
        async for event in parser.parse_stream(self.run_asn_raw(asns)):
            yield event

    async def run_organization_raw(self, organizations: list[str] | str) -> AsyncIterator[ProcessEvent]:
        """
        Enumerate ASN from organization names.

        Args:
            organizations: Single org name or list of organization names

        Yields:
            Raw ProcessEvent objects from CommandExecutor.
        """
        if isinstance(organizations, str):
            organizations = [organizations]

        command = [
            self.asnmap_path,
            "-json",
            "-silent",
            "-duc",
        ]

        for org in organizations:
            command.extend(["-org", org])

        logger.info("Starting asnmap organization enumeration: orgs=%d", len(organizations))

        executor = CommandExecutor(command_invocation(command, timeout=self.timeout))

        async for event in executor.run():
            if event.type == "stderr" and event.payload:
                logger.warning("asnmap stderr: %s", event.payload)
            yield event

        logger.info("asnmap organization enumeration completed")

    async def run_organization(self, organizations: list[str] | str) -> AsyncIterator[ProcessEvent]:
        parser = JSONStdoutProcessEventParser()
        async for event in parser.parse_stream(self.run_organization_raw(organizations)):
            yield event
