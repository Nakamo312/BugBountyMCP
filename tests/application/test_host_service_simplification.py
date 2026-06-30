from __future__ import annotations

from pathlib import Path


def test_host_service_uses_model_validation_for_repository_dtos() -> None:
    source = Path("src/api/application/services/host.py").read_text(encoding="utf-8")

    assert "HostResponseDTO(\n" not in source
    assert "EndpointResponseDTO(\n" not in source
    assert "InputParameterResponseDTO(\n" not in source
    assert "HeaderResponseDTO(\n" not in source
    assert "limit=1000" not in source
