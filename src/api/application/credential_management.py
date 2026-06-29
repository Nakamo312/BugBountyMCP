"""Credential management service for audit-safe registry and rotation APIs.

This service is the human/API boundary for creating stable credential refs and
rotating the secret versions behind them. It accepts raw secret material only in
rotation requests and returns only audit-safe metadata. Runner-side secret
resolution still goes through ``CredentialLeaseService``.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr

from api.application.credential_secret_versions import (
    CredentialRefreshPolicy,
    CredentialSecretVersionService,
)
from api.application.credential_storage import (
    CredentialRecord,
    CredentialRegistry,
    CredentialSecretKind,
    CredentialStorageError,
    SecretMaterial,
    credential_record,
)


class CredentialCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    program_id: UUID
    credential_ref: str
    identity_label: str
    secret_kind: CredentialSecretKind
    scope: dict[str, Any]
    expires_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CredentialSecretRotateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    program_id: UUID
    credential_ref: str
    secret_value: SecretStr = Field(repr=False)
    content_type: str = "text/plain"
    expires_at: datetime | None = None
    refresh_policy: dict[str, Any] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CredentialExpireCurrentSecretRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    program_id: UUID
    credential_ref: str


class CredentialMetadataReadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    program_id: UUID
    credential_ref: str


class CredentialManagementService:
    """Audit-safe boundary for registering credential refs and rotating secrets."""

    def __init__(
        self,
        *,
        registry: CredentialRegistry,
        secret_versions: CredentialSecretVersionService,
    ) -> None:
        self._registry = registry
        self._secret_versions = secret_versions

    def register_credential(self, request: CredentialCreateRequest) -> dict[str, Any]:
        if not isinstance(request, CredentialCreateRequest):
            raise CredentialStorageError("credential create request is required")
        record = credential_record(
            program_id=request.program_id,
            credential_ref=request.credential_ref,
            identity_label=request.identity_label,
            secret_kind=request.secret_kind,
            scope=request.scope,
            expires_at=request.expires_at,
            metadata=request.metadata,
        )
        return self._registry.register_credential(record).audit_view()

    def rotate_secret(self, request: CredentialSecretRotateRequest) -> dict[str, Any]:
        if not isinstance(request, CredentialSecretRotateRequest):
            raise CredentialStorageError("credential secret rotation request is required")
        credential = self._require_credential(
            program_id=request.program_id,
            credential_ref=request.credential_ref,
        )
        material = SecretMaterial.from_text(
            kind=credential.secret_kind,
            value=request.secret_value.get_secret_value(),
            content_type=request.content_type,
        )
        version = self._secret_versions.rotate_secret(
            program_id=request.program_id,
            credential_ref=request.credential_ref,
            material=material,
            expires_at=request.expires_at,
            refresh_policy=(
                CredentialRefreshPolicy(**request.refresh_policy)
                if request.refresh_policy is not None
                else None
            ),
            metadata=request.metadata,
        )
        credential_after = self._require_credential(
            program_id=request.program_id,
            credential_ref=request.credential_ref,
        )
        return {
            "credential": credential_after.audit_view(),
            "secret_version": self._secret_versions.audit_view(version),
            "secret_material": {"present": True, "redacted": True},
        }

    def mark_current_secret_expired(self, request: CredentialExpireCurrentSecretRequest) -> dict[str, Any]:
        if not isinstance(request, CredentialExpireCurrentSecretRequest):
            raise CredentialStorageError("credential expire request is required")
        version = self._secret_versions.mark_current_secret_expired(
            program_id=request.program_id,
            credential_ref=request.credential_ref,
        )
        credential = self._require_credential(
            program_id=request.program_id,
            credential_ref=request.credential_ref,
        )
        return {
            "credential": credential.audit_view(),
            "secret_version": self._secret_versions.audit_view(version),
        }

    def get_metadata(self, request: CredentialMetadataReadRequest) -> dict[str, Any]:
        credential = self._require_credential(
            program_id=request.program_id,
            credential_ref=request.credential_ref,
        )
        return credential.audit_view()

    def list_metadata(self, *, program_id: UUID, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        _validate_pagination(limit=limit, offset=offset)
        records = self._registry.list_credentials(program_id=program_id, limit=limit, offset=offset)
        return [record.audit_view() for record in records]

    def _require_credential(self, *, program_id: UUID, credential_ref: str) -> CredentialRecord:
        credential = self._registry.get_credential(program_id=program_id, credential_ref=credential_ref)
        if credential is None:
            raise CredentialStorageError("credential_ref is not registered")
        return credential


def _validate_pagination(*, limit: int, offset: int) -> None:
    if not isinstance(limit, int) or isinstance(limit, bool) or limit <= 0 or limit > 500:
        raise CredentialStorageError("limit must be between 1 and 500")
    if not isinstance(offset, int) or isinstance(offset, bool) or offset < 0:
        raise CredentialStorageError("offset must be non-negative")
