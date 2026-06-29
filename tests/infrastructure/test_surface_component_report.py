from __future__ import annotations

import sys
from pathlib import Path
from tests.infrastructure.graph_projector_cli_test_helpers import graph_projector_cli_source


def _symbols():
    sys.path.insert(0, str(Path("services/graph-projector").resolve()))
    from graph_projector.surface_component_report import SurfaceComponentReportReader
    from graph_projector.surface_gds import (
        SurfaceComponentActionCandidate,
        SurfaceComponentBridgeProfile,
        SurfaceComponentCoverageProfile,
        SurfaceComponentDrift,
        SurfaceComponentOutlierProfile,
        SurfaceComponentProfile,
    )

    return (
        SurfaceComponentReportReader,
        SurfaceComponentProfile,
        SurfaceComponentDrift,
        SurfaceComponentBridgeProfile,
        SurfaceComponentOutlierProfile,
        SurfaceComponentCoverageProfile,
        SurfaceComponentActionCandidate,
    )


class FakeSession:
    def __init__(self) -> None:
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.closed = True
        return False


class FakeDriver:
    def __init__(self) -> None:
        self.session_kwargs: list[dict[str, object]] = []
        self.session_obj = FakeSession()

    def session(self, **kwargs):
        self.session_kwargs.append(kwargs)
        return self.session_obj


class FakeSurfaceMathReader:
    def __init__(self, symbols) -> None:
        (
            _,
            Profile,
            Drift,
            Bridge,
            Outlier,
            Coverage,
            Candidate,
        ) = symbols
        self.calls: list[tuple[str, dict[str, object]]] = []
        self.Profile = Profile
        self.Drift = Drift
        self.Bridge = Bridge
        self.Outlier = Outlier
        self.Coverage = Coverage
        self.Candidate = Candidate

    def component_profiles(self, session, **kwargs):
        self.calls.append(("profiles", kwargs))
        return (self.Profile(1, 5, 2, 18.0, 80, 1.8, 4.0, 0.4, 73),)

    def component_drift(self, session, **kwargs):
        self.calls.append(("drift", kwargs))
        return (self.Drift(1, 3, 5, 4, 2, 3, 2, 0.33, 22.0, 70, 81),)

    def component_bridges(self, session, **kwargs):
        self.calls.append(("bridges", kwargs))
        return (self.Bridge(1, 5, 2, 1.2, 8.0, 1.8, 4.0, 0.4, 80, 66),)

    def component_outliers(self, session, **kwargs):
        self.calls.append(("outliers", kwargs))
        return (self.Outlier(1, 5, 2, 0.12, 0.25, 4, 0.4, 80, 72),)

    def component_coverage(self, session, **kwargs):
        self.calls.append(("coverage", kwargs))
        return (self.Coverage(1, 5, 2, 1, 1, 0, 6.0, 0.4, 80, 55, 34),)

    def component_action_candidates(self, session, **kwargs):
        self.calls.append(("candidates", kwargs))
        return (self.Candidate(1, 5, 2, 80, "katana", "safe-crawl", 4, 0.44, 5.0, 0.25, 0.0, 2.5, 70, 61),)


def test_surface_component_report_reader_collects_all_structural_views() -> None:
    symbols = _symbols()
    SurfaceComponentReportReader = symbols[0]
    driver = FakeDriver()
    math_reader = FakeSurfaceMathReader(symbols)

    report = SurfaceComponentReportReader(
        driver,
        neo4j_database="neo4j-test",
        surface_math_reader=math_reader,
    ).read(
        program_id="program-1",
        snapshot_id="snap-2",
        previous_snapshot_id="snap-1",
        limit=3,
        candidate_limit=2,
        component_limit=4,
        similarity_cutoff=0.07,
    )

    assert driver.session_kwargs == [{"database": "neo4j-test"}]
    assert [name for name, _ in math_reader.calls] == [
        "profiles",
        "bridges",
        "outliers",
        "coverage",
        "drift",
        "candidates",
    ]
    assert report.program_id == "program-1"
    assert report.snapshot_id == "snap-2"
    assert report.previous_snapshot_id == "snap-1"
    assert report.profiles[0].structural_pressure_score == 73
    assert report.drift[0].drift_score == 81
    assert report.action_candidates[0].capability_id == "katana"
    payload = report.to_dict()
    assert payload["component_count"] == 1
    assert payload["profiles"][0]["component_id"] == 1
    assert payload["action_candidates"][0]["candidate_score"] == 61


def test_surface_component_report_can_skip_drift_and_action_candidates() -> None:
    symbols = _symbols()
    SurfaceComponentReportReader = symbols[0]
    math_reader = FakeSurfaceMathReader(symbols)

    report = SurfaceComponentReportReader(
        FakeDriver(),
        surface_math_reader=math_reader,
    ).read(
        program_id="program-1",
        snapshot_id="snap-2",
        include_action_candidates=False,
    )

    assert "drift" not in [name for name, _ in math_reader.calls]
    assert "candidates" not in [name for name, _ in math_reader.calls]
    assert report.drift == ()
    assert report.action_candidates == ()


def test_surface_component_report_rejects_invalid_inputs() -> None:
    symbols = _symbols()
    SurfaceComponentReportReader = symbols[0]
    reader = SurfaceComponentReportReader(FakeDriver(), surface_math_reader=FakeSurfaceMathReader(symbols))

    for kwargs, expected in [
        ({"program_id": "", "snapshot_id": "snap"}, "program_id must not be empty"),
        ({"program_id": "program", "snapshot_id": ""}, "snapshot_id must not be empty"),
        ({"program_id": "program", "snapshot_id": "snap", "limit": 0}, "limit must be positive"),
        ({"program_id": "program", "snapshot_id": "snap", "similarity_cutoff": 1.5}, "similarity_cutoff"),
    ]:
        try:
            reader.read(**kwargs)
        except ValueError as exc:
            assert expected in str(exc)
        else:  # pragma: no cover
            raise AssertionError("expected invalid input to fail")


def test_graph_projector_cli_exposes_surface_components_command() -> None:
    source = graph_projector_cli_source()

    assert 'subparsers.add_parser(\n        "surface-components"' in source
    assert "SurfaceComponentReportReader" in source
    assert "--snapshot-id" in source
    assert "surface_component_action_candidate" in source
