from __future__ import annotations

from datetime import timedelta
import base64
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, insert, select

from api.application.credential_leases import CredentialLeasePolicy, CredentialLeaseService
from api.application.credential_secret_versions import CredentialRefreshPolicy, CredentialSecretVersionService
from api.application.credential_storage import CredentialStorageError, SecretMaterial, credential_record, utcnow
from api.infrastructure.adapters.orm import credential_leases, credential_refs, credential_secret_versions, metadata, programs
from api.infrastructure.credential_store import PostgresCredentialStore
from api.infrastructure.credentials.secret_codec import DevOnlyPlaintextSecretCodec, EncodedSecretPayload, LocalEncryptedSecretCodec


def _store():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    metadata.create_all(
        engine,
        tables=[programs, credential_refs, credential_secret_versions, credential_leases],
    )
    connection = engine.connect()
    program_id = uuid4()
    connection.execute(insert(programs).values(id=program_id, name=f"program-{program_id.hex}"))
    return connection, program_id, PostgresCredentialStore(
        connection,
        secret_codec=DevOnlyPlaintextSecretCodec(),
    )


def test_postgres_credential_store_requires_explicit_secret_codec() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    connection = engine.connect()

    with pytest.raises(CredentialStorageError, match="explicit secret codec"):
        PostgresCredentialStore(connection, secret_codec=None)  # type: ignore[arg-type]


def test_dev_plaintext_codec_is_explicit_and_does_not_leak_secret_in_repr_or_audit() -> None:
    codec = DevOnlyPlaintextSecretCodec()
    payload = codec.encode(SecretMaterial.from_text(kind="api_key", value="secret-token"))

    assert payload.storage_backend == "postgres_dev_plaintext"
    assert "secret-token" not in repr(payload)
    assert "secret-token" not in str(payload.audit_view())
    decoded = codec.decode(secret_kind="api_key", payload=payload)
    assert decoded.reveal_for_runner() == b"secret-token"

    with pytest.raises(CredentialStorageError, match="metadata"):
        EncodedSecretPayload(
            storage_backend="postgres_dev_plaintext",
            ciphertext=b"ciphertext",
            metadata={"Authorization": "Bearer raw-token"},
        )


def test_postgres_credential_store_rotates_versions_and_new_leases_use_current_secret() -> None:
    connection, program_id, store = _store()
    credential_ref = "credref:program/acme/identity/user_a"
    record = credential_record(
        program_id=program_id,
        credential_ref=credential_ref,
        identity_label="user_a",
        secret_kind="api_key",
        scope={"base_url": "https://target.example", "role": "user"},
    )
    store.register_credential(record)
    version_service = CredentialSecretVersionService(registry=store, secret_store=store)
    lease_service = CredentialLeaseService(
        registry=store,
        secret_store=store,
        lease_store=store,
        policy=CredentialLeasePolicy(default_ttl_seconds=60, max_ttl_seconds=120),
    )

    first = version_service.rotate_secret(
        program_id=program_id,
        credential_ref=credential_ref,
        material=SecretMaterial.from_text(kind="api_key", value="secret-v1"),
        expires_at=utcnow() + timedelta(hours=1),
        refresh_policy=CredentialRefreshPolicy(mode="manual", refresh_before_seconds=300),
    )
    first_lease = lease_service.request_lease(
        program_id=program_id,
        credential_ref=credential_ref,
        purpose="idor_probe",
        target_scope="https://target.example/api/orders/123",
        capability="custom_authz_probe",
    )

    second = version_service.rotate_secret(
        program_id=program_id,
        credential_ref=credential_ref,
        material=SecretMaterial.from_text(kind="api_key", value="secret-v2"),
        expires_at=utcnow() + timedelta(hours=2),
        refresh_policy={"mode": "manual", "refresh_before_seconds": 600},
    )
    second_lease = lease_service.request_lease(
        program_id=program_id,
        credential_ref=credential_ref,
        purpose="idor_probe",
        target_scope="https://target.example/api/orders/123",
        capability="custom_authz_probe",
    )

    stored = store.get_credential(program_id=program_id, credential_ref=credential_ref)
    assert stored is not None
    assert stored.current_secret_version_id == second.id
    assert stored.refresh_status == "fresh"
    assert stored.next_refresh_at == second.expires_at - timedelta(seconds=600)

    retired_first = connection.execute(
        credential_secret_versions.select().where(credential_secret_versions.c.id == first.id)
    ).mappings().one()
    assert retired_first["status"] == "retired"
    assert retired_first["replaced_by_version_id"] == second.id

    assert first_lease.secret_version_id == first.id
    assert second_lease.secret_version_id == second.id
    assert lease_service.resolve_secret_for_runner(
        first_lease,
        purpose="idor_probe",
        capability="custom_authz_probe",
        target_scope="https://target.example/api/orders/123",
    ).reveal_for_runner() == b"secret-v1"
    assert lease_service.resolve_secret_for_runner(
        second_lease,
        purpose="idor_probe",
        capability="custom_authz_probe",
        target_scope="https://target.example/api/orders/123",
    ).reveal_for_runner() == b"secret-v2"


def test_postgres_credential_store_rejects_new_lease_when_current_version_is_expired() -> None:
    _connection, program_id, store = _store()
    credential_ref = "credref:program/acme/identity/user_a"
    store.register_credential(
        credential_record(
            program_id=program_id,
            credential_ref=credential_ref,
            identity_label="user_a",
            secret_kind="api_key",
            scope={"base_url": "https://target.example", "role": "user"},
        )
    )
    version_service = CredentialSecretVersionService(registry=store, secret_store=store)
    lease_service = CredentialLeaseService(
        registry=store,
        secret_store=store,
        lease_store=store,
    )
    version_service.rotate_secret(
        program_id=program_id,
        credential_ref=credential_ref,
        material=SecretMaterial.from_text(kind="api_key", value="secret-v1"),
        expires_at=utcnow() + timedelta(hours=1),
    )

    version_service.mark_current_secret_expired(program_id=program_id, credential_ref=credential_ref)

    stored = store.get_credential(program_id=program_id, credential_ref=credential_ref)
    assert stored is not None
    assert stored.current_secret_version_id is None
    assert stored.refresh_status == "refresh_due"
    with pytest.raises(CredentialStorageError, match="active secret version"):
        lease_service.request_lease(
            program_id=program_id,
            credential_ref=credential_ref,
            purpose="idor_probe",
            target_scope="https://target.example/api/orders/123",
            capability="custom_authz_probe",
        )


def test_postgres_credential_store_revokes_lease_before_secret_resolution() -> None:
    _connection, program_id, store = _store()
    credential_ref = "credref:program/acme/identity/user_a"
    store.put_secret(
        credential=credential_record(
            program_id=program_id,
            credential_ref=credential_ref,
            identity_label="user_a",
            secret_kind="api_key",
            scope={"base_url": "https://target.example", "role": "user"},
        ),
        material=SecretMaterial.from_text(kind="api_key", value="secret-v1"),
    )
    lease_service = CredentialLeaseService(
        registry=store,
        secret_store=store,
        lease_store=store,
    )
    lease = lease_service.request_lease(
        program_id=program_id,
        credential_ref=credential_ref,
        purpose="idor_probe",
        target_scope="https://target.example/api/orders/123",
        capability="custom_authz_probe",
    )

    revoked = lease_service.revoke_lease(lease.id)

    assert revoked.status == "revoked"
    with pytest.raises(CredentialStorageError, match="lease is not usable"):
        lease_service.resolve_secret_for_runner(
            revoked,
            purpose="idor_probe",
            capability="custom_authz_probe",
            target_scope="https://target.example/api/orders/123",
        )


def _encrypted_codec(key_byte: int = 7, *, key_id: str = "local-test-key") -> LocalEncryptedSecretCodec:
    return LocalEncryptedSecretCodec(master_key=bytes([key_byte]) * 32, key_id=key_id)


def test_local_encrypted_secret_codec_encrypts_and_decrypts_without_plaintext_leakage() -> None:
    codec = _encrypted_codec()
    material = SecretMaterial.from_text(kind="api_key", value="secret-token")

    payload = codec.encode(material)

    assert payload.storage_backend == "postgres_encrypted_aesgcm"
    assert payload.nonce is not None and len(payload.nonce) == 12
    assert payload.ciphertext is not None
    assert b"secret-token" not in payload.ciphertext
    assert "secret-token" not in repr(payload)
    assert "secret-token" not in str(payload.audit_view())
    assert payload.audit_view()["ciphertext_present"] is True
    decoded = codec.decode(secret_kind="api_key", payload=payload)
    assert decoded.reveal_for_runner() == b"secret-token"


def test_local_encrypted_secret_codec_rejects_wrong_key_or_wrong_key_id() -> None:
    payload = _encrypted_codec(7, key_id="key-a").encode(
        SecretMaterial.from_text(kind="api_key", value="secret-token")
    )

    with pytest.raises(CredentialStorageError, match="key_id"):
        _encrypted_codec(8, key_id="key-b").decode(secret_kind="api_key", payload=payload)

    same_key_wrong_id = _encrypted_codec(7, key_id="key-b")
    with pytest.raises(CredentialStorageError, match="key_id"):
        same_key_wrong_id.decode(secret_kind="api_key", payload=payload)

    tampered_ciphertext = payload.ciphertext[:-1] + bytes([payload.ciphertext[-1] ^ 0x01])
    tampered = EncodedSecretPayload(
        storage_backend=payload.storage_backend,
        ciphertext=tampered_ciphertext,
        nonce=payload.nonce,
        key_id=payload.key_id,
        metadata=payload.metadata,
    )
    with pytest.raises(CredentialStorageError, match="could not be decoded"):
        _encrypted_codec(7, key_id="key-a").decode(secret_kind="api_key", payload=tampered)


def test_local_encrypted_secret_codec_from_env_validates_base64_master_key() -> None:
    key = base64.urlsafe_b64encode(bytes(range(32))).decode("ascii")
    codec = LocalEncryptedSecretCodec.from_env(environ={"CREDENTIAL_MASTER_KEY": f"base64:{key}"})

    payload = codec.encode(SecretMaterial.from_text(kind="api_key", value="secret-token"))

    assert codec.decode(secret_kind="api_key", payload=payload).reveal_for_runner() == b"secret-token"
    with pytest.raises(CredentialStorageError, match="required"):
        LocalEncryptedSecretCodec.from_env(environ={})
    with pytest.raises(CredentialStorageError, match="32 bytes"):
        LocalEncryptedSecretCodec.from_env(environ={"CREDENTIAL_MASTER_KEY": base64.urlsafe_b64encode(b"short").decode("ascii")})


def test_postgres_credential_store_with_local_encrypted_codec_keeps_plaintext_out_of_db() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    metadata.create_all(
        engine,
        tables=[programs, credential_refs, credential_secret_versions, credential_leases],
    )
    connection = engine.connect()
    program_id = uuid4()
    connection.execute(insert(programs).values(id=program_id, name=f"program-{program_id.hex}"))
    store = PostgresCredentialStore(connection, secret_codec=_encrypted_codec())
    record = credential_record(
        program_id=program_id,
        credential_ref="credref:program/acme/identity/user_a",
        identity_label="user_a",
        secret_kind="api_key",
        scope={"base_url": "https://target.example", "role": "user"},
    )

    store.put_secret(
        credential=record,
        material=SecretMaterial.from_text(kind="api_key", value="secret-v1"),
        expires_at=utcnow() + timedelta(hours=1),
    )
    row = connection.execute(select(credential_secret_versions)).mappings().one()

    assert row["storage_backend"] == "postgres_encrypted_aesgcm"
    assert row["key_id"] == "local-test-key"
    assert row["nonce"] is not None
    assert b"secret-v1" not in row["ciphertext"]

    lease_service = CredentialLeaseService(
        registry=store,
        secret_store=store,
        lease_store=store,
    )
    lease = lease_service.request_lease(
        program_id=program_id,
        credential_ref="credref:program/acme/identity/user_a",
        purpose="idor_probe",
        target_scope="https://target.example/api/orders/123",
        capability="custom_authz_probe",
    )

    assert lease_service.resolve_secret_for_runner(
        lease,
        purpose="idor_probe",
        capability="custom_authz_probe",
        target_scope="https://target.example/api/orders/123",
    ).reveal_for_runner() == b"secret-v1"
