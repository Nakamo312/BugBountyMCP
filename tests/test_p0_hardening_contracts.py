from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def _compose(path: str) -> dict:
    return yaml.safe_load((ROOT / path).read_text(encoding="utf-8"))


def _port_strings(compose: dict) -> list[str]:
    ports: list[str] = []
    for service in compose["services"].values():
        for port in service.get("ports", []) or []:
            if isinstance(port, str):
                ports.append(port)
            elif isinstance(port, dict):
                ports.append(str(port.get("published", "")))
    return ports


def test_all_compose_ports_bind_to_loopback() -> None:
    for filename in ("docker-compose.yml", "docker-compose.integration.yml"):
        ports = _port_strings(_compose(filename))

        assert ports, f"{filename} should expose explicit local ports"
        assert all(port.startswith("127.0.0.1:") for port in ports), (filename, ports)


def test_monitoring_services_are_not_enabled_by_default() -> None:
    compose = _compose("docker-compose.yml")
    services = compose["services"]

    for name in ("prometheus", "cadvisor", "node-exporter", "grafana"):
        assert services[name]["profiles"] == ["monitoring"]


def test_config_does_not_contain_real_pdcp_api_key() -> None:
    source = (ROOT / "src/api/config.py").read_text(encoding="utf-8")

    assert 'PDCP_API_KEY: str = ""' in source
    assert not re.search(
        r"PDCP_API_KEY:\s*str\s*=\s*['\"][0-9a-f]{8}-[0-9a-f-]{27,}['\"]",
        source,
        re.IGNORECASE,
    )


def test_opensearch_default_http_projection_excludes_body_preview() -> None:
    sys.path.insert(0, str((ROOT / "services/search-indexer").resolve()))
    from search_indexer.documents import build_http_observation_document
    from search_indexer.postgres_reader import HTTP_OBSERVATIONS_SQL
    from search_indexer.reindex import HTTP_OBSERVATIONS_INDEX, INDEX_MAPPINGS

    row = {
        "id": "obs-1",
        "program_id": "program-1",
        "body_preview": "secret body preview",
    }
    document = build_http_observation_document(row)
    properties = INDEX_MAPPINGS[HTTP_OBSERVATIONS_INDEX]["mappings"]["properties"]

    assert "body_preview" not in document
    assert "body_preview" not in properties
    assert "ho.body_preview" not in HTTP_OBSERVATIONS_SQL
