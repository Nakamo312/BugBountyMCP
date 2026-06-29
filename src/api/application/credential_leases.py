"""Application-level credential lease service.

The service is the public boundary for issuing short-lived access to secret
material. Stores may retain defensive validation, but callers should not issue
or resolve leases by talking to storage backends directly.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping
from uuid import UUID

from api.application.credential_refs import CLI_AUTH_INJECTION_MODES, reject_raw_credential_option
from api.application.credential_storage import (
    MAX_CREDENTIAL_LEASE_TTL_SECONDS,
    CredentialLease,
    CredentialLeaseRequest,
    CredentialLeaseStore,
    CredentialRegistry,
    CredentialSecretStore,
    CredentialStorageError,
    SecretMaterial,
    credential_lease_request,
)


@dataclass(frozen=True)
class CredentialLeasePolicy:
    """Hard ceilings for credential lease issuance."""

    default_ttl_seconds: int = 5 * 60
    max_ttl_seconds: int = MAX_CREDENTIAL_LEASE_TTL_SECONDS
    allow_argv_exposure: bool = False
    allowed_cli_flags: tuple[str, ...] = ()
    audit_context: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.default_ttl_seconds, int) or isinstance(self.default_ttl_seconds, bool):
            raise CredentialStorageError("default lease ttl must be an integer")
        if not isinstance(self.max_ttl_seconds, int) or isinstance(self.max_ttl_seconds, bool):
            raise CredentialStorageError("max lease ttl must be an integer")
        if self.default_ttl_seconds <= 0:
            raise CredentialStorageError("default lease ttl must be positive")
        if self.max_ttl_seconds <= 0 or self.max_ttl_seconds > MAX_CREDENTIAL_LEASE_TTL_SECONDS:
            raise CredentialStorageError(
                f"max lease ttl must be between 1 and {MAX_CREDENTIAL_LEASE_TTL_SECONDS}"
            )
        if self.default_ttl_seconds > self.max_ttl_seconds:
            raise CredentialStorageError("default lease ttl cannot exceed max lease ttl")
        if not isinstance(self.allowed_cli_flags, tuple):
            object.__setattr__(self, "allowed_cli_flags", tuple(self.allowed_cli_flags))
        if not isinstance(self.allow_argv_exposure, bool):
            raise CredentialStorageError("allow_argv_exposure must be boolean")
        if self.allowed_cli_flags and not self.allow_argv_exposure:
            raise CredentialStorageError("allowed_cli_flags require allow_argv_exposure")
        _validate_public_mapping("audit_context", self.audit_context)


class CredentialLeaseService:
    """Issue and resolve credential leases through one application boundary."""

    def __init__(
        self,
        *,
        registry: CredentialRegistry,
        secret_store: CredentialSecretStore,
        lease_store: CredentialLeaseStore,
        policy: CredentialLeasePolicy | None = None,
    ) -> None:
        self._registry = registry
        self._secret_store = secret_store
        self._lease_store = lease_store
        self._policy = policy or CredentialLeasePolicy()

    @property
    def policy(self) -> CredentialLeasePolicy:
        return self._policy

    def request_lease(
        self,
        *,
        program_id: UUID,
        credential_ref: str,
        purpose: str,
        target_scope: str,
        capability: str,
        ttl_seconds: int | None = None,
        auth_injection: Mapping[str, Any] | None = None,
    ) -> CredentialLease:
        """Build and issue a bounded lease request.

        Secret bytes are not returned here. A separate runner-side resolve call
        must present the issued lease and expected action context.
        """
        request = credential_lease_request(
            program_id=program_id,
            credential_ref=credential_ref,
            purpose=purpose,
            target_scope=target_scope,
            capability=capability,
            ttl_seconds=self._normalize_ttl(ttl_seconds),
            auth_injection=auth_injection,
        )
        return self.issue_lease(request)

    def issue_lease(self, request: CredentialLeaseRequest) -> CredentialLease:
        """Issue a lease after applying service-level policy."""
        if not isinstance(request, CredentialLeaseRequest):
            raise CredentialStorageError("lease request must be CredentialLeaseRequest")
        self._validate_request_policy(request)
        credential = self._registry.get_credential(
            program_id=request.program_id,
            credential_ref=request.credential_ref,
        )
        if credential is None:
            raise CredentialStorageError("credential_ref is not registered")
        if not credential.is_active():
            raise CredentialStorageError("credential_ref is not active")
        if credential.secret_kind == "cookie" and request.auth_injection is not None:
            mode = request.auth_injection.get("mode")
            cookie_modes = {
                "cookie",
                "cookie_jar",
                "browser_context",
                "header",
                "env",
                "config_file",
                "cli_flag",
                "cli_flag_equals",
            }
            if mode not in cookie_modes:
                raise CredentialStorageError("cookie credential cannot use requested auth injection mode")
        return self._lease_store.issue_lease(request)

    def revoke_lease(self, lease_id: UUID) -> CredentialLease:
        return self._lease_store.revoke_lease(lease_id)

    def resolve_secret_for_runner(
        self,
        lease: CredentialLease,
        *,
        purpose: str,
        capability: str,
        target_scope: str | None = None,
    ) -> SecretMaterial:
        """Resolve secret material for the runner injector only.

        The caller must prove it is resolving for the same action context that
        obtained the lease. This prevents accidental reuse across capabilities
        or authz comparison branches.
        """
        if not isinstance(lease, CredentialLease):
            raise CredentialStorageError("lease must be CredentialLease")
        if lease.purpose != purpose:
            raise CredentialStorageError("lease purpose mismatch")
        if lease.capability != capability:
            raise CredentialStorageError("lease capability mismatch")
        if target_scope is not None and lease.target_scope != target_scope:
            raise CredentialStorageError("lease target_scope mismatch")
        if not lease.is_usable():
            raise CredentialStorageError("lease is not usable")
        return self._secret_store.resolve_secret_for_lease(lease)

    def audit_view(self, lease: CredentialLease) -> dict[str, Any]:
        """Return a lease view safe for logs/events/read models."""
        view = lease.audit_view()
        view["lease_service"] = "credential_lease_service"
        return view

    def _normalize_ttl(self, ttl_seconds: int | None) -> int:
        if ttl_seconds is None:
            return self._policy.default_ttl_seconds
        if not isinstance(ttl_seconds, int) or isinstance(ttl_seconds, bool):
            raise CredentialStorageError("lease ttl_seconds must be an integer")
        return ttl_seconds

    def _validate_request_policy(self, request: CredentialLeaseRequest) -> None:
        if request.ttl_seconds > self._policy.max_ttl_seconds:
            raise CredentialStorageError("lease ttl_seconds exceeds credential lease policy")
        if request.auth_injection is not None:
            mode = request.auth_injection.get("mode")
            if mode in CLI_AUTH_INJECTION_MODES:
                if not self._policy.allow_argv_exposure:
                    raise CredentialStorageError("CLI auth injection requires explicit argv exposure policy")
                flag = request.auth_injection.get("flag")
                if flag not in self._policy.allowed_cli_flags:
                    raise CredentialStorageError("CLI auth injection flag is not allowed by lease policy")


# Keep this local to avoid exporting storage internals as public service API.
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
