from __future__ import annotations

from uuid import UUID


def surface_map_dedupe_key(program_id: UUID | str, snapshot_id: UUID | str, parser_version: str) -> str:
    return f"surface-map:{program_id}:{snapshot_id}:{parser_version}"


def surface_node_key(*, snapshot_id: str, node_fingerprint: str) -> str:
    return f"{snapshot_id}:{node_fingerprint}"


def surface_delta_key(*, snapshot_id: str, delta_type: str, subject_fingerprint: str) -> str:
    return f"{snapshot_id}:{delta_type}:{subject_fingerprint}"
