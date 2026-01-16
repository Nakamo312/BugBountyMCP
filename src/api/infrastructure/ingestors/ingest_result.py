"""IngestResult dataclass for returning new entities from ingestors"""
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
