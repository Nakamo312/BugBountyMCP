from __future__ import annotations

from datetime import timedelta
import uuid

import pytest

from api.application.credential_storage import (
    MAX_CREDENTIAL_LEASE_TTL_SECONDS,
    CredentialStorageError,
    SecretMaterial,
    credential_lease_request,
    credential_record,
    utcnow,
)
from api.infrastructure.credential_store import InMemoryCredentialStore


def test_secret_material_is_runner_only_and_redacted_from_repr_and_audit_view() -> None:
    material = SecretMaterial.from_text(kind="api_key", value="sk_live_should_not_leak")

    assert material.reveal_for_runner() == b"sk_live_should_not_leak"
    assert "sk_live_should_not_leak" not in repr(material)
    assert material.audit_view() == {
        "kind": "api_key",
        "content_type": "text/plain",
        "present": True,
        "redacted": True,
    }

    # The boundary intentionally does not expose model_dump/json helpers for secret material.
    assert not hasattr(material, "model_dump")


def test_in_memory_store_issues_short_lived_lease_without_exposing_secret_in_audit_views() -> None:
    program_id = uuid.uuid4()
    record = credential_record(
        program_id=program_id,
        credential_ref="credref:program/acme/identity/user_a",
        identity_label="user_a",
        secret_kind="api_key",
        scope={"base_url": "https://target.example", "role": "user"},
        metadata={"owner": "analyst"},
    )
    store = InMemoryCredentialStore()
    store.register_credential(record)
    version = store.put_secret(
        credential=record,
        material=SecretMaterial.from_text(kind="api_key", value="real-secret-token"),
        storage_backend="memory_test",
        metadata={"source": "test_fixture"},
    )
    request = credential_lease_request(
        program_id=program_id,
        credential_ref="credref:program/acme/identity/user_a",
        purpose="idor_probe",
        target_scope="https://target.example/api/orders/123",
        capability="custom_authz_probe",
        ttl_seconds=60,
        auth_injection={"mode": "cli_flag", "flag": "--api-token"},
    )

    lease = store.issue_lease(request)

    assert version.audit_view()["storage_backend"] == "memory_test"
    assert lease.secret_version_id == version.id
    assert lease.is_usable()
    assert store.resolve_secret_for_lease(lease).reveal_for_runner() == b"real-secret-token"
    assert "real-secret-token" not in repr(version)
    assert "real-secret-token" not in repr(lease)
    assert "real-secret-token" not in str(version.audit_view())
    assert "real-secret-token" not in str(lease.audit_view())
    assert lease.audit_view()["auth_injection"] == {
        "mode": "cli_flag",
        "flag": "--api-token",
        "placement": "separate_arg",
    }


def test_lease_request_requires_scope_purpose_and_bounded_ttl() -> None:
    program_id = uuid.uuid4()

    with pytest.raises(CredentialStorageError, match="purpose"):
        credential_lease_request(
            program_id=program_id,
            credential_ref="credref:program/acme/identity/user_a",
            purpose="",
            target_scope="https://target.example",
            capability="probe",
            ttl_seconds=60,
        )

    with pytest.raises(CredentialStorageError, match="ttl_seconds"):
        credential_lease_request(
            program_id=program_id,
            credential_ref="credref:program/acme/identity/user_a",
            purpose="idor_probe",
            target_scope="https://target.example",
            capability="probe",
            ttl_seconds=MAX_CREDENTIAL_LEASE_TTL_SECONDS + 1,
        )


def test_secret_store_rejects_raw_credentials_in_public_metadata_and_wrong_kind() -> None:
    program_id = uuid.uuid4()

    with pytest.raises(CredentialStorageError, match="raw credential"):
        credential_record(
            program_id=program_id,
            credential_ref="credref:program/acme/identity/user_a",
            identity_label="user_a",
            secret_kind="api_key",
            scope={"Authorization": "Bearer raw-token"},
        )

    record = credential_record(
        program_id=program_id,
        credential_ref="credref:program/acme/identity/user_a",
        identity_label="user_a",
        secret_kind="api_key",
        scope={"base_url": "https://target.example"},
    )
    store = InMemoryCredentialStore()

    with pytest.raises(CredentialStorageError, match="kind"):
        store.put_secret(
            credential=record,
            material=SecretMaterial.from_text(kind="cookie", value="session=abc"),
        )


def test_resolve_secret_requires_registered_unexpired_lease() -> None:
    program_id = uuid.uuid4()
    record = credential_record(
        program_id=program_id,
        credential_ref="credref:program/acme/identity/user_a",
        identity_label="user_a",
        secret_kind="api_key",
        scope={"base_url": "https://target.example"},
    )
    store = InMemoryCredentialStore()
    store.put_secret(credential=record, material=SecretMaterial.from_text(kind="api_key", value="secret"))
    lease = store.issue_lease(
        credential_lease_request(
            program_id=program_id,
            credential_ref="credref:program/acme/identity/user_a",
            purpose="idor_probe",
            target_scope="https://target.example",
            capability="probe",
            ttl_seconds=60,
        )
    )

    revoked = store.revoke_lease(lease.id)

    assert not revoked.is_usable()
    with pytest.raises(CredentialStorageError, match="not usable"):
        store.resolve_secret_for_lease(revoked)

    expired_record = credential_record(
        program_id=program_id,
        credential_ref="credref:program/acme/identity/expired",
        identity_label="expired",
        secret_kind="api_key",
        scope={"base_url": "https://target.example"},
        expires_at=utcnow() - timedelta(seconds=1),
    )
    with pytest.raises(CredentialStorageError, match="inactive"):
        store.put_secret(
            credential=expired_record,
            material=SecretMaterial.from_text(kind="api_key", value="expired-secret"),
        )
