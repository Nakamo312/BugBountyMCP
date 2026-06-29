"""Secret encoding boundary for durable credential stores.

Durable stores must never serialize :class:`SecretMaterial` directly into logs,
read models, graph/search projections, or agent-visible state. A store receives
``SecretMaterial`` only at write time, encodes it through a codec, and later
reconstructs ``SecretMaterial`` only when a lease is resolved for a runner.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import base64
import json
import os
from typing import Any, Mapping, Protocol

try:
    from cryptography.exceptions import InvalidTag
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
except ImportError:  # pragma: no cover - exercised only in stripped runtime images
    AESGCM = None  # type: ignore[assignment]

    class InvalidTag(Exception):  # type: ignore[no-redef]
        pass

from api.application.credential_storage import CredentialSecretKind, CredentialStorageError, SecretMaterial
from api.application.credential_refs import reject_raw_credential_option


@dataclass(frozen=True)
class EncodedSecretPayload:
    """Encoded secret payload safe for durable storage metadata paths.

    ``ciphertext`` and ``nonce`` are deliberately omitted from repr. The object
    may represent either local encrypted/blob storage or an external vault
    pointer, but must not expose the raw secret in audit views.
    """

    storage_backend: str
    ciphertext: bytes | None = field(default=None, repr=False)
    nonce: bytes | None = field(default=None, repr=False)
    key_id: str | None = None
    external_secret_ref: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "storage_backend", _validate_label("storage_backend", self.storage_backend))
        if self.ciphertext is not None:
            _validate_bytes("ciphertext", self.ciphertext)
        if self.nonce is not None:
            _validate_bytes("nonce", self.nonce)
        if self.key_id is not None:
            object.__setattr__(self, "key_id", _validate_label("key_id", self.key_id))
        if self.external_secret_ref is not None:
            object.__setattr__(
                self,
                "external_secret_ref",
                _validate_ref_text("external_secret_ref", self.external_secret_ref, max_length=500),
            )
        if self.ciphertext is None and self.external_secret_ref is None:
            raise CredentialStorageError("encoded secret requires ciphertext or external_secret_ref")
        _validate_public_mapping("encoded secret metadata", self.metadata)

    def audit_view(self) -> dict[str, Any]:
        return {
            "storage_backend": self.storage_backend,
            "key_id": self.key_id,
            "external_secret_ref": self.external_secret_ref,
            "ciphertext_present": self.ciphertext is not None,
            "nonce_present": self.nonce is not None,
            "metadata": dict(self.metadata),
            "redacted": True,
        }


class SecretCodec(Protocol):
    """Encode/decode secret material for one storage backend."""

    storage_backend: str

    def encode(self, material: SecretMaterial) -> EncodedSecretPayload: ...

    def decode(
        self,
        *,
        secret_kind: CredentialSecretKind,
        payload: EncodedSecretPayload,
    ) -> SecretMaterial: ...


class DevOnlyPlaintextSecretCodec:
    """Dev/test codec that stores bytes without encryption.

    This codec is intentionally noisy in its name and backend id. Production
    composition must provide an encrypted or external-vault codec instead.
    """

    storage_backend = "postgres_dev_plaintext"
    key_id = "dev-only-plaintext"
    _prefix = b"dev-plaintext-v1:"

    def encode(self, material: SecretMaterial) -> EncodedSecretPayload:
        return EncodedSecretPayload(
            storage_backend=self.storage_backend,
            ciphertext=self._prefix + material.reveal_for_runner(),
            key_id=self.key_id,
            metadata={"content_type": material.content_type},
        )

    def decode(
        self,
        *,
        secret_kind: CredentialSecretKind,
        payload: EncodedSecretPayload,
    ) -> SecretMaterial:
        if payload.storage_backend != self.storage_backend:
            raise CredentialStorageError("secret payload storage backend does not match codec")
        if payload.ciphertext is None:
            raise CredentialStorageError("dev plaintext codec requires ciphertext")
        if not payload.ciphertext.startswith(self._prefix):
            raise CredentialStorageError("dev plaintext ciphertext prefix is invalid")
        content_type = payload.metadata.get("content_type", "application/octet-stream")
        if not isinstance(content_type, str) or not content_type.strip():
            raise CredentialStorageError("encoded secret content_type metadata is invalid")
        return SecretMaterial(
            kind=secret_kind,
            value=payload.ciphertext[len(self._prefix) :],
            content_type=content_type,
        )


class LocalEncryptedSecretCodec:
    """AES-GCM codec for local/Postgres encrypted secret storage.

    The database stores ciphertext, nonce, key id, and public metadata only. The
    master key must come from process configuration, Docker secret, KMS bootstrap,
    or another source outside the database. This backend is self-contained and
    testable locally; larger deployments can replace it with an external
    vault/KMS codec without changing ``PostgresCredentialStore``.
    """

    storage_backend = "postgres_encrypted_aesgcm"
    algorithm = "AES-256-GCM"
    nonce_size = 12

    def __init__(self, *, master_key: bytes, key_id: str = "local-master-key") -> None:
        if AESGCM is None:
            raise CredentialStorageError(
                "LocalEncryptedSecretCodec requires the optional 'cryptography' package"
            )
        if not isinstance(master_key, bytes):
            raise CredentialStorageError("credential master key must be bytes")
        if len(master_key) != 32:
            raise CredentialStorageError("credential master key must be exactly 32 bytes for AES-256-GCM")
        self._aesgcm = AESGCM(master_key)
        self.key_id = _validate_label("key_id", key_id)

    @classmethod
    def from_env(
        cls,
        *,
        env_var: str = "CREDENTIAL_MASTER_KEY",
        key_id: str = "local-env-master-key",
        environ: Mapping[str, str] | None = None,
    ) -> "LocalEncryptedSecretCodec":
        source = os.environ if environ is None else environ
        raw = source.get(env_var)
        if raw is None or not raw.strip():
            raise CredentialStorageError(f"{env_var} is required for LocalEncryptedSecretCodec")
        return cls(master_key=_decode_master_key(raw), key_id=key_id)

    @staticmethod
    def generate_master_key_b64() -> str:
        """Return a base64-encoded 32-byte key suitable for local dev configuration."""

        return base64.urlsafe_b64encode(os.urandom(32)).decode("ascii")

    def encode(self, material: SecretMaterial) -> EncodedSecretPayload:
        nonce = os.urandom(self.nonce_size)
        metadata = {
            "algorithm": self.algorithm,
            "content_type": material.content_type,
        }
        ciphertext = self._aesgcm.encrypt(
            nonce,
            material.reveal_for_runner(),
            _aad(
                storage_backend=self.storage_backend,
                key_id=self.key_id,
                secret_kind=material.kind,
                metadata=metadata,
            ),
        )
        return EncodedSecretPayload(
            storage_backend=self.storage_backend,
            ciphertext=ciphertext,
            nonce=nonce,
            key_id=self.key_id,
            metadata=metadata,
        )

    def decode(
        self,
        *,
        secret_kind: CredentialSecretKind,
        payload: EncodedSecretPayload,
    ) -> SecretMaterial:
        if payload.storage_backend != self.storage_backend:
            raise CredentialStorageError("secret payload storage backend does not match codec")
        if payload.key_id != self.key_id:
            raise CredentialStorageError("secret payload key_id does not match codec")
        if payload.ciphertext is None or payload.nonce is None:
            raise CredentialStorageError("encrypted codec requires ciphertext and nonce")
        if len(payload.nonce) != self.nonce_size:
            raise CredentialStorageError("encrypted secret nonce length is invalid")
        algorithm = payload.metadata.get("algorithm")
        if algorithm != self.algorithm:
            raise CredentialStorageError("encrypted secret algorithm metadata is invalid")
        content_type = payload.metadata.get("content_type", "application/octet-stream")
        if not isinstance(content_type, str) or not content_type.strip():
            raise CredentialStorageError("encoded secret content_type metadata is invalid")
        try:
            value = self._aesgcm.decrypt(
                payload.nonce,
                payload.ciphertext,
                _aad(
                    storage_backend=payload.storage_backend,
                    key_id=payload.key_id,
                    secret_kind=secret_kind,
                    metadata={"algorithm": algorithm, "content_type": content_type},
                ),
            )
        except InvalidTag as exc:
            raise CredentialStorageError("encrypted secret could not be decoded with the configured key") from exc
        return SecretMaterial(kind=secret_kind, value=value, content_type=content_type)


def _decode_master_key(value: str) -> bytes:
    text = value.strip()
    if text.startswith("base64:"):
        text = text[len("base64:") :]
    try:
        decoded = base64.urlsafe_b64decode(text.encode("ascii"))
    except Exception as exc:  # noqa: BLE001 - normalize config parsing errors
        raise CredentialStorageError("credential master key must be URL-safe base64") from exc
    if len(decoded) != 32:
        raise CredentialStorageError("credential master key must decode to exactly 32 bytes")
    return decoded


def _aad(
    *,
    storage_backend: str,
    key_id: str | None,
    secret_kind: CredentialSecretKind,
    metadata: Mapping[str, Any],
) -> bytes:
    return json.dumps(
        {
            "storage_backend": storage_backend,
            "key_id": key_id,
            "secret_kind": secret_kind,
            "algorithm": metadata.get("algorithm"),
            "content_type": metadata.get("content_type"),
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _validate_bytes(name: str, value: bytes) -> None:
    if not isinstance(value, bytes):
        raise CredentialStorageError(f"{name} must be bytes")
    if not value:
        raise CredentialStorageError(f"{name} must not be empty")


def _validate_label(name: str, value: str, *, max_length: int = 120) -> str:
    if not isinstance(value, str):
        raise CredentialStorageError(f"{name} must be string")
    text = value.strip()
    if not text or len(text) > max_length or "\x00" in text or "\n" in text or "\r" in text:
        raise CredentialStorageError(f"{name} is invalid")
    if any(char.isspace() for char in text):
        raise CredentialStorageError(f"{name} must not contain whitespace")
    return text


def _validate_ref_text(name: str, value: str, *, max_length: int) -> str:
    if not isinstance(value, str):
        raise CredentialStorageError(f"{name} must be string")
    text = value.strip()
    if not text or len(text) > max_length or "\x00" in text or "\n" in text or "\r" in text:
        raise CredentialStorageError(f"{name} is invalid")
    return text


def _validate_public_mapping(name: str, value: Mapping[str, Any]) -> None:
    if not isinstance(value, Mapping):
        raise CredentialStorageError(f"{name} must be mapping")
    for key, item in value.items():
        if not isinstance(key, str) or not key.strip() or "\x00" in key:
            raise CredentialStorageError(f"{name} contains invalid key")
        try:
            reject_raw_credential_option(f"{name}.{key}", item)
        except ValueError as exc:
            raise CredentialStorageError(str(exc)) from exc
