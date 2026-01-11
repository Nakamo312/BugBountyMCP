"""Utility functions for extracting data from events"""
from typing import Dict, Any, List


def default_target_extractor(event: Dict[str, Any]) -> List[str]:
    """
    Extract targets from various event types.

    Supports multiple field names for flexibility:
    - subdomains (from Subfinder)
    - urls (from GAU)
    - hosts (from DNSx, HTTPX)
    - ips (from MapCIDR, ASNMap)
    - targets (generic)

    Args:
        event: Event payload

    Returns:
        List of targets (URLs, hosts, IPs, etc.)
    """
    return (
        event.get("subdomains") or
        event.get("urls") or
        event.get("hosts") or
        event.get("ips") or
        event.get("targets") or
        []
    )
