from pathlib import Path


GENERIC_ROUTE_FILES = (
    Path("src/api/presentation/rest/routes/host.py"),
    Path("src/api/presentation/rest/routes/infrastructure.py"),
    Path("src/api/presentation/rest/routes/program.py"),
)


def test_read_only_routes_do_not_wrap_unknown_exceptions_locally() -> None:
    for path in GENERIC_ROUTE_FILES:
        source = path.read_text(encoding="utf-8")
        assert "except Exception" not in source, path
        assert "HTTP_500_INTERNAL_SERVER_ERROR" not in source, path
