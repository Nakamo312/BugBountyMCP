from pathlib import Path


ANALYSIS_ROUTES = Path("src/api/presentation/rest/routes/analysis.py")


def test_analysis_routes_are_registered_from_endpoint_table() -> None:
    source = ANALYSIS_ROUTES.read_text(encoding="utf-8")

    assert "_ANALYSIS_ENDPOINTS" in source
    assert "router.add_api_route" in source
    assert "query_key" in source
    assert "get_analysis(" in source
    assert "getattr(" not in source
    assert source.count("@router.get(") == 0


def test_analysis_routes_do_not_duplicate_generic_exception_wrappers() -> None:
    source = ANALYSIS_ROUTES.read_text(encoding="utf-8")

    assert "except Exception" not in source
