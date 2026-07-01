from uuid import uuid4

import pytest

from api.application.read_only_views import ReadOnlyView, ReadOnlyViewPage
from api.application.services.analysis import AnalysisService


@pytest.mark.parametrize("bad_name", ["", "HostStats", "host-stats", "host_stats;drop"])
def test_read_only_view_rejects_invalid_view_names(bad_name: str) -> None:
    with pytest.raises(ValueError):
        ReadOnlyView(bad_name, frozenset({"program_id"}))


def test_read_only_view_rejects_filters_outside_view_contract() -> None:
    view = ReadOnlyView("host_full_stats", frozenset({"program_id"}))

    with pytest.raises(ValueError):
        view.validate_filters({"program_id": uuid4(), "in_scope": True})


class _FakeViewReader:
    def __init__(self, *, row=None):
        self.calls = []
        self.row = row

    async def list_view_rows(self, view, filters, *, limit: int, offset: int):
        self.calls.append(("list", view, dict(filters), limit, offset))
        return [self.row or {"program_id": filters["program_id"], "candidate": "xss"}]

    async def page_view_rows(self, view, filters, *, limit: int, offset: int):
        self.calls.append(("page", view, dict(filters), limit, offset))
        return ReadOnlyViewPage(
            rows=[self.row or {"program_id": filters["program_id"], "candidate": "xss"}],
            total=1,
        )


@pytest.mark.asyncio
async def test_analysis_service_queries_views_through_read_model_port() -> None:
    reader = _FakeViewReader()
    service = AnalysisService(reader)
    program_id = uuid4()

    rows, total = await service._query_view(
        ReadOnlyView("injection_candidates_view", frozenset({"program_id"})),
        program_id,
        limit=50,
        offset=10,
    )

    assert total == 1
    assert rows == [{"program_id": program_id, "candidate": "xss"}]
    assert reader.calls == [
        (
            "page",
            ReadOnlyView("injection_candidates_view", frozenset({"program_id"})),
            {"program_id": program_id},
            50,
            10,
        )
    ]


@pytest.mark.asyncio
async def test_analysis_service_reads_registered_analysis_kind() -> None:
    program_id = uuid4()
    reader = _FakeViewReader(
        row={
            "program_id": program_id,
            "host": "example.com",
            "full_url": "https://example.com/search?q=x",
            "path": "/search",
        }
    )
    service = AnalysisService(reader)

    result = await service.get_analysis(
        "injection_candidates",
        program_id=program_id,
        limit=50,
        offset=10,
    )

    assert result.total == 1
    assert result.limit == 50
    assert result.offset == 10
    assert result.items[0].program_id == program_id
    assert reader.calls[0][1].name == "injection_candidates_view"


@pytest.mark.asyncio
async def test_analysis_service_rejects_unknown_analysis_kind() -> None:
    service = AnalysisService(_FakeViewReader())

    with pytest.raises(ValueError, match="Unknown analysis kind"):
        await service.get_analysis("unknown", program_id=uuid4())
