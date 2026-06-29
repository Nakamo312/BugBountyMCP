from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

import pytest

from api.application.credential_management import (
    CredentialCreateRequest,
    CredentialExpireCurrentSecretRequest,
    CredentialManagementService,
    CredentialMetadataReadRequest,
    CredentialSecretRotateRequest,
)
from api.application.credential_secret_versions import CredentialSecretVersionService
from api.application.credential_storage import CredentialStorageError, utcnow
from api.infrastructure.credential_store import InMemoryCredentialStore


def _service() -> CredentialManagementService:
    store = InMemoryCredentialStore()
    return CredentialManagementService(
        registry=store,
        secret_versions=CredentialSecretVersionService(registry=store, secret_store=store),
    )


def _create_request(program_id):
    return CredentialCreateRequest(
        program_id=program_id,
        credential_ref="credref:program/acme/identity/user_a",
        identity_label="user_a",
        secret_kind="api_key",
        scope={"base_url": "https://target.example"},
        metadata={"source": "manual"},
    )


def test_register_credential_returns_audit_safe_metadata() -> None:
    service = _service()
    program_id = uuid4()

    view = service.register_credential(_create_request(program_id))

    assert view["program_id"] == str(program_id)
    assert view["credential_ref"] == "credref:program/acme/identity/user_a"
    assert view["identity_label"] == "user_a"
    assert view["secret_kind"] == "api_key"
    assert view["current_secret_version_id"] is None
    assert "real-api-token" not in repr(view)
    assert "secret_value" not in repr(view)


def test_rotate_secret_updates_current_version_without_returning_secret() -> None:
    service = _service()
    program_id = uuid4()
    service.register_credential(_create_request(program_id))

    result = service.rotate_secret(
        CredentialSecretRotateRequest(
            program_id=program_id,
            credential_ref="credref:program/acme/identity/user_a",
            secret_value="real-api-token",
            expires_at=utcnow() + timedelta(hours=1),
            refresh_policy={"mode": "manual", "refresh_before_seconds": 300},
        )
    )

    assert result["credential"]["current_secret_version_id"] == result["secret_version"]["id"]
    assert result["credential"]["refresh_status"] == "fresh"
    assert result["secret_material"] == {"present": True, "redacted": True}
    assert "real-api-token" not in repr(result)


def test_rotate_secret_rejects_unregistered_ref_and_secret_like_metadata() -> None:
    service = _service()
    program_id = uuid4()

    with pytest.raises(CredentialStorageError, match="not registered"):
        service.rotate_secret(
            CredentialSecretRotateRequest(
                program_id=program_id,
                credential_ref="credref:program/acme/identity/user_a",
                secret_value="real-api-token",
            )
        )

    service.register_credential(_create_request(program_id))
    with pytest.raises(CredentialStorageError):
        service.rotate_secret(
            CredentialSecretRotateRequest(
                program_id=program_id,
                credential_ref="credref:program/acme/identity/user_a",
                secret_value="real-api-token",
                metadata={"note": "Authorization: Bearer secret"},
            )
        )


def test_get_and_list_metadata_are_audit_safe() -> None:
    service = _service()
    program_id = uuid4()
    service.register_credential(_create_request(program_id))

    one = service.get_metadata(
        CredentialMetadataReadRequest(
            program_id=program_id,
            credential_ref="credref:program/acme/identity/user_a",
        )
    )
    many = service.list_metadata(program_id=program_id)

    assert one["credential_ref"] == "credref:program/acme/identity/user_a"
    assert many == [one]
    assert "secret_value" not in repr(one)
    assert "real-api-token" not in repr(many)


def test_expire_current_secret_marks_credential_refresh_due() -> None:
    service = _service()
    program_id = uuid4()
    service.register_credential(_create_request(program_id))
    service.rotate_secret(
        CredentialSecretRotateRequest(
            program_id=program_id,
            credential_ref="credref:program/acme/identity/user_a",
            secret_value="real-api-token",
        )
    )

    result = service.mark_current_secret_expired(
        CredentialExpireCurrentSecretRequest(
            program_id=program_id,
            credential_ref="credref:program/acme/identity/user_a",
        )
    )

    assert result["credential"]["current_secret_version_id"] is None
    assert result["credential"]["refresh_status"] == "refresh_due"
    assert result["secret_version"]["status"] == "expired"
    assert "real-api-token" not in repr(result)
