"""Credential store composition boundary.

The credential storage layer is deliberately split into a durable store and a
secret codec. This module is the application composition point that chooses a
codec from process settings and wires it into ``PostgresCredentialStore``. It
keeps plaintext dev/test storage opt-in and prevents accidental production use
of the dev codec.
"""
from __future__ import annotations

from typing import Any, Final

from api.application.credential_storage import CredentialStorageError
from api.config import Settings
from api.infrastructure.credential_store import PostgresCredentialStore
from api.infrastructure.credentials.secret_codec import (
    DevOnlyPlaintextSecretCodec,
    LocalEncryptedSecretCodec,
    SecretCodec,
)

POSTGRES_ENCRYPTED_BACKEND: Final = "postgres_encrypted"
LOCAL_ENCRYPTED_BACKEND: Final = "local_encrypted"
DEV_PLAINTEXT_BACKEND: Final = "dev_plaintext"
_SUPPORTED_BACKENDS: Final = frozenset(
    {
        POSTGRES_ENCRYPTED_BACKEND,
        LOCAL_ENCRYPTED_BACKEND,
        DEV_PLAINTEXT_BACKEND,
    }
)


def build_credential_secret_codec(settings: Settings) -> SecretCodec:
    """Build the configured credential secret codec.

    Default/non-test composition uses ``LocalEncryptedSecretCodec`` and requires
    ``CREDENTIAL_MASTER_KEY``. The dev plaintext backend must be explicitly
    enabled with ``CREDENTIAL_ALLOW_DEV_PLAINTEXT=true`` so a missing master key
    cannot silently downgrade durable secret storage to plaintext.
    """

    backend = _normalize_backend(settings.CREDENTIAL_SECRET_BACKEND)
    if backend in {POSTGRES_ENCRYPTED_BACKEND, LOCAL_ENCRYPTED_BACKEND}:
        master_key = settings.CREDENTIAL_MASTER_KEY
        if master_key is None or not master_key.strip():
            raise CredentialStorageError(
                "CREDENTIAL_MASTER_KEY is required when CREDENTIAL_SECRET_BACKEND="
                f"{settings.CREDENTIAL_SECRET_BACKEND!r}"
            )
        return LocalEncryptedSecretCodec.from_env(
            environ={"CREDENTIAL_MASTER_KEY": master_key},
            key_id=settings.CREDENTIAL_KEY_ID,
        )

    if backend == DEV_PLAINTEXT_BACKEND:
        if not settings.CREDENTIAL_ALLOW_DEV_PLAINTEXT:
            raise CredentialStorageError(
                "CREDENTIAL_SECRET_BACKEND=dev_plaintext requires "
                "CREDENTIAL_ALLOW_DEV_PLAINTEXT=true"
            )
        return DevOnlyPlaintextSecretCodec()

    raise CredentialStorageError(f"unsupported credential secret backend: {settings.CREDENTIAL_SECRET_BACKEND!r}")


def build_postgres_credential_store(connection: Any, settings: Settings) -> PostgresCredentialStore:
    """Build the DB-backed credential store with the configured secret codec."""

    return PostgresCredentialStore(
        connection,
        secret_codec=build_credential_secret_codec(settings),
    )


def _normalize_backend(value: str) -> str:
    if not isinstance(value, str):
        raise CredentialStorageError("credential secret backend must be a string")
    normalized = value.strip().lower().replace("-", "_")
    aliases = {
        "postgres_encrypted_aesgcm": POSTGRES_ENCRYPTED_BACKEND,
        "encrypted_postgres": POSTGRES_ENCRYPTED_BACKEND,
        "aesgcm": POSTGRES_ENCRYPTED_BACKEND,
        "local_encrypted_aesgcm": LOCAL_ENCRYPTED_BACKEND,
        "postgres_dev_plaintext": DEV_PLAINTEXT_BACKEND,
        "plaintext": DEV_PLAINTEXT_BACKEND,
    }
    normalized = aliases.get(normalized, normalized)
    if normalized not in _SUPPORTED_BACKENDS:
        raise CredentialStorageError(
            "credential secret backend must be one of: " + ", ".join(sorted(_SUPPORTED_BACKENDS))
        )
    return normalized
