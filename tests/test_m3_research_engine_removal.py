from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def test_standalone_research_engine_service_is_removed() -> None:
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))

    assert "research-engine" not in compose["services"]
    assert "bb-research-engine" not in (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert not (ROOT / "services/research-engine").exists()


def test_surface_map_adr_no_longer_reuses_standalone_research_engine() -> None:
    source = (ROOT / "docs/adr/surface-map-v1.md").read_text(encoding="utf-8")

    assert "existing `research-engine` package" not in source
    assert "services/research-engine" not in source
