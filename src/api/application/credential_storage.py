"""Credential registry, secret material, and lease contracts.

This module defines where credentials may exist in the application boundary.
Secret values are allowed only as ``SecretMaterial`` objects and only for
runner-side materialization after a lease is issued. Public records, leases,
events, read models, graph/search projections, and agent context must use
opaque credential references and redacted audit metadata.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import uuid
from typing import Any, Literal, Mapping, Protocol, Sequence
from uuid import UUID

from api.application.credential_refs import (
    normalize_auth_injection_spec,
    normalize_credential_ref,
    reject_raw_credential_option,
)

CredentialSecretKind = Literal[
    "bearer_token",
    "api_key",
    "cookie",
    "cookie_jar",
    "basic_auth",
    "oauth_token",
    "client_cert",
    "custom",
]
CredentialStatus = Literal["active", "disabled", "revoked"]
CredentialSecretVersionStatus = Literal["active", "retired", "expired", "revoked"]
CredentialRefreshStatus = Literal["not_configured", "fresh", "refresh_due", "refresh_failed", "disabled"]
CredentialLeaseStatus = Literal["issued", "used", "expired", "revoked"]

SECRET_KINDS: frozenset[str] = frozenset(
    {
        "bearer_token",
        "api_key",
        "cookie",
        "cookie_jar",
        "basic_auth",
        "oauth_token",
        "client_cert",
        "custom",
    }
)
CREDENTIAL_STATUSES: frozenset[str] = frozenset({"active", "disabled", "revoked"})
SECRET_VERSION_STATUSES: frozenset[str] = frozenset({"active", "retired", "expired", "revoked"})
REFRESH_STATUSES: frozenset[str] = frozenset({"not_configured", "fresh", "refresh_due", "refresh_failed", "disabled"})
LEASE_STATUSES: frozenset[str] = frozenset({"issued", "used", "expired", "revoked"})
MAX_CREDENTIAL_LEASE_TTL_SECONDS = 15 * 60


class CredentialStorageError(ValueError):
    """Raised when credential registry, secret, or lease contracts are invalid."""


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class SecretMaterial:
    """Runner-only secret bytes.

    ``value`` is deliberately excluded from ``repr``. Do not place this object
    into pydantic models, events, logs, graph facts, OpenSearch documents, or
    agent messages. It may only cross the lease resolver -> runner injector
    boundary.
    """

    kind: CredentialSecretKind
    value: bytes = field(repr=False)
    content_type: str = "application/octet-stream"

    def __post_init__(self) -> None:
        _validate_secret_kind(self.kind)
        if not isinstance(self.value, bytes):
            raise CredentialStorageError("secret material must be bytes")
        if not self.value:
            raise CredentialStorageError("secret material must not be empty")
        if b"\x00" in self.value:
            raise CredentialStorageError("secret material must not contain NUL bytes")
        if not isinstance(self.content_type, str) or not self.content_type.strip():
            raise CredentialStorageError("secret content_type is required")

    @classmethod
    def from_text(
        cls,
        *,
        kind: CredentialSecretKind,
        value: str,
        content_type: str = "text/plain",
    ) -> "SecretMaterial":
        if not isinstance(value, str):
            raise CredentialStorageError("secret text material must be a string")
        return cls(kind=kind, value=value.encode("utf-8"), content_type=content_type)

    def reveal_for_runner(self) -> bytes:
        """Return secret bytes for the runner injector only."""
        return self.value

    def audit_view(self) -> dict[str, Any]:
        """Return non-secret metadata safe for logs/events/read models."""
        return {
            "kind": self.kind,
            "content_type": self.content_type,
            "present": True,
            "redacted": True,
        }


@dataclass(frozen=True)
class CredentialRecord:
    id: UUID
    program_id: UUID
    credential_ref: str
    identity_label: str
    secret_kind: CredentialSecretKind
    scope: Mapping[str, Any]
    status: CredentialStatus = "active"
    expires_at: datetime | None = None
    current_secret_version_id: UUID | None = None
    refresh_policy: Mapping[str, Any] = field(default_factory=dict)
    refresh_status: CredentialRefreshStatus = "not_configured"
    last_refreshed_at: datetime | None = None
    next_refresh_at: datetime | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=utcnow)
    updated_at: datetime = field(default_factory=utcnow)

    def __post_init__(self) -> None:
        _validate_uuid("id", self.id)
        _validate_uuid("program_id", self.program_id)
        object.__setattr__(
            self,
            "credential_ref",
            normalize_credential_ref("credential_ref", self.credential_ref),
        )
        object.__setattr__(self, "identity_label", _validate_label("identity_label", self.identity_label))
        _validate_secret_kind(self.secret_kind)
        _validate_status("status", self.status, CREDENTIAL_STATUSES)
        _validate_datetime("expires_at", self.expires_at, optional=True)
        _validate_uuid("current_secret_version_id", self.current_secret_version_id, optional=True)
        _validate_status("refresh_status", self.refresh_status, REFRESH_STATUSES)
        _validate_datetime("last_refreshed_at", self.last_refreshed_at, optional=True)
        _validate_datetime("next_refresh_at", self.next_refresh_at, optional=True)
        _validate_public_mapping("scope", self.scope)
        _validate_public_mapping("refresh_policy", self.refresh_policy)
        _validate_public_mapping("metadata", self.metadata)

    def is_active(self, *, now: datetime | None = None) -> bool:
        moment = now or utcnow()
        return self.status == "active" and (self.expires_at is None or self.expires_at > moment)

    def audit_view(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "program_id": str(self.program_id),
            "credential_ref": self.credential_ref,
            "identity_label": self.identity_label,
            "secret_kind": self.secret_kind,
            "scope": dict(self.scope),
            "status": self.status,
            "expires_at": _datetime_to_iso(self.expires_at),
            "current_secret_version_id": str(self.current_secret_version_id) if self.current_secret_version_id else None,
            "refresh_policy": dict(self.refresh_policy),
            "refresh_status": self.refresh_status,
            "last_refreshed_at": _datetime_to_iso(self.last_refreshed_at),
            "next_refresh_at": _datetime_to_iso(self.next_refresh_at),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class CredentialSecretVersion:
    id: UUID
    credential_id: UUID
    version: int
    secret_kind: CredentialSecretKind
    storage_backend: str
    status: CredentialSecretVersionStatus = "active"
    key_id: str | None = None
    external_secret_ref: str | None = None
    expires_at: datetime | None = None
    replaced_by_version_id: UUID | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=utcnow)

    def __post_init__(self) -> None:
        _validate_uuid("id", self.id)
        _validate_uuid("credential_id", self.credential_id)
        if not isinstance(self.version, int) or isinstance(self.version, bool) or self.version <= 0:
            raise CredentialStorageError("secret version must be a positive integer")
        _validate_secret_kind(self.secret_kind)
        _validate_status("status", self.status, SECRET_VERSION_STATUSES)
        object.__setattr__(self, "storage_backend", _validate_label("storage_backend", self.storage_backend))
        if self.key_id is not None:
            object.__setattr__(self, "key_id", _validate_label("key_id", self.key_id))
        if self.external_secret_ref is not None:
            object.__setattr__(
                self,
                "external_secret_ref",
                _validate_ref_text("external_secret_ref", self.external_secret_ref, max_length=500),
            )
        _validate_datetime("expires_at", self.expires_at, optional=True)
        _validate_uuid("replaced_by_version_id", self.replaced_by_version_id, optional=True)
        if self.replaced_by_version_id == self.id:
            raise CredentialStorageError("secret version cannot replace itself")
        _validate_public_mapping("metadata", self.metadata)

    def is_active(self, *, now: datetime | None = None) -> bool:
        moment = now or utcnow()
        return self.status == "active" and (self.expires_at is None or self.expires_at > moment)

    def audit_view(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "credential_id": str(self.credential_id),
            "version": self.version,
            "secret_kind": self.secret_kind,
            "storage_backend": self.storage_backend,
            "status": self.status,
            "key_id": self.key_id,
            "external_secret_ref": self.external_secret_ref,
            "expires_at": _datetime_to_iso(self.expires_at),
            "replaced_by_version_id": str(self.replaced_by_version_id) if self.replaced_by_version_id else None,
            "metadata": dict(self.metadata),
            "created_at": _datetime_to_iso(self.created_at),
        }


@dataclass(frozen=True)
class CredentialLeaseRequest:
    program_id: UUID
    credential_ref: str
    purpose: str
    target_scope: str
    capability: str
    ttl_seconds: int
    auth_injection: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        _validate_uuid("program_id", self.program_id)
        object.__setattr__(
            self,
            "credential_ref",
            normalize_credential_ref("credential_ref", self.credential_ref),
        )
        object.__setattr__(self, "purpose", _validate_label("purpose", self.purpose))
        object.__setattr__(self, "target_scope", _validate_ref_text("target_scope", self.target_scope, max_length=500))
        object.__setattr__(self, "capability", _validate_label("capability", self.capability))
        if not isinstance(self.ttl_seconds, int) or isinstance(self.ttl_seconds, bool):
            raise CredentialStorageError("lease ttl_seconds must be an integer")
        if self.ttl_seconds <= 0 or self.ttl_seconds > MAX_CREDENTIAL_LEASE_TTL_SECONDS:
            raise CredentialStorageError(
                f"lease ttl_seconds must be between 1 and {MAX_CREDENTIAL_LEASE_TTL_SECONDS}"
            )
        if self.auth_injection is not None:
            object.__setattr__(
                self,
                "auth_injection",
                normalize_auth_injection_spec("auth_injection", self.auth_injection),
            )


@dataclass(frozen=True)
class CredentialLease:
    id: UUID
    program_id: UUID
    credential_id: UUID
    secret_version_id: UUID
    credential_ref: str
    purpose: str
    target_scope: str
    capability: str
    auth_injection: Mapping[str, Any] | None
    status: CredentialLeaseStatus
    issued_at: datetime
    expires_at: datetime
    revoked_at: datetime | None = None
    audit_metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _validate_uuid("id", self.id)
        _validate_uuid("program_id", self.program_id)
        _validate_uuid("credential_id", self.credential_id)
        _validate_uuid("secret_version_id", self.secret_version_id)
        object.__setattr__(
            self,
            "credential_ref",
            normalize_credential_ref("credential_ref", self.credential_ref),
        )
        object.__setattr__(self, "purpose", _validate_label("purpose", self.purpose))
        object.__setattr__(self, "target_scope", _validate_ref_text("target_scope", self.target_scope, max_length=500))
        object.__setattr__(self, "capability", _validate_label("capability", self.capability))
        _validate_status("status", self.status, LEASE_STATUSES)
        _validate_datetime("issued_at", self.issued_at)
        _validate_datetime("expires_at", self.expires_at)
        _validate_datetime("revoked_at", self.revoked_at, optional=True)
        if self.expires_at <= self.issued_at:
            raise CredentialStorageError("lease expires_at must be after issued_at")
        if self.auth_injection is not None:
            object.__setattr__(
                self,
                "auth_injection",
                normalize_auth_injection_spec("auth_injection", self.auth_injection),
            )
        _validate_public_mapping("audit_metadata", self.audit_metadata)

    def is_usable(self, *, now: datetime | None = None) -> bool:
        moment = now or utcnow()
        return self.status == "issued" and self.revoked_at is None and self.expires_at > moment

    def audit_view(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "program_id": str(self.program_id),
            "credential_id": str(self.credential_id),
            "secret_version_id": str(self.secret_version_id),
            "credential_ref": self.credential_ref,
            "purpose": self.purpose,
            "target_scope": self.target_scope,
            "capability": self.capability,
            "auth_injection": dict(self.auth_injection) if self.auth_injection is not None else None,
            "status": self.status,
            "issued_at": _datetime_to_iso(self.issued_at),
            "expires_at": _datetime_to_iso(self.expires_at),
            "revoked_at": _datetime_to_iso(self.revoked_at),
            "audit_metadata": dict(self.audit_metadata),
            "redacted": True,
        }


class CredentialRegistry(Protocol):
    def register_credential(self, record: CredentialRecord) -> CredentialRecord: ...

    def update_credential(self, record: CredentialRecord) -> CredentialRecord: ...

    def get_credential(self, *, program_id: UUID, credential_ref: str) -> CredentialRecord | None: ...

    def list_credentials(self, *, program_id: UUID, limit: int, offset: int = 0) -> Sequence[CredentialRecord]: ...


class CredentialSecretStore(Protocol):
    def put_secret(
        self,
        *,
        credential: CredentialRecord,
        material: SecretMaterial,
        storage_backend: str,
        key_id: str | None = None,
        external_secret_ref: str | None = None,
        metadata: Mapping[str, Any] | None = None,
        expires_at: datetime | None = None,
    ) -> CredentialSecretVersion: ...

    def get_current_secret_version(self, credential: CredentialRecord) -> CredentialSecretVersion | None: ...

    def mark_secret_version_expired(self, secret_version_id: UUID) -> CredentialSecretVersion: ...

    def resolve_secret_for_lease(self, lease: CredentialLease) -> SecretMaterial: ...


class CredentialLeaseStore(Protocol):
    def issue_lease(self, request: CredentialLeaseRequest) -> CredentialLease: ...

    def revoke_lease(self, lease_id: UUID) -> CredentialLease: ...


def credential_record(
    *,
    program_id: UUID,
    credential_ref: str,
    identity_label: str,
    secret_kind: CredentialSecretKind,
    scope: Mapping[str, Any],
    expires_at: datetime | None = None,
    metadata: Mapping[str, Any] | None = None,
    status: CredentialStatus = "active",
    current_secret_version_id: UUID | None = None,
    refresh_policy: Mapping[str, Any] | None = None,
    refresh_status: CredentialRefreshStatus = "not_configured",
    last_refreshed_at: datetime | None = None,
    next_refresh_at: datetime | None = None,
    id: UUID | None = None,
) -> CredentialRecord:
    return CredentialRecord(
        id=id or uuid.uuid4(),
        program_id=program_id,
        credential_ref=credential_ref,
        identity_label=identity_label,
        secret_kind=secret_kind,
        scope=scope,
        status=status,
        expires_at=expires_at,
        current_secret_version_id=current_secret_version_id,
        refresh_policy=refresh_policy or {},
        refresh_status=refresh_status,
        last_refreshed_at=last_refreshed_at,
        next_refresh_at=next_refresh_at,
        metadata=metadata or {},
    )


def credential_lease_request(
    *,
    program_id: UUID,
    credential_ref: str,
    purpose: str,
    target_scope: str,
    capability: str,
    ttl_seconds: int,
    auth_injection: Mapping[str, Any] | None = None,
) -> CredentialLeaseRequest:
    return CredentialLeaseRequest(
        program_id=program_id,
        credential_ref=credential_ref,
        purpose=purpose,
        target_scope=target_scope,
        capability=capability,
        ttl_seconds=ttl_seconds,
        auth_injection=auth_injection,
    )


def _validate_uuid(name: str, value: UUID | None, *, optional: bool = False) -> None:
    if value is None and optional:
        return
    if not isinstance(value, UUID):
        raise CredentialStorageError(f"{name} must be UUID")


def _validate_secret_kind(value: str) -> None:
    if value not in SECRET_KINDS:
        raise CredentialStorageError("unsupported credential secret kind")


def _validate_status(name: str, value: str, allowed: frozenset[str]) -> None:
    if value not in allowed:
        raise CredentialStorageError(f"{name} is not valid")


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


def _validate_datetime(name: str, value: datetime | None, *, optional: bool = False) -> None:
    if value is None:
        if optional:
            return
        raise CredentialStorageError(f"{name} is required")
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise CredentialStorageError(f"{name} must be timezone-aware datetime")


def _validate_public_mapping(name: str, value: Mapping[str, Any] | Sequence[Any]) -> None:
    if not isinstance(value, Mapping):
        raise CredentialStorageError(f"{name} must be mapping")
    for key, item in value.items():
        if not isinstance(key, str) or not key.strip() or "\x00" in key:
            raise CredentialStorageError(f"{name} contains invalid key")
        try:
            reject_raw_credential_option(f"{name}.{key}", item)
        except ValueError as exc:
            raise CredentialStorageError(str(exc)) from exc


def _datetime_to_iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def lease_expiration(*, issued_at: datetime, ttl_seconds: int) -> datetime:
    _validate_datetime("issued_at", issued_at)
    if not isinstance(ttl_seconds, int) or isinstance(ttl_seconds, bool):
        raise CredentialStorageError("lease ttl_seconds must be an integer")
    if ttl_seconds <= 0 or ttl_seconds > MAX_CREDENTIAL_LEASE_TTL_SECONDS:
        raise CredentialStorageError(
            f"lease ttl_seconds must be between 1 and {MAX_CREDENTIAL_LEASE_TTL_SECONDS}"
        )
    return issued_at + timedelta(seconds=ttl_seconds)
