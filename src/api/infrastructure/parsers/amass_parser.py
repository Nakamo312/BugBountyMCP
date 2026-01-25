import re
import logging
from typing import Dict, List, Set, Tuple, Optional

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
    def extract_domains_and_ips(cls, lines: List[str]) -> Dict[str, Set[str]]:
        """
        Extract domains and IP addresses from amass graph output.

        Args:
            lines: List of graph output lines

        Returns:
            Dict with 'domains' and 'ips' sets
        """
        domains = set()
        ips = set()

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

        logger.info(f"AmassParser: Extracted domains={len(domains)} ips={len(ips)}")

        return {
            "domains": domains,
            "ips": ips
        }
