from __future__ import annotations

from pathlib import Path

ROOT = Path(".")
POSTGRES_READER = ROOT / "src/api/infrastructure/artifacts/postgres_reader.py"
ASSET_READER = ROOT / "src/api/infrastructure/artifacts/asset_reader.py"
HTTP_READER = ROOT / "src/api/infrastructure/artifacts/http_reader.py"
ENDPOINT_READER = ROOT / "src/api/infrastructure/artifacts/endpoint_reader.py"
SECURITY_READER = ROOT / "src/api/infrastructure/artifacts/security_reader.py"
COMMON = ROOT / "src/api/infrastructure/artifacts/common.py"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_postgres_artifact_reader_is_composition_root_not_query_archive() -> None:
    source = _read(POSTGRES_READER)

    assert "AssetArtifactReader" in source
    assert "HttpObservationArtifactReader" in source
    assert "EndpointArtifactReader" in source
    assert "SecurityArtifactReader" in source
    assert "ArtifactQueryExecutor" in source
    assert "from api.infrastructure.adapters.orm" not in source
    assert "select(" not in source
    assert "join(" not in source


def test_artifact_query_responsibilities_have_separate_modules() -> None:
    assert "async def list_hosts" in _read(ASSET_READER)
    assert "async def list_services" in _read(ASSET_READER)
    assert "async def list_dns_records" in _read(ASSET_READER)

    assert "async def list_headers" in _read(HTTP_READER)
    assert "async def list_bodies" in _read(HTTP_READER)
    assert "latest_observation_has_body" in _read(HTTP_READER)

    assert "async def list_endpoints" in _read(ENDPOINT_READER)
    assert "async def get_endpoint_detail" in _read(ENDPOINT_READER)
    assert "async def list_parameters" in _read(ENDPOINT_READER)

    assert "async def list_findings" in _read(SECURITY_READER)
    assert "async def list_leaks" in _read(SECURITY_READER)
    assert "async def list_events" in _read(SECURITY_READER)
    assert "async def list_artifact_previews" in _read(SECURITY_READER)


def test_shared_artifact_helpers_are_not_hidden_on_facade() -> None:
    common = _read(COMMON)
    facade = _read(POSTGRES_READER)

    assert "class ArtifactQueryExecutor" in common
    assert "def scope_endpoint_child_query" in common
    assert "def sanitize_header_row" in common
    assert "def sanitize_body_row" in common
    assert "def sanitize_leak_row" in common
    assert "_scope_endpoint_child_query = staticmethod(scope_endpoint_child_query)" in facade
