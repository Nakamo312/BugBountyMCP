"""State crawler data models."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Set
from urllib.parse import parse_qs, urlparse


@dataclass
class Action:
    selector: str
    text: str
    tag: str
    event_type: str = "click"
    semantic: str = "unknown"

    def _identity_key(self) -> tuple[str, str, str, str]:
        return (self.semantic, self.tag, self.text[:20].lower(), self.selector.split(">")[-1])

    def __hash__(self):
        return hash(self._identity_key())

    def __eq__(self, other):
        return isinstance(other, Action) and self._identity_key() == other._identity_key()

    def get_cluster_key(self) -> str:
        """Get key for clustering similar actions."""
        text_words = "".join(c for c in self.text.lower() if c.isalnum() or c.isspace()).split()
        text_sig = "_".join(text_words[:3])
        return f"{self.semantic}:{self.tag}:{text_sig}"


@dataclass
class State:
    url: str
    dom_hash: str
    dom_vector: Dict[str, int]
    cookies_hash: str
    storage_hash: str
    depth: int
    path: List[Action] = field(default_factory=list)
    actions: Set[Action] = field(default_factory=set)
    executed_actions: Set[Action] = field(default_factory=set)
    dead_actions: Set[Action] = field(default_factory=set)
    executed_clusters: Set[str] = field(default_factory=set)
    discovered_endpoints: Set[str] = field(default_factory=set)
    is_volatile: bool = False

    def __hash__(self):
        parsed = urlparse(self.url)
        normalized_url = f"{parsed.netloc}{parsed.path}"
        query_keys = frozenset(parse_qs(parsed.query).keys()) if parsed.query else frozenset()
        return hash((normalized_url, query_keys, self.cookies_hash))

    def get_fingerprint(self):
        parsed = urlparse(self.url)
        normalized_url = f"{parsed.netloc}{parsed.path}"
        query_keys = frozenset(parse_qs(parsed.query).keys()) if parsed.query else frozenset()
        return (normalized_url, query_keys, self.cookies_hash, self.storage_hash)

    def is_exhausted(self, no_new_endpoints: bool, no_new_clusters: bool) -> bool:
        """Check if state exploration is exhausted."""
        all_executed = len(self.executed_actions) >= len(self.actions)
        return all_executed or (no_new_endpoints and no_new_clusters)
