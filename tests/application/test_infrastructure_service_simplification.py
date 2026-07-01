from pathlib import Path


INFRASTRUCTURE_SERVICE = Path("src/api/application/services/infrastructure.py")


def test_infrastructure_service_uses_application_reader_boundary() -> None:
    source = INFRASTRUCTURE_SERVICE.read_text(encoding="utf-8")

    assert "InfrastructureGraphReader" in source
    assert "InfrastructureUnitOfWork" not in source
    assert "api.infrastructure" not in source
    assert "async with self" not in source
    assert "self.uow" not in source
    assert "uow." not in source
