from __future__ import annotations

from dataclasses import dataclass

from .query_templates import GraphQueryTemplateRegistry, default_query_template_registry


REQUIRED_GDS_PREREQUISITE_TEMPLATES = (
    "asset_exposure",
    "endpoint_neighborhood",
    "evidence_path",
    "exposed_services_by_technology",
    "hidden_endpoints_from_js",
    "hypothesis_evidence_paths",
    "action_outcome_experience_neighborhood",
    "surface_graph_math",
)


@dataclass(frozen=True)
class GdsReadinessReport:
    ready: bool
    rebuild_supported: bool
    missing_query_templates: tuple[str, ...]
    reasons: tuple[str, ...]


def evaluate_gds_readiness(
    *,
    query_templates: GraphQueryTemplateRegistry | None = None,
    rebuild_supported: bool,
) -> GdsReadinessReport:
    registry = query_templates or default_query_template_registry()
    missing = tuple(name for name in REQUIRED_GDS_PREREQUISITE_TEMPLATES if name not in registry.names)
    reasons: list[str] = []
    if not rebuild_supported:
        reasons.append("graph rebuild command is not available")
    for name in missing:
        reasons.append(f"safe graph query template is missing: {name}")
    return GdsReadinessReport(
        ready=not reasons,
        rebuild_supported=rebuild_supported,
        missing_query_templates=missing,
        reasons=tuple(reasons),
    )
