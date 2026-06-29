"""In-memory credential registry/secret/lease store for dev and tests.

This is not the production encrypted backend. It is a boundary implementation
that preserves the core rule: raw secret material is only returned by
``resolve_secret_for_lease`` after a valid, unexpired lease exists.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import uuid
from typing import Any, Mapping
from uuid import UUID

from sqlalchemy import func, insert, select, update
from sqlalchemy.exc import IntegrityError

from api.application.credential_refs import normalize_credential_ref
from api.application.credential_storage import (
    CredentialLease,
    CredentialLeaseRequest,
    CredentialRecord,
    CredentialSecretVersion,
    CredentialStorageError,
    SecretMaterial,
    lease_expiration,
    utcnow,
)
from api.infrastructure.adapters.orm import credential_leases, credential_refs, credential_secret_versions
from api.infrastructure.credentials.secret_codec import EncodedSecretPayload, SecretCodec



class InMemoryCredentialStore:
    """Dev/test implementation of registry, secret store, and lease store."""

    def __init__(self) -> None:
        self._credentials: dict[tuple[UUID, str], CredentialRecord] = {}
        self._secret_versions: dict[UUID, CredentialSecretVersion] = {}
        self._secrets: dict[UUID, SecretMaterial] = {}
        self._active_version_by_credential: dict[UUID, UUID] = {}
        self._leases: dict[UUID, CredentialLease] = {}

    def register_credential(self, record: CredentialRecord) -> CredentialRecord:
        key = (record.program_id, record.credential_ref)
        if key in self._credentials:
            raise CredentialStorageError("credential_ref already exists for program")
        self._credentials[key] = record
        return record

    def update_credential(self, record: CredentialRecord) -> CredentialRecord:
        key = (record.program_id, record.credential_ref)
        if key not in self._credentials:
            raise CredentialStorageError("credential_ref is not registered")
        self._credentials[key] = record
        return record

    def get_credential(self, *, program_id: UUID, credential_ref: str) -> CredentialRecord | None:
        normalized = normalize_credential_ref("credential_ref", credential_ref)
        return self._credentials.get((program_id, normalized))

    def list_credentials(self, *, program_id: UUID, limit: int, offset: int = 0) -> list[CredentialRecord]:
        _validate_list_bounds(limit=limit, offset=offset)
        items = [
            record
            for (record_program_id, _), record in sorted(
                self._credentials.items(),
                key=lambda item: (item[1].identity_label, item[1].credential_ref),
            )
            if record_program_id == program_id
        ]
        return items[offset : offset + limit]

    def put_secret(
        self,
        *,
        credential: CredentialRecord,
        material: SecretMaterial,
        storage_backend: str = "memory_test",
        key_id: str | None = None,
        external_secret_ref: str | None = None,
        metadata: Mapping[str, Any] | None = None,
        expires_at: Any | None = None,
    ) -> CredentialSecretVersion:
        if material.kind != credential.secret_kind:
            raise CredentialStorageError("secret material kind does not match credential")
        if not credential.is_active():
            raise CredentialStorageError("cannot attach secret to inactive credential")
        if expires_at is not None and expires_at <= utcnow():
            raise CredentialStorageError("secret version expires_at must be in the future")
        stored_credential = self.get_credential(program_id=credential.program_id, credential_ref=credential.credential_ref)
        if stored_credential is None:
            self.register_credential(credential)
            stored_credential = credential

        next_version = 1 + sum(
            1
            for version in self._secret_versions.values()
            if version.credential_id == credential.id
        )
        secret_version = CredentialSecretVersion(
            id=uuid.uuid4(),
            credential_id=credential.id,
            version=next_version,
            secret_kind=credential.secret_kind,
            storage_backend=storage_backend,
            key_id=key_id,
            external_secret_ref=external_secret_ref,
            expires_at=expires_at,
            metadata=metadata or {},
        )
        previous_id = self._active_version_by_credential.get(credential.id)
        if previous_id is not None:
            previous = self._secret_versions[previous_id]
            self._secret_versions[previous_id] = replace(
                previous,
                status="retired",
                replaced_by_version_id=secret_version.id,
            )
        self._secret_versions[secret_version.id] = secret_version
        self._secrets[secret_version.id] = material
        self._active_version_by_credential[credential.id] = secret_version.id
        self._credentials[(credential.program_id, credential.credential_ref)] = replace(
            stored_credential,
            current_secret_version_id=secret_version.id,
            refresh_status="fresh",
            last_refreshed_at=utcnow(),
            updated_at=utcnow(),
        )
        return secret_version

    def get_current_secret_version(self, credential: CredentialRecord) -> CredentialSecretVersion | None:
        secret_version_id = self._active_version_by_credential.get(credential.id)
        if secret_version_id is None:
            stored = self.get_credential(program_id=credential.program_id, credential_ref=credential.credential_ref)
            secret_version_id = stored.current_secret_version_id if stored is not None else None
        if secret_version_id is None:
            return None
        return self._secret_versions.get(secret_version_id)

    def mark_secret_version_expired(self, secret_version_id: UUID) -> CredentialSecretVersion:
        version = self._secret_versions.get(secret_version_id)
        if version is None:
            raise CredentialStorageError("secret version does not exist")
        expired = replace(version, status="expired")
        self._secret_versions[secret_version_id] = expired
        if self._active_version_by_credential.get(version.credential_id) == secret_version_id:
            del self._active_version_by_credential[version.credential_id]
            for key, credential in list(self._credentials.items()):
                if credential.id == version.credential_id:
                    self._credentials[key] = replace(
                        credential,
                        current_secret_version_id=None,
                        refresh_status="refresh_due",
                        updated_at=utcnow(),
                    )
                    break
        return expired

    def issue_lease(self, request: CredentialLeaseRequest) -> CredentialLease:
        credential = self.get_credential(
            program_id=request.program_id,
            credential_ref=request.credential_ref,
        )
        if credential is None:
            raise CredentialStorageError("credential_ref is not registered")
        if not credential.is_active():
            raise CredentialStorageError("credential_ref is not active")
        secret_version_id = self._active_version_by_credential.get(credential.id)
        if secret_version_id is None:
            raise CredentialStorageError("credential_ref has no active secret version")
        secret_version = self._secret_versions[secret_version_id]
        if not secret_version.is_active():
            if secret_version.status == "active":
                self.mark_secret_version_expired(secret_version.id)
            raise CredentialStorageError("credential_ref has no active secret version")

        issued_at = utcnow()
        lease = CredentialLease(
            id=uuid.uuid4(),
            program_id=request.program_id,
            credential_id=credential.id,
            secret_version_id=secret_version.id,
            credential_ref=credential.credential_ref,
            purpose=request.purpose,
            target_scope=request.target_scope,
            capability=request.capability,
            auth_injection=request.auth_injection,
            status="issued",
            issued_at=issued_at,
            expires_at=lease_expiration(issued_at=issued_at, ttl_seconds=request.ttl_seconds),
            audit_metadata={
                "identity_label": credential.identity_label,
                "secret_kind": credential.secret_kind,
                "storage_backend": secret_version.storage_backend,
            },
        )
        self._leases[lease.id] = lease
        return lease

    def revoke_lease(self, lease_id: UUID) -> CredentialLease:
        lease = self._leases.get(lease_id)
        if lease is None:
            raise CredentialStorageError("lease does not exist")
        revoked = replace(lease, status="revoked", revoked_at=utcnow())
        self._leases[lease_id] = revoked
        return revoked

    def resolve_secret_for_lease(self, lease: CredentialLease) -> SecretMaterial:
        stored = self._leases.get(lease.id)
        if stored is None:
            raise CredentialStorageError("lease does not exist")
        if stored != lease:
            raise CredentialStorageError("lease metadata mismatch")
        if not stored.is_usable():
            raise CredentialStorageError("lease is not usable")
        material = self._secrets.get(stored.secret_version_id)
        if material is None:
            raise CredentialStorageError("lease secret material is unavailable")
        return material

class PostgresCredentialStore:
    """SQLAlchemy Core credential registry/secret/lease store.

    The class is named for the production backend, but it uses SQLAlchemy Core
    statements and is intentionally testable against SQLite. It does not choose
    a default secret codec: composition must provide an encrypted/vault codec in
    production, or ``DevOnlyPlaintextSecretCodec`` explicitly in tests/dev.
    """

    def __init__(self, connection, *, secret_codec: SecretCodec) -> None:
        if secret_codec is None:
            raise CredentialStorageError("PostgresCredentialStore requires an explicit secret codec")
        self._connection = connection
        self._codec = secret_codec

    def register_credential(self, record: CredentialRecord) -> CredentialRecord:
        try:
            self._connection.execute(
                insert(credential_refs).values(
                    id=record.id,
                    program_id=record.program_id,
                    credential_ref=record.credential_ref,
                    identity_label=record.identity_label,
                    secret_kind=record.secret_kind,
                    scope_json=dict(record.scope),
                    status=record.status,
                    expires_at=record.expires_at,
                    current_secret_version_id=record.current_secret_version_id,
                    refresh_policy_json=dict(record.refresh_policy),
                    refresh_status=record.refresh_status,
                    last_refreshed_at=record.last_refreshed_at,
                    next_refresh_at=record.next_refresh_at,
                    metadata_json=dict(record.metadata),
                    created_at=record.created_at,
                    updated_at=record.updated_at,
                )
            )
        except IntegrityError as exc:
            raise CredentialStorageError("credential_ref already exists for program") from exc
        return record

    def update_credential(self, record: CredentialRecord) -> CredentialRecord:
        result = self._connection.execute(
            update(credential_refs)
            .where(credential_refs.c.id == record.id)
            .values(
                program_id=record.program_id,
                credential_ref=record.credential_ref,
                identity_label=record.identity_label,
                secret_kind=record.secret_kind,
                scope_json=dict(record.scope),
                status=record.status,
                expires_at=record.expires_at,
                current_secret_version_id=record.current_secret_version_id,
                refresh_policy_json=dict(record.refresh_policy),
                refresh_status=record.refresh_status,
                last_refreshed_at=record.last_refreshed_at,
                next_refresh_at=record.next_refresh_at,
                metadata_json=dict(record.metadata),
                updated_at=record.updated_at,
            )
        )
        if result.rowcount == 0:
            raise CredentialStorageError("credential_ref is not registered")
        return record

    def get_credential(self, *, program_id: UUID, credential_ref: str) -> CredentialRecord | None:
        normalized = normalize_credential_ref("credential_ref", credential_ref)
        row = self._connection.execute(
            select(credential_refs).where(
                credential_refs.c.program_id == program_id,
                credential_refs.c.credential_ref == normalized,
            )
        ).mappings().one_or_none()
        return _credential_record_from_row(row) if row is not None else None

    def list_credentials(self, *, program_id: UUID, limit: int, offset: int = 0) -> list[CredentialRecord]:
        _validate_list_bounds(limit=limit, offset=offset)
        rows = self._connection.execute(
            select(credential_refs)
            .where(credential_refs.c.program_id == program_id)
            .order_by(credential_refs.c.identity_label, credential_refs.c.credential_ref)
            .limit(limit)
            .offset(offset)
        ).mappings().all()
        return [_credential_record_from_row(row) for row in rows]

    def put_secret(
        self,
        *,
        credential: CredentialRecord,
        material: SecretMaterial,
        storage_backend: str = "memory_test",
        key_id: str | None = None,
        external_secret_ref: str | None = None,
        metadata: Mapping[str, Any] | None = None,
        expires_at: Any | None = None,
    ) -> CredentialSecretVersion:
        if material.kind != credential.secret_kind:
            raise CredentialStorageError("secret material kind does not match credential")
        if not credential.is_active():
            raise CredentialStorageError("cannot attach secret to inactive credential")
        if expires_at is not None and expires_at <= utcnow():
            raise CredentialStorageError("secret version expires_at must be in the future")

        stored_credential = self.get_credential(program_id=credential.program_id, credential_ref=credential.credential_ref)
        if stored_credential is None:
            self.register_credential(credential)
            stored_credential = credential

        if storage_backend not in {"memory_test", self._codec.storage_backend}:
            raise CredentialStorageError("storage_backend does not match configured secret codec")
        encoded = self._codec.encode(material)
        if encoded.storage_backend != self._codec.storage_backend:
            raise CredentialStorageError("secret codec returned unexpected storage backend")
        merged_metadata = {**dict(encoded.metadata), **dict(metadata or {})}

        next_version_value = self._connection.execute(
            select(func.coalesce(func.max(credential_secret_versions.c.version), 0) + 1).where(
                credential_secret_versions.c.credential_ref_id == stored_credential.id
            )
        ).scalar_one()
        secret_version = CredentialSecretVersion(
            id=uuid.uuid4(),
            credential_id=stored_credential.id,
            version=int(next_version_value),
            secret_kind=stored_credential.secret_kind,
            storage_backend=encoded.storage_backend,
            key_id=key_id or encoded.key_id,
            external_secret_ref=external_secret_ref or encoded.external_secret_ref,
            expires_at=expires_at,
            metadata=merged_metadata,
        )

        previous_id = stored_credential.current_secret_version_id
        self._connection.execute(
            insert(credential_secret_versions).values(
                id=secret_version.id,
                credential_ref_id=secret_version.credential_id,
                version=secret_version.version,
                secret_kind=secret_version.secret_kind,
                storage_backend=secret_version.storage_backend,
                ciphertext=encoded.ciphertext,
                nonce=encoded.nonce,
                key_id=secret_version.key_id,
                external_secret_ref=secret_version.external_secret_ref,
                status=secret_version.status,
                expires_at=secret_version.expires_at,
                replaced_by_version_id=secret_version.replaced_by_version_id,
                metadata_json=dict(secret_version.metadata),
                created_at=secret_version.created_at,
            )
        )
        if previous_id is not None:
            self._connection.execute(
                update(credential_secret_versions)
                .where(credential_secret_versions.c.id == previous_id)
                .values(status="retired", replaced_by_version_id=secret_version.id)
            )
        self._connection.execute(
            update(credential_refs)
            .where(credential_refs.c.id == stored_credential.id)
            .values(
                current_secret_version_id=secret_version.id,
                refresh_status="fresh",
                last_refreshed_at=utcnow(),
                updated_at=utcnow(),
            )
        )
        return secret_version

    def get_current_secret_version(self, credential: CredentialRecord) -> CredentialSecretVersion | None:
        stored = self.get_credential(program_id=credential.program_id, credential_ref=credential.credential_ref)
        secret_version_id = stored.current_secret_version_id if stored is not None else credential.current_secret_version_id
        if secret_version_id is None:
            return None
        return self._get_secret_version(secret_version_id)

    def mark_secret_version_expired(self, secret_version_id: UUID) -> CredentialSecretVersion:
        version = self._get_secret_version(secret_version_id)
        if version is None:
            raise CredentialStorageError("secret version does not exist")
        expired = replace(version, status="expired")
        self._connection.execute(
            update(credential_secret_versions)
            .where(credential_secret_versions.c.id == secret_version_id)
            .values(status="expired")
        )
        credential_row = self._connection.execute(
            select(credential_refs).where(credential_refs.c.id == version.credential_id)
        ).mappings().one_or_none()
        if credential_row is not None and credential_row["current_secret_version_id"] == secret_version_id:
            self._connection.execute(
                update(credential_refs)
                .where(credential_refs.c.id == version.credential_id)
                .values(
                    current_secret_version_id=None,
                    refresh_status="refresh_due",
                    updated_at=utcnow(),
                )
            )
        return expired

    def issue_lease(self, request: CredentialLeaseRequest) -> CredentialLease:
        credential = self.get_credential(program_id=request.program_id, credential_ref=request.credential_ref)
        if credential is None:
            raise CredentialStorageError("credential_ref is not registered")
        if not credential.is_active():
            raise CredentialStorageError("credential_ref is not active")
        secret_version = self.get_current_secret_version(credential)
        if secret_version is None or not secret_version.is_active():
            if secret_version is not None and secret_version.status == "active":
                self.mark_secret_version_expired(secret_version.id)
            raise CredentialStorageError("credential_ref has no active secret version")

        issued_at = utcnow()
        lease = CredentialLease(
            id=uuid.uuid4(),
            program_id=request.program_id,
            credential_id=credential.id,
            secret_version_id=secret_version.id,
            credential_ref=credential.credential_ref,
            purpose=request.purpose,
            target_scope=request.target_scope,
            capability=request.capability,
            auth_injection=request.auth_injection,
            status="issued",
            issued_at=issued_at,
            expires_at=lease_expiration(issued_at=issued_at, ttl_seconds=request.ttl_seconds),
            audit_metadata={
                "identity_label": credential.identity_label,
                "secret_kind": credential.secret_kind,
                "storage_backend": secret_version.storage_backend,
            },
        )
        self._connection.execute(
            insert(credential_leases).values(
                id=lease.id,
                program_id=lease.program_id,
                credential_ref_id=lease.credential_id,
                secret_version_id=lease.secret_version_id,
                purpose=lease.purpose,
                capability=lease.capability,
                target_scope=lease.target_scope,
                auth_injection_json=dict(lease.auth_injection) if lease.auth_injection is not None else {},
                status=lease.status,
                issued_at=lease.issued_at,
                expires_at=lease.expires_at,
                revoked_at=lease.revoked_at,
                audit_json=dict(lease.audit_metadata),
                created_at=lease.issued_at,
            )
        )
        return lease

    def revoke_lease(self, lease_id: UUID) -> CredentialLease:
        lease = self._get_lease(lease_id)
        if lease is None:
            raise CredentialStorageError("lease does not exist")
        revoked = replace(lease, status="revoked", revoked_at=utcnow())
        self._connection.execute(
            update(credential_leases)
            .where(credential_leases.c.id == lease_id)
            .values(status="revoked", revoked_at=revoked.revoked_at)
        )
        return revoked

    def resolve_secret_for_lease(self, lease: CredentialLease) -> SecretMaterial:
        stored = self._get_lease(lease.id)
        if stored is None:
            raise CredentialStorageError("lease does not exist")
        if (
            stored.program_id != lease.program_id
            or stored.credential_id != lease.credential_id
            or stored.secret_version_id != lease.secret_version_id
            or stored.purpose != lease.purpose
            or stored.capability != lease.capability
            or stored.target_scope != lease.target_scope
        ):
            raise CredentialStorageError("lease metadata mismatch")
        if not stored.is_usable():
            raise CredentialStorageError("lease is not usable")
        version_row = self._connection.execute(
            select(credential_secret_versions).where(
                credential_secret_versions.c.id == stored.secret_version_id,
            )
        ).mappings().one_or_none()
        if version_row is None:
            raise CredentialStorageError("lease secret version is unavailable")
        payload = EncodedSecretPayload(
            storage_backend=version_row["storage_backend"],
            ciphertext=version_row["ciphertext"],
            nonce=version_row["nonce"],
            key_id=version_row["key_id"],
            external_secret_ref=version_row["external_secret_ref"],
            metadata=version_row["metadata_json"] or {},
        )
        return self._codec.decode(secret_kind=version_row["secret_kind"], payload=payload)

    def _get_secret_version(self, secret_version_id: UUID) -> CredentialSecretVersion | None:
        row = self._connection.execute(
            select(credential_secret_versions).where(credential_secret_versions.c.id == secret_version_id)
        ).mappings().one_or_none()
        return _secret_version_from_row(row) if row is not None else None

    def _get_lease(self, lease_id: UUID) -> CredentialLease | None:
        row = self._connection.execute(
            select(credential_leases, credential_refs.c.credential_ref)
            .select_from(
                credential_leases.join(
                    credential_refs,
                    credential_refs.c.id == credential_leases.c.credential_ref_id,
                )
            )
            .where(credential_leases.c.id == lease_id)
        ).mappings().one_or_none()
        return _lease_from_row(row) if row is not None else None


def _validate_list_bounds(*, limit: int, offset: int) -> None:
    if not isinstance(limit, int) or isinstance(limit, bool) or limit <= 0 or limit > 500:
        raise CredentialStorageError("limit must be between 1 and 500")
    if not isinstance(offset, int) or isinstance(offset, bool) or offset < 0:
        raise CredentialStorageError("offset must be non-negative")


def _credential_record_from_row(row: Mapping[str, Any]) -> CredentialRecord:
    return CredentialRecord(
        id=row["id"],
        program_id=row["program_id"],
        credential_ref=row["credential_ref"],
        identity_label=row["identity_label"],
        secret_kind=row["secret_kind"],
        scope=row["scope_json"] or {},
        status=row["status"],
        expires_at=_aware(row["expires_at"]),
        current_secret_version_id=row["current_secret_version_id"],
        refresh_policy=row["refresh_policy_json"] or {},
        refresh_status=row["refresh_status"],
        last_refreshed_at=_aware(row["last_refreshed_at"]),
        next_refresh_at=_aware(row["next_refresh_at"]),
        metadata=row["metadata_json"] or {},
        created_at=_aware(row["created_at"]),
        updated_at=_aware(row["updated_at"]),
    )


def _secret_version_from_row(row: Mapping[str, Any]) -> CredentialSecretVersion:
    return CredentialSecretVersion(
        id=row["id"],
        credential_id=row["credential_ref_id"],
        version=row["version"],
        secret_kind=row["secret_kind"],
        storage_backend=row["storage_backend"],
        status=row["status"],
        key_id=row["key_id"],
        external_secret_ref=row["external_secret_ref"],
        expires_at=_aware(row["expires_at"]),
        replaced_by_version_id=row["replaced_by_version_id"],
        metadata=row["metadata_json"] or {},
        created_at=_aware(row["created_at"]),
    )


def _lease_from_row(row: Mapping[str, Any]) -> CredentialLease:
    auth_injection = row["auth_injection_json"] or None
    return CredentialLease(
        id=row["id"],
        program_id=row["program_id"],
        credential_id=row["credential_ref_id"],
        secret_version_id=row["secret_version_id"],
        credential_ref=row["credential_ref"],
        purpose=row["purpose"],
        target_scope=row["target_scope"],
        capability=row["capability"],
        auth_injection=auth_injection,
        status=row["status"],
        issued_at=_aware(row["issued_at"]),
        expires_at=_aware(row["expires_at"]),
        revoked_at=_aware(row["revoked_at"]),
        audit_metadata=row["audit_json"] or {},
    )


def _aware(value: Any) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, datetime):
        raise CredentialStorageError("stored datetime value is invalid")
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value
