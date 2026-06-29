from __future__ import annotations

import hashlib
from uuid import UUID

from .proposal_row_codec import _required_text


def _proposal_key(source_outcome_id: UUID, capability_id: str, profile_id: str, feature_builder_version: str) -> str:
    return ":".join(
        (
            "action-experience-proposal",
            str(source_outcome_id),
            _required_text(capability_id, "capability_id"),
            _required_text(profile_id, "profile_id"),
            _required_text(feature_builder_version, "feature_builder_version"),
        )
    )


def _surface_component_proposal_key(
    source_outcome_id: UUID,
    snapshot_id: str,
    component_id: int,
    capability_id: str,
    profile_id: str,
    feature_builder_version: str,
) -> str:
    digest = hashlib.sha256(
        "|".join(
            (
                str(source_outcome_id),
                snapshot_id,
                str(component_id),
                _required_text(capability_id, "capability_id"),
                _required_text(profile_id, "profile_id"),
                _required_text(feature_builder_version, "feature_builder_version"),
            )
        ).encode("utf-8")
    ).hexdigest()[:24]
    return f"surface-component-action-proposal:{digest}"
