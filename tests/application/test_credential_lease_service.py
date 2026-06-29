from __future__ import annotations

import uuid

import pytest

from api.application.credential_leases import CredentialLeasePolicy, CredentialLeaseService
from api.application.credential_storage import (
    CredentialStorageError,
    SecretMaterial,
    credential_record,
)
from api.infrastructure.credential_store import InMemoryCredentialStore


def _seed_store(*, secret_kind: str = "api_key") -> tuple[uuid.UUID, InMemoryCredentialStore, str]:
    program_id = uuid.uuid4()
    credential_ref = "credref:program/acme/identity/user_a"
    record = credential_record(
        program_id=program_id,
        credential_ref=credential_ref,
        identity_label="user_a",
        secret_kind=secret_kind,
        scope={"base_url": "https://target.example", "role": "user"},
    )
    store = InMemoryCredentialStore()
    store.put_secret(
        credential=record,
        material=SecretMaterial.from_text(kind=secret_kind, value="real-secret-token"),
    )
    return program_id, store, credential_ref


def test_credential_lease_service_issues_audit_safe_lease_and_resolves_only_for_same_context() -> None:
    program_id, store, credential_ref = _seed_store()
    service = CredentialLeaseService(
        registry=store,
        secret_store=store,
        lease_store=store,
        policy=CredentialLeasePolicy(default_ttl_seconds=60, max_ttl_seconds=120),
    )

    lease = service.request_lease(
        program_id=program_id,
        credential_ref=credential_ref,
        purpose="idor_probe",
        target_scope="https://target.example/api/orders/123",
        capability="custom_authz_probe",
        auth_injection={"mode": "env", "slot": "TOOL_TOKEN"},
    )

    audit_view = service.audit_view(lease)
    assert audit_view["lease_service"] == "credential_lease_service"
    assert audit_view["redacted"] is True
    assert "real-secret-token" not in repr(lease)
    assert "real-secret-token" not in str(audit_view)
    assert service.resolve_secret_for_runner(
        lease,
        purpose="idor_probe",
        capability="custom_authz_probe",
        target_scope="https://target.example/api/orders/123",
    ).reveal_for_runner() == b"real-secret-token"

    with pytest.raises(CredentialStorageError, match="purpose mismatch"):
        service.resolve_secret_for_runner(
            lease,
            purpose="different_probe",
            capability="custom_authz_probe",
        )
    with pytest.raises(CredentialStorageError, match="capability mismatch"):
        service.resolve_secret_for_runner(
            lease,
            purpose="idor_probe",
            capability="other_tool",
        )


def test_credential_lease_service_enforces_ttl_policy_before_store_issue() -> None:
    program_id, store, credential_ref = _seed_store()
    service = CredentialLeaseService(
        registry=store,
        secret_store=store,
        lease_store=store,
        policy=CredentialLeasePolicy(default_ttl_seconds=30, max_ttl_seconds=45),
    )

    lease = service.request_lease(
        program_id=program_id,
        credential_ref=credential_ref,
        purpose="idor_probe",
        target_scope="https://target.example/api/orders/123",
        capability="custom_authz_probe",
    )
    assert int((lease.expires_at - lease.issued_at).total_seconds()) == 30

    with pytest.raises(CredentialStorageError, match="exceeds credential lease policy"):
        service.request_lease(
            program_id=program_id,
            credential_ref=credential_ref,
            purpose="idor_probe",
            target_scope="https://target.example/api/orders/123",
            capability="custom_authz_probe",
            ttl_seconds=60,
        )


def test_credential_lease_service_requires_explicit_policy_for_cli_flag_injection() -> None:
    program_id, store, credential_ref = _seed_store()
    default_service = CredentialLeaseService(
        registry=store,
        secret_store=store,
        lease_store=store,
    )

    with pytest.raises(CredentialStorageError, match="argv exposure policy"):
        default_service.request_lease(
            program_id=program_id,
            credential_ref=credential_ref,
            purpose="tool_probe",
            target_scope="https://target.example",
            capability="some_cli_tool",
            auth_injection={"mode": "cli_flag", "flag": "--api-token"},
        )

    strict_service = CredentialLeaseService(
        registry=store,
        secret_store=store,
        lease_store=store,
        policy=CredentialLeasePolicy(
            allow_argv_exposure=True,
            allowed_cli_flags=("--approved-token",),
        ),
    )
    with pytest.raises(CredentialStorageError, match="flag is not allowed"):
        strict_service.request_lease(
            program_id=program_id,
            credential_ref=credential_ref,
            purpose="tool_probe",
            target_scope="https://target.example",
            capability="some_cli_tool",
            auth_injection={"mode": "cli_flag", "flag": "--api-token"},
        )

    allowed = strict_service.request_lease(
        program_id=program_id,
        credential_ref=credential_ref,
        purpose="tool_probe",
        target_scope="https://target.example",
        capability="some_cli_tool",
        auth_injection={"mode": "cli_flag", "flag": "--approved-token"},
    )
    assert allowed.auth_injection == {
        "mode": "cli_flag",
        "flag": "--approved-token",
        "placement": "separate_arg",
    }


def test_credential_lease_policy_rejects_raw_credentials_in_audit_context() -> None:
    with pytest.raises(CredentialStorageError, match="raw credential"):
        CredentialLeasePolicy(audit_context={"Authorization": "Bearer raw-token"})
