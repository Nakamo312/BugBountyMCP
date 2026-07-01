from __future__ import annotations

from pathlib import Path


def test_credential_management_routes_are_registered_and_audit_safe() -> None:
    source = Path("src/api/presentation/rest/routes/credentials.py").read_text(encoding="utf-8")
    router_source = Path("src/api/presentation/rest/routes/__init__.py").read_text(encoding="utf-8")
    service_source = Path("src/api/application/credential_management.py").read_text(encoding="utf-8")
    container_source = Path("src/api/infrastructure/container.py").read_text(encoding="utf-8")
    credential_provider_source = Path("src/api/infrastructure/providers/credentials.py").read_text(encoding="utf-8")

    assert '@router.post(\n    ""' in source
    assert '@router.post(\n    "/rotate-secret"' in source
    assert '@router.post(\n    "/expire-current-secret"' in source
    assert '@router.get(\n    "/metadata"' in source
    assert 'prefix="/api/v1/credentials"' in router_source
    assert "CredentialManagementService" in source
    assert "SecretStr" in service_source
    assert "secret_value: SecretStr" in service_source
    assert "get_secret_value()" in service_source
    assert "secret_material" in service_source
    assert "audit-safe" in service_source
    assert "CredentialProvider" in container_source
    assert "build_postgres_credential_store" in credential_provider_source


def test_credential_management_boundaries_do_not_expose_secret_resolve_or_runner_materialization() -> None:
    source = Path("src/api/presentation/rest/routes/credentials.py").read_text(encoding="utf-8")
    service_source = Path("src/api/application/credential_management.py").read_text(encoding="utf-8")

    forbidden_route_tokens = (
        "resolve_secret_for_runner",
        "resolve_secret_for_lease",
        "materialize_credential_for_runner",
        "CommandExecutor",
        "subprocess",
    )
    for token in forbidden_route_tokens:
        assert token not in source

    assert "resolve_secret_for_runner" not in service_source
    assert "resolve_secret_for_lease" not in service_source
