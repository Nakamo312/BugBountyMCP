from __future__ import annotations

import sys
from pathlib import Path


PROJECTOR_ROOT = Path("services/graph-projector").resolve()
SIGNAL_MODULE = PROJECTOR_ROOT / "graph_projector" / "surface_gds_signals.py"
LEGACY_SCORE_MODULE = PROJECTOR_ROOT / "graph_projector" / "surface_gds_scores.py"
SURFACE_COMPONENTS_PAGE = Path("BugBountyDashBoard/src/pages/SurfaceComponents.jsx")


def test_surface_gds_score_module_stays_removed() -> None:
    assert not LEGACY_SCORE_MODULE.exists()


def test_surface_gds_calculations_are_named_as_uncalibrated_signals() -> None:
    source = SIGNAL_MODULE.read_text()

    assert "SURFACE_GDS_SIGNAL_FORMULA_VERSION" in source
    assert "def _component_action_candidate_signal" in source
    assert "def _exploration_pressure_signal" in source
    assert "def _component_action_candidate_score" not in source
    assert "score_name" not in source
    assert "signal_name" in source
    assert "calibrated priority" in source


def test_surface_gds_candidate_features_expose_signal_semantics() -> None:
    sys.path.insert(0, str(PROJECTOR_ROOT))
    from graph_projector.surface_gds_signals import _component_action_candidate_signal_features

    features = _component_action_candidate_signal_features(
        component_attention_score=80,
        sample_count=10,
        avg_similarity=0.5,
        utility_score=5.0,
        human_stop_rate=0.0,
    )

    assert features["calibration_status"] == "uncalibrated"
    assert features["persisted_field"] == "candidate_score"
    assert features["signal_name"] == "candidate_rank_signal"
    assert "uncalibrated heuristic ranking signal" in features["signal_semantics"]


def test_surface_component_dashboard_does_not_label_heuristics_as_priority() -> None:
    source = SURFACE_COMPONENTS_PAGE.read_text()

    assert "priority {item.exploration_priority_score" not in source
    assert "uncalibrated heuristic graph signals" in source
    assert "not priority, risk, severity, or learned utility" in source
    assert "item.exploration_priority_score" not in source


def test_surface_component_read_api_hides_legacy_score_columns() -> None:
    source = Path("src/api/application/surface_component_analysis.py").read_text(encoding="utf-8")

    assert "class SurfaceComponentHeuristicSignals" in source
    assert "exploration_pressure" in source
    assert "structural_pressure_score" not in source
    assert "exploration_priority_score" not in source
