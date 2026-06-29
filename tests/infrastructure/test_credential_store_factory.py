from __future__ import annotations

import base64
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, insert, select

from api.application.credential_storage import CredentialStorageError, SecretMaterial, credential_record
from api.config import Settings
from api.infrastructure.adapters.orm import credential_leases, credential_refs, credential_secret_versions, metadata, programs
from api.infrastructure.credential_store import PostgresCredentialStore
from api.infrastructure.credentials.factory import build_credential_secret_codec, build_postgres_credential_store
from api.infrastructure.credentials.secret_codec import DevOnlyPlaintextSecretCodec, LocalEncryptedSecretCodec


def _master_key() -> str:
    return "base64:" + base64.urlsafe_b64encode(bytes(range(32))).decode("ascii")


def test_credential_secret_backend_defaults_to_encrypted_postgres() -> None:
    settings = Settings()

    assert settings.CREDENTIAL_SECRET_BACKEND == "postgres_encrypted"
    assert settings.CREDENTIAL_ALLOW_DEV_PLAINTEXT is False


@pytest.mark.parametrize("backend", ["postgres_encrypted", "local_encrypted", "postgres-encrypted", "aesgcm"])
def test_factory_builds_local_encrypted_codec_when_master_key_is_configured(backend: str) -> None:
    settings = Settings(
        CREDENTIAL_SECRET_BACKEND=backend,
        CREDENTIAL_MASTER_KEY=_master_key(),
        CREDENTIAL_KEY_ID="test-key",
    )

    codec = build_credential_secret_codec(settings)

    assert isinstance(codec, LocalEncryptedSecretCodec)
    assert codec.key_id == "test-key"


def test_factory_rejects_encrypted_backend_without_master_key() -> None:
    settings = Settings(CREDENTIAL_SECRET_BACKEND="postgres_encrypted", CREDENTIAL_MASTER_KEY=None)

    with pytest.raises(CredentialStorageError, match="CREDENTIAL_MASTER_KEY"):
        build_credential_secret_codec(settings)


def test_factory_rejects_unknown_backend() -> None:
    settings = Settings(CREDENTIAL_SECRET_BACKEND="vaultish", CREDENTIAL_MASTER_KEY=_master_key())

    with pytest.raises(CredentialStorageError, match="credential secret backend"):
        build_credential_secret_codec(settings)


def test_factory_refuses_dev_plaintext_without_explicit_opt_in() -> None:
    settings = Settings(CREDENTIAL_SECRET_BACKEND="dev_plaintext")

    with pytest.raises(CredentialStorageError, match="CREDENTIAL_ALLOW_DEV_PLAINTEXT"):
        build_credential_secret_codec(settings)


def test_factory_allows_dev_plaintext_only_with_explicit_opt_in() -> None:
    settings = Settings(
        CREDENTIAL_SECRET_BACKEND="dev_plaintext",
        CREDENTIAL_ALLOW_DEV_PLAINTEXT=True,
    )

    codec = build_credential_secret_codec(settings)

    assert isinstance(codec, DevOnlyPlaintextSecretCodec)


def test_postgres_credential_store_factory_wires_encrypted_codec_without_plaintext_in_db() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    metadata.create_all(engine, tables=[programs, credential_refs, credential_secret_versions, credential_leases])
    connection = engine.connect()
    program_id = uuid4()
    connection.execute(insert(programs).values(id=program_id, name=f"program-{program_id.hex}"))
    settings = Settings(
        CREDENTIAL_SECRET_BACKEND="postgres_encrypted",
        CREDENTIAL_MASTER_KEY=_master_key(),
        CREDENTIAL_KEY_ID="factory-test-key",
    )

    store = build_postgres_credential_store(connection, settings)
    assert isinstance(store, PostgresCredentialStore)
    credential = credential_record(
        program_id=program_id,
        credential_ref="credref:program/acme/identity/user_a",
        identity_label="user_a",
        secret_kind="api_key",
        scope={"base_url": "https://target.example"},
    )

    store.put_secret(
        credential=credential,
        material=SecretMaterial.from_text(kind="api_key", value="factory-secret-token"),
    )

    row = connection.execute(select(credential_secret_versions)).mappings().one()
    assert row["storage_backend"] == "postgres_encrypted_aesgcm"
    assert row["key_id"] == "factory-test-key"
    assert b"factory-secret-token" not in row["ciphertext"]
