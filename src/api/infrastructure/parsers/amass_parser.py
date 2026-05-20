import re
import logging
from collections.abc import AsyncIterator
from typing import Dict, List, Set, Tuple, Optional

from api.infrastructure.schemas.models.process_event import ProcessEvent

logger = logging.getLogger(__name__)


class AmassGraphParser:
    """
    Parses Amass graph output to extract domains and IP addresses.

    Amass output format:
    source_entity (type) --> relationship --> target_entity (type)

    Example:
    tinkoff.ru (FQDN) --> a_record --> 178.130.128.27 (IPAddress)
    tinkoff.ru (FQDN) --> node --> www.tinkoff.ru (FQDN)
    """

    GRAPH_PATTERN = re.compile(
        r'^(.+?)\s+\((\w+)\)\s+-->\s+(\w+)\s+-->\s+(.+?)\s+\((\w+)\)$'
    )

    async def parse_stream(self, stream: AsyncIterator[ProcessEvent]) -> AsyncIterator[ProcessEvent]:
        """Normalize raw Amass graph stdout lines into fact records."""
        async for event in stream:
            if event.type != "stdout" or not event.payload:
                continue
            record = self.parse_record(event.payload)
            if record is not None:
                yield ProcessEvent(type="result", payload=record)

    @classmethod
    def parse_line(cls, line: str) -> Optional[Tuple[str, str, str, str, str]]:
        """
        Parse single graph line.

        Args:
            line: Graph line from amass output

        Returns:
            Tuple of (source_entity, source_type, relationship, target_entity, target_type)
            or None if line doesn't match
        """
        match = cls.GRAPH_PATTERN.match(line.strip())
        if not match:
            return None

        return (
            match.group(1).strip(),
            match.group(2).strip(),
            match.group(3).strip(),
            match.group(4).strip(),
            match.group(5).strip(),
        )

    @classmethod
    def parse_record(cls, line: str) -> dict[str, list[str]] | None:
        """Extract normalized facts from one Amass graph line."""
        parsed = cls.parse_line(line)
        if not parsed:
            return None

        source_entity, source_type, relationship, target_entity, target_type = parsed
        domains: set[str] = set()
        ips: set[str] = set()
        cidrs: set[str] = set()
        asns: set[str] = set()

        if source_type == "FQDN":
            domains.add(source_entity)

        if target_type == "FQDN" and relationship in ("node", "cname_record", "mx_record"):
            domains.add(target_entity)

        if target_type == "IPAddress" and relationship in ("a_record", "aaaa_record"):
            ips.add(target_entity)

        if source_type == "Netblock":
            cidrs.add(source_entity)

        if target_type == "Netblock":
            cidrs.add(target_entity)

        if source_type == "ASN":
            try:
                asn_num = int(source_entity)
            except ValueError:
                asn_num = 0
            if asn_num > 0:
                asns.add(str(asn_num))

        if not (domains or ips or cidrs or asns):
            return None

        return {
            "domains": sorted(domains),
            "ips": sorted(ips),
            "cidrs": sorted(cidrs),
            "asns": sorted(asns),
        }

    @classmethod
    def extract_domains_and_ips(cls, lines: List[str]) -> Dict[str, Set[str]]:
        """
        Extract domains, IPs, CIDRs, and ASNs from amass graph output.

        Args:
            lines: List of graph output lines

        Returns:
            Dict with 'domains', 'ips', 'cidrs', 'asns' sets
        """
        domains = set()
        ips = set()
        cidrs = set()
        asns = set()

        for line in lines:
            parsed = cls.parse_line(line)
            if not parsed:
                continue

            source_entity, source_type, relationship, target_entity, target_type = parsed

            if source_type == "FQDN":
                domains.add(source_entity)

            if target_type == "FQDN":
                if relationship in ("node", "cname_record", "mx_record"):
                    domains.add(target_entity)

            if target_type == "IPAddress":
                if relationship in ("a_record", "aaaa_record"):
                    ips.add(target_entity)

            if source_type == "Netblock":
                cidrs.add(source_entity)

            if target_type == "Netblock":
                cidrs.add(target_entity)

            if source_type == "ASN":
                try:
                    asn_num = int(source_entity)
                    if asn_num > 0:
                        asns.add(asn_num)
                except ValueError:
                    pass

        logger.info(
            f"AmassParser: Extracted domains={len(domains)} ips={len(ips)} "
            f"cidrs={len(cidrs)} asns={len(asns)}"
        )

        return {
            "domains": domains,
            "ips": ips,
            "cidrs": cidrs,
            "asns": asns
        }
