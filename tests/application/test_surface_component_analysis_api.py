from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from api.application.surface_component_analysis import (
    SurfaceComponentAnalysisItem,
    SurfaceComponentAnalysisNotFound,
    SurfaceComponentHeuristicSignals,
    SurfaceComponentAnalysisReport,
    SurfaceComponentAnalysisService,
    surface_component_analysis_boundary,
)


class FakeStore:
    def __init__(self, report: SurfaceComponentAnalysisReport | None) -> None:
        self.report = report
        self.calls: list[dict[str, object]] = []

    async def latest(self, **kwargs):
        self.calls.append({"method": "latest", **kwargs})
        return self.report

    async def latest_for_program(self, **kwargs):
        self.calls.append({"method": "latest_for_program", **kwargs})
        return self.report


def _report() -> SurfaceComponentAnalysisReport:
    program_id = uuid4()
    snapshot_id = uuid4()
    return SurfaceComponentAnalysisReport(
        analysis_run_id=uuid4(),
        program_id=program_id,
        snapshot_id=snapshot_id,
        previous_snapshot_id=None,
        report_fingerprint="a" * 64,
        algorithm="surface-component-report",
        algorithm_version="surface-component-analysis-v1",
        stats={"component_count": 1},
        settings={"limit": 10},
        created_at=datetime(2026, 6, 27, 1, 0, tzinfo=timezone.utc),
        item_count=1,
        items=[
            SurfaceComponentAnalysisItem(
                component_id=7,
                node_count=5,
                changed_node_count=2,
                signals=SurfaceComponentHeuristicSignals(
                    structural_pressure=73,
                    drift=None,
                    bridge_pressure=66,
                    outlier=72,
                    coverage=55,
                    exploration_pressure=34,
                ),
                action_candidate_count=1,
                metrics={"profile": {"component_id": 7}},
                action_candidates=[{"capability_id": "katana", "profile_id": "safe-crawl"}],
            )
        ],
    )


def test_surface_component_analysis_item_exposes_signal_contract_not_score_fields() -> None:
    item = _report().items[0].model_dump()

    assert "signals" in item
    assert item["signals"]["calibration_status"] == "uncalibrated"
    assert item["signals"]["exploration_pressure"] == 34
    assert "exploration_priority_score" not in item
    assert "structural_pressure_score" not in item


@pytest.mark.asyncio
async def test_surface_component_analysis_service_returns_materialized_report() -> None:
    report = _report()
    store = FakeStore(report)
    service = SurfaceComponentAnalysisService(store)

    result = await service.latest(program_id=report.program_id, snapshot_id=report.snapshot_id)

    assert result.analysis_run_id == report.analysis_run_id
    assert result.items[0].signals.structural_pressure == 73
    assert store.calls == [
        {
            "method": "latest",
            "program_id": report.program_id,
            "snapshot_id": report.snapshot_id,
            "previous_snapshot_id": None,
        }
    ]


@pytest.mark.asyncio
async def test_surface_component_analysis_service_raises_not_found() -> None:
    service = SurfaceComponentAnalysisService(FakeStore(None))

    with pytest.raises(SurfaceComponentAnalysisNotFound):
        await service.latest(program_id=uuid4(), snapshot_id=uuid4())


@pytest.mark.asyncio
async def test_surface_component_analysis_service_returns_latest_for_program() -> None:
    report = _report()
    store = FakeStore(report)
    service = SurfaceComponentAnalysisService(store)

    result = await service.latest_for_program(program_id=report.program_id)

    assert result.analysis_run_id == report.analysis_run_id
    assert store.calls == [{"method": "latest_for_program", "program_id": report.program_id}]


def test_surface_component_analysis_boundary_is_read_only() -> None:
    boundary = surface_component_analysis_boundary()

    assert boundary["gds_execution"] == "not_available_from_api_read_endpoint"
    assert boundary["proposal_creation"] == "forbidden"
    assert boundary["action_submission"] == "forbidden"
    assert boundary["signal_contract"]["calibration_status"] == "uncalibrated"
    assert "priority" in boundary["signal_contract"]["not_semantics"]


def test_surface_component_analysis_route_is_registered() -> None:
    source = __import__("pathlib").Path("src/api/presentation/rest/routes/__init__.py").read_text(encoding="utf-8")

    assert "surface_component_analysis_router" in source
    assert "/api/v1/surface-component-analysis" in source


def test_surface_component_analysis_latest_route_exists() -> None:
    source = __import__("pathlib").Path("src/api/presentation/rest/routes/surface_component_analysis.py").read_text(encoding="utf-8")

    assert '"/latest"' in source
    assert "latest_for_program" in source
