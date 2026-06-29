from __future__ import annotations

from datetime import timedelta
import uuid

import pytest

from api.application.credential_secret_versions import (
    CredentialRefreshPolicy,
    CredentialSecretVersionService,
)
from api.application.credential_storage import (
    CredentialStorageError,
    SecretMaterial,
    credential_lease_request,
    credential_record,
    utcnow,
)
from api.infrastructure.credential_store import InMemoryCredentialStore


def _seed() -> tuple[uuid.UUID, str, InMemoryCredentialStore, CredentialSecretVersionService]:
    program_id = uuid.uuid4()
    credential_ref = "credref:program/acme/identity/user_a"
    record = credential_record(
        program_id=program_id,
        credential_ref=credential_ref,
        identity_label="user_a",
        secret_kind="api_key",
        scope={"base_url": "https://target.example", "role": "user"},
    )
    store = InMemoryCredentialStore()
    store.register_credential(record)
    service = CredentialSecretVersionService(registry=store, secret_store=store)
    return program_id, credential_ref, store, service


def test_rotate_secret_keeps_credential_ref_stable_and_updates_current_version() -> None:
    program_id, credential_ref, store, service = _seed()
    expires_at = utcnow() + timedelta(hours=1)

    first = service.rotate_secret(
        program_id=program_id,
        credential_ref=credential_ref,
        material=SecretMaterial.from_text(kind="api_key", value="secret-v1"),
        expires_at=expires_at,
        refresh_policy=CredentialRefreshPolicy(mode="manual", refresh_before_seconds=300),
    )
    second = service.rotate_secret(
        program_id=program_id,
        credential_ref=credential_ref,
        material=SecretMaterial.from_text(kind="api_key", value="secret-v2"),
        expires_at=expires_at + timedelta(hours=1),
        refresh_policy={"mode": "manual", "refresh_before_seconds": 600},
    )

    stored = store.get_credential(program_id=program_id, credential_ref=credential_ref)
    assert stored is not None
    assert stored.credential_ref == credential_ref
    assert stored.current_secret_version_id == second.id
    assert stored.refresh_status == "fresh"
    assert stored.last_refreshed_at is not None
    assert stored.next_refresh_at == second.expires_at - timedelta(seconds=600)

    current = service.get_current_secret_version(program_id=program_id, credential_ref=credential_ref)
    assert current.id == second.id
    assert current.version == 2

    retired_first = store._secret_versions[first.id]  # test-only in-memory inspection
    assert retired_first.status == "retired"
    assert retired_first.replaced_by_version_id == second.id
    assert "secret-v2" not in str(service.audit_view(second))

    lease = store.issue_lease(
        credential_lease_request(
            program_id=program_id,
            credential_ref=credential_ref,
            purpose="idor_probe",
            target_scope="https://target.example/api/orders/123",
            capability="custom_authz_probe",
            ttl_seconds=60,
        )
    )
    assert lease.secret_version_id == second.id
    assert store.resolve_secret_for_lease(lease).reveal_for_runner() == b"secret-v2"


def test_expired_current_secret_version_is_not_used_for_new_leases() -> None:
    program_id, credential_ref, store, service = _seed()
    version = service.rotate_secret(
        program_id=program_id,
        credential_ref=credential_ref,
        material=SecretMaterial.from_text(kind="api_key", value="secret-v1"),
        expires_at=utcnow() + timedelta(hours=1),
    )

    expired = service.mark_current_secret_expired(program_id=program_id, credential_ref=credential_ref)
    assert expired.id == version.id
    assert expired.status == "expired"

    stored = store.get_credential(program_id=program_id, credential_ref=credential_ref)
    assert stored is not None
    assert stored.current_secret_version_id is None
    assert stored.refresh_status == "refresh_due"

    with pytest.raises(CredentialStorageError, match="active secret version"):
        store.issue_lease(
            credential_lease_request(
                program_id=program_id,
                credential_ref=credential_ref,
                purpose="idor_probe",
                target_scope="https://target.example/api/orders/123",
                capability="custom_authz_probe",
                ttl_seconds=60,
            )
        )


def test_secret_version_lifecycle_rejects_raw_refresh_metadata_and_past_expiry() -> None:
    program_id, credential_ref, _store, service = _seed()

    with pytest.raises(CredentialStorageError, match="raw credential"):
        CredentialRefreshPolicy(metadata={"Authorization": "Bearer raw-token"})

    with pytest.raises(CredentialStorageError, match="future"):
        service.rotate_secret(
            program_id=program_id,
            credential_ref=credential_ref,
            material=SecretMaterial.from_text(kind="api_key", value="secret-v1"),
            expires_at=utcnow() - timedelta(seconds=1),
        )
