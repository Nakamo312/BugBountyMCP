"""IngestResult dataclass for returning new entities from ingestors"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass
class IngestResult:
    """
    Result of ingestion containing only NEW entities discovered.
    Ingestors filter duplicates by checking DB before returning.
    """

    new_hosts: List[str] = field(default_factory=list)
    js_files: List[str] = field(default_factory=list)
    asns: List[str] = field(default_factory=list)
    cidrs: List[str] = field(default_factory=list)
    urls: List[str] = field(default_factory=list)
    ips: List[str] = field(default_factory=list)
    hostnames: List[str] = field(default_factory=list)
    raw_domains: List[str] = field(default_factory=list)

    def merge(self, other: "IngestResult") -> "IngestResult":
        """Return a new result containing values from both results."""
        return IngestResult(
            new_hosts=[*self.new_hosts, *other.new_hosts],
            js_files=[*self.js_files, *other.js_files],
            asns=[*self.asns, *other.asns],
            cidrs=[*self.cidrs, *other.cidrs],
            urls=[*self.urls, *other.urls],
            ips=[*self.ips, *other.ips],
            hostnames=[*self.hostnames, *other.hostnames],
            raw_domains=[*self.raw_domains, *other.raw_domains],
        )
