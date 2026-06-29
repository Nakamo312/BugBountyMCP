from __future__ import annotations

from uuid import UUID


def raw_artifact_dedupe_key(artifact_id: UUID | str, parser_version: str) -> str:
    return f"raw-artifact-metadata:{artifact_id}:{parser_version}"
