"""Application-level credential secret version lifecycle service.

Credential refs are stable identity handles. Secret versions are replaceable
runtime materials behind those refs. This service keeps rotation, expiry, and
refresh metadata explicit instead of hiding them inside a storage backend.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from typing import Any, Mapping
from uuid import UUID

from api.application.credential_storage import (
    CredentialRecord,
    CredentialRegistry,
    CredentialSecretStore,
    CredentialSecretVersion,
    CredentialStorageError,
    SecretMaterial,
    utcnow,
)
from api.application.credential_refs import reject_raw_credential_option


@dataclass(frozen=True)
class CredentialRefreshPolicy:
    """Public refresh metadata for a stable credential identity."""

    mode: str = "manual"
    refresh_before_seconds: int | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "mode", _validate_label("refresh mode", self.mode))
        if self.refresh_before_seconds is not None:
            if (
                not isinstance(self.refresh_before_seconds, int)
                or isinstance(self.refresh_before_seconds, bool)
                or self.refresh_before_seconds <= 0
            ):
                raise CredentialStorageError("refresh_before_seconds must be a positive integer")
        _validate_public_mapping("refresh policy metadata", self.metadata)

    def audit_view(self) -> dict[str, Any]:
        view = {"mode": self.mode, "metadata": dict(self.metadata)}
        if self.refresh_before_seconds is not None:
            view["refresh_before_seconds"] = self.refresh_before_seconds
        return view


class CredentialSecretVersionService:
    """Rotate and expire secret versions behind a stable credential_ref."""

    def __init__(
        self,
        *,
        registry: CredentialRegistry,
        secret_store: CredentialSecretStore,
    ) -> None:
        self._registry = registry
        self._secret_store = secret_store

    def rotate_secret(
        self,
        *,
        program_id: UUID,
        credential_ref: str,
        material: SecretMaterial,
        storage_backend: str = "memory_test",
        expires_at: datetime | None = None,
        refresh_policy: CredentialRefreshPolicy | Mapping[str, Any] | None = None,
        key_id: str | None = None,
        external_secret_ref: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> CredentialSecretVersion:
        """Install a new current secret version for an existing credential_ref."""
        credential = self._registry.get_credential(program_id=program_id, credential_ref=credential_ref)
        if credential is None:
            raise CredentialStorageError("credential_ref is not registered")
        if not credential.is_active():
            raise CredentialStorageError("credential_ref is not active")
        if material.kind != credential.secret_kind:
            raise CredentialStorageError("secret material kind does not match credential")
        _validate_future_datetime("expires_at", expires_at, optional=True)
        _validate_public_mapping("secret version metadata", metadata or {})

        policy = _normalize_refresh_policy(refresh_policy)
        next_refresh_at = _derive_next_refresh_at(expires_at=expires_at, policy=policy)
        version = self._secret_store.put_secret(
            credential=credential,
            material=material,
            storage_backend=storage_backend,
            key_id=key_id,
            external_secret_ref=external_secret_ref,
            metadata=metadata or {},
            expires_at=expires_at,
        )
        stored = self._registry.get_credential(program_id=program_id, credential_ref=credential_ref) or credential
        self._registry.update_credential(
            replace(
                stored,
                current_secret_version_id=version.id,
                refresh_policy=policy.audit_view(),
                refresh_status="fresh",
                last_refreshed_at=utcnow(),
                next_refresh_at=next_refresh_at,
                updated_at=utcnow(),
            )
        )
        return version

    def mark_current_secret_expired(self, *, program_id: UUID, credential_ref: str) -> CredentialSecretVersion:
        """Expire the current version and mark the credential as refresh_due."""
        credential = self._registry.get_credential(program_id=program_id, credential_ref=credential_ref)
        if credential is None:
            raise CredentialStorageError("credential_ref is not registered")
        current = self._secret_store.get_current_secret_version(credential)
        if current is None:
            raise CredentialStorageError("credential_ref has no current secret version")
        expired = self._secret_store.mark_secret_version_expired(current.id)
        stored = self._registry.get_credential(program_id=program_id, credential_ref=credential_ref) or credential
        self._registry.update_credential(
            replace(
                stored,
                current_secret_version_id=None,
                refresh_status="refresh_due",
                next_refresh_at=utcnow(),
                updated_at=utcnow(),
            )
        )
        return expired

    def get_current_secret_version(self, *, program_id: UUID, credential_ref: str) -> CredentialSecretVersion:
        credential = self._registry.get_credential(program_id=program_id, credential_ref=credential_ref)
        if credential is None:
            raise CredentialStorageError("credential_ref is not registered")
        current = self._secret_store.get_current_secret_version(credential)
        if current is None or not current.is_active():
            raise CredentialStorageError("credential_ref has no active secret version")
        return current

    def audit_view(self, version: CredentialSecretVersion) -> dict[str, Any]:
        view = version.audit_view()
        view["secret_version_service"] = "credential_secret_version_service"
        view["redacted"] = True
        return view


def _normalize_refresh_policy(
    policy: CredentialRefreshPolicy | Mapping[str, Any] | None,
) -> CredentialRefreshPolicy:
    if policy is None:
        return CredentialRefreshPolicy()
    if isinstance(policy, CredentialRefreshPolicy):
        return policy
    if not isinstance(policy, Mapping):
        raise CredentialStorageError("refresh_policy must be mapping")
    return CredentialRefreshPolicy(
        mode=policy.get("mode", "manual"),
        refresh_before_seconds=policy.get("refresh_before_seconds"),
        metadata=policy.get("metadata", {}),
    )


def _derive_next_refresh_at(*, expires_at: datetime | None, policy: CredentialRefreshPolicy) -> datetime | None:
    if expires_at is None:
        return None
    if policy.refresh_before_seconds is None:
        return None
    return expires_at - timedelta(seconds=policy.refresh_before_seconds)


def _validate_future_datetime(name: str, value: datetime | None, *, optional: bool = False) -> None:
    if value is None:
        if optional:
            return
        raise CredentialStorageError(f"{name} is required")
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise CredentialStorageError(f"{name} must be timezone-aware datetime")
    if value <= utcnow():
        raise CredentialStorageError(f"{name} must be in the future")


def _validate_label(name: str, value: str, *, max_length: int = 120) -> str:
    if not isinstance(value, str):
        raise CredentialStorageError(f"{name} must be string")
    text = value.strip()
    if not text or len(text) > max_length or "\x00" in text or "\n" in text or "\r" in text:
        raise CredentialStorageError(f"{name} is invalid")
    if any(char.isspace() for char in text):
        raise CredentialStorageError(f"{name} must not contain whitespace")
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
