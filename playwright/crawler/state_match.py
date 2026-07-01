"""State matching helpers for Playwright crawler replay decisions."""
from __future__ import annotations

from typing import Iterable
from urllib.parse import urlparse

from crawler.dom import dom_similarity
from crawler.models import Action, State


def normalized_location(url: str) -> str:
    """Return the URL part used by the crawler state fingerprint."""
    parsed = urlparse(url)
    return f"{parsed.netloc}{parsed.path}"


def action_cluster_keys(actions: Iterable[Action]) -> set[str]:
    """Return semantic action cluster keys for state validation."""
    return {action.get_cluster_key() for action in actions}


def state_observation_mismatch(
    target_state: State,
    *,
    current_url: str,
    current_dom_vector: dict[str, int],
    current_actions: Iterable[Action],
    min_dom_similarity: float = 0.85,
) -> str | None:
    """Return a mismatch reason, or None when the current page matches target_state.

    URL equality alone is not enough for stateful apps: two states can share the
    same route while cookies, storage, DOM, or available actions differ.
    """
    current_normalized = normalized_location(current_url)
    expected_normalized = target_state.get_fingerprint()[0]
    if current_normalized != expected_normalized:
        return f"URL {current_normalized} != {expected_normalized}"

    similarity = dom_similarity(target_state.dom_vector, current_dom_vector)
    if similarity < min_dom_similarity:
        return f"DOM similarity {similarity:.2f}"

    current_clusters = action_cluster_keys(current_actions)
    expected_clusters = action_cluster_keys(target_state.actions)
    if expected_clusters and not (current_clusters & expected_clusters):
        return "no shared action clusters"

    return None


def state_observation_matches(
    target_state: State,
    *,
    current_url: str,
    current_dom_vector: dict[str, int],
    current_actions: Iterable[Action],
    min_dom_similarity: float = 0.85,
) -> bool:
    """Return True when the current page still represents target_state."""
    return state_observation_mismatch(
        target_state,
        current_url=current_url,
        current_dom_vector=current_dom_vector,
        current_actions=current_actions,
        min_dom_similarity=min_dom_similarity,
    ) is None
