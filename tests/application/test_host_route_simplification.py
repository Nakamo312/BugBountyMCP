from __future__ import annotations

from pathlib import Path


def test_host_routes_share_not_found_mapping() -> None:
    source = Path("src/api/presentation/rest/routes/host.py").read_text(encoding="utf-8")

    assert "def _require_found(" in source
    assert source.count("HTTP_404_NOT_FOUND") == 1
