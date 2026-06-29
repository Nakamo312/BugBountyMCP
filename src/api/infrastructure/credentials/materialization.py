"""Runner-side credential materialization contracts.

This module converts already-leased ``SecretMaterial`` plus an
``auth_injection`` metadata spec into a runner-local plan. The plan may contain
secret values, so it must stay inside the execution boundary. Its repr and audit
views are intentionally redacted.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
import shlex
from typing import Any, Literal

from api.application.credential_refs import AuthInjectionSpec
from api.application.credential_storage import CredentialStorageError, SecretMaterial
from api.infrastructure.commands.command_boundary import redact_command_argv

MaterializationExposure = Literal["none", "argv", "env", "file", "request", "browser", "proxy"]

_FILE_MODE_BY_INJECTION_MODE = {
    "cookie_jar": "cookie_jar",
    "config_file": "config_file",
    "browser_context": "browser_context",
    "mtls_cert": "mtls_cert",
}
_FILE_SUFFIX_BY_ROLE = {
    "cookie_jar": ".cookies.txt",
    "config_file": ".conf",
    "browser_context": ".browser.json",
    "mtls_cert": ".pem",
}
_TEXT_SECRET_MODES = frozenset(
    {
        "header",
        "cookie",
        "env",
        "cli_flag",
        "cli_flag_equals",
        "proxy_auth",
    }
)


class CredentialMaterializationError(CredentialStorageError):
    """Raised when leased secret material cannot be materialized safely."""


@dataclass(frozen=True, slots=True)
class CredentialTempFileDescriptor:
    """Descriptor for a future temp file containing secret material.

    ``content`` is runner-only secret material and is deliberately excluded from
    repr/audit output. This descriptor does not write to disk; concrete runner
    adapters should create the file with mode 0600 and delete it after the run.
    """

    role: str
    content: bytes = field(repr=False)
    slot: str | None = None
    suffix: str = ".secret"
    file_mode: int = 0o600

    def __post_init__(self) -> None:
        if not isinstance(self.role, str) or not self.role.strip() or "\x00" in self.role:
            raise CredentialMaterializationError("temp file role is required")
        if self.slot is not None and (not isinstance(self.slot, str) or not self.slot.strip() or "\x00" in self.slot):
            raise CredentialMaterializationError("temp file slot is invalid")
        if not isinstance(self.content, bytes) or not self.content:
            raise CredentialMaterializationError("temp file content is required")
        if not isinstance(self.suffix, str) or not self.suffix.startswith(".") or "\x00" in self.suffix:
            raise CredentialMaterializationError("temp file suffix is invalid")
        if self.file_mode != 0o600:
            raise CredentialMaterializationError("secret temp files must use mode 0600")

    def audit_view(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "slot": self.slot,
            "suffix": self.suffix,
            "file_mode": oct(self.file_mode),
            "present": True,
            "redacted": True,
        }


@dataclass(frozen=True, slots=True)
class CredentialMaterializationPlan:
    """Runner-local materialization plan for one leased credential.

    Secret-bearing fields are excluded from repr. Use ``audit_view`` or
    ``redacted_command_for_log`` for logs/events/read models.
    """

    mode: str
    slot: str | None = None
    flag: str | None = None
    placement: str | None = None
    argv_additions: tuple[str, ...] = field(default_factory=tuple, repr=False)
    env_additions: Mapping[str, str] = field(default_factory=dict, repr=False)
    header_additions: Mapping[str, str] = field(default_factory=dict, repr=False)
    cookie_additions: Mapping[str, str] = field(default_factory=dict, repr=False)
    proxy_auth: str | None = field(default=None, repr=False)
    temp_files: tuple[CredentialTempFileDescriptor, ...] = ()
    exposures: tuple[MaterializationExposure, ...] = ()

    def __post_init__(self) -> None:
        for name, value in (("mode", self.mode),):
            if not isinstance(value, str) or not value.strip() or "\x00" in value:
                raise CredentialMaterializationError(f"{name} is required")
        if self.slot is not None and (not isinstance(self.slot, str) or not self.slot.strip() or "\x00" in self.slot):
            raise CredentialMaterializationError("slot is invalid")
        if self.flag is not None and (not isinstance(self.flag, str) or not self.flag.strip() or "\x00" in self.flag):
            raise CredentialMaterializationError("flag is invalid")
        object.__setattr__(self, "argv_additions", tuple(self.argv_additions))
        object.__setattr__(self, "env_additions", dict(self.env_additions))
        object.__setattr__(self, "header_additions", dict(self.header_additions))
        object.__setattr__(self, "cookie_additions", dict(self.cookie_additions))
        object.__setattr__(self, "temp_files", tuple(self.temp_files))
        object.__setattr__(self, "exposures", tuple(dict.fromkeys(self.exposures)))

    def apply_to_argv(self, base_argv: Sequence[str]) -> tuple[str, ...]:
        """Return runner argv with secret argv additions appended."""
        return tuple(base_argv) + self.argv_additions

    def apply_to_env(self, base_env: Mapping[str, str] | None = None) -> dict[str, str]:
        """Return runner env with secret env additions applied."""
        env = dict(base_env or {})
        env.update(self.env_additions)
        return env

    def redacted_argv(self, base_argv: Sequence[str] = ()) -> tuple[str, ...]:
        redacted = list(redact_command_argv(base_argv))
        if self.mode == "cli_flag" and self.flag:
            redacted.extend([self.flag, "<redacted>"])
        elif self.mode == "cli_flag_equals" and self.flag:
            redacted.append(f"{self.flag}=<redacted>")
        else:
            redacted.extend("<redacted>" for _ in self.argv_additions)
        return tuple(redacted)

    def redacted_command_for_log(self, base_argv: Sequence[str] = ()) -> str:
        return shlex.join(self.redacted_argv(base_argv))

    def audit_view(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "slot": self.slot,
            "flag": self.flag,
            "placement": self.placement,
            "exposures": list(self.exposures),
            "argv_additions": self._audit_argv_additions(),
            "env_additions": _redacted_names(self.env_additions),
            "header_additions": _redacted_names(self.header_additions),
            "cookie_additions": _redacted_names(self.cookie_additions),
            "proxy_auth": {"present": self.proxy_auth is not None, "redacted": self.proxy_auth is not None},
            "temp_files": [item.audit_view() for item in self.temp_files],
        }

    def _audit_argv_additions(self) -> list[dict[str, Any]]:
        if not self.argv_additions:
            return []
        if self.mode in {"cli_flag", "cli_flag_equals"}:
            return [
                {
                    "flag": self.flag,
                    "placement": self.placement,
                    "present": True,
                    "redacted": True,
                }
            ]
        return [{"present": True, "redacted": True} for _ in self.argv_additions]


def materialize_credential_for_runner(
    *,
    material: SecretMaterial,
    auth_injection: Mapping[str, Any] | AuthInjectionSpec,
) -> CredentialMaterializationPlan:
    """Build a runner-local secret materialization plan.

    The returned plan may carry secret values. It must not be persisted or shown
    to agents/read models. Use ``audit_view`` for safe diagnostics.
    """
    if not isinstance(material, SecretMaterial):
        raise CredentialMaterializationError("material must be SecretMaterial")
    spec = _normalize_spec(auth_injection)
    if spec.mode in _TEXT_SECRET_MODES:
        secret = _secret_text(material, mode=spec.mode)
    else:
        secret = None

    if spec.mode == "header":
        assert spec.slot is not None and secret is not None
        return CredentialMaterializationPlan(
            mode=spec.mode,
            slot=spec.slot,
            header_additions={spec.slot: secret},
            exposures=("request",),
        )
    if spec.mode == "cookie":
        assert spec.slot is not None and secret is not None
        return CredentialMaterializationPlan(
            mode=spec.mode,
            slot=spec.slot,
            cookie_additions={spec.slot: secret},
            exposures=("request",),
        )
    if spec.mode == "env":
        assert spec.slot is not None and secret is not None
        return CredentialMaterializationPlan(
            mode=spec.mode,
            slot=spec.slot,
            env_additions={spec.slot: secret},
            exposures=("env",),
        )
    if spec.mode == "cli_flag":
        assert spec.flag is not None and secret is not None
        return CredentialMaterializationPlan(
            mode=spec.mode,
            flag=spec.flag,
            placement=spec.placement,
            argv_additions=(spec.flag, secret),
            exposures=("argv",),
        )
    if spec.mode == "cli_flag_equals":
        assert spec.flag is not None and secret is not None
        return CredentialMaterializationPlan(
            mode=spec.mode,
            flag=spec.flag,
            placement=spec.placement,
            argv_additions=(f"{spec.flag}={secret}",),
            exposures=("argv",),
        )
    if spec.mode == "proxy_auth":
        assert secret is not None
        return CredentialMaterializationPlan(
            mode=spec.mode,
            slot=spec.slot,
            proxy_auth=secret,
            exposures=("proxy",),
        )
    if spec.mode in _FILE_MODE_BY_INJECTION_MODE:
        role = _FILE_MODE_BY_INJECTION_MODE[spec.mode]
        return CredentialMaterializationPlan(
            mode=spec.mode,
            slot=spec.slot,
            temp_files=(
                CredentialTempFileDescriptor(
                    role=role,
                    slot=spec.slot,
                    content=material.reveal_for_runner(),
                    suffix=_FILE_SUFFIX_BY_ROLE[role],
                ),
            ),
            exposures=("file", "browser") if spec.mode == "browser_context" else ("file",),
        )
    raise CredentialMaterializationError(f"unsupported auth injection mode: {spec.mode}")


def _normalize_spec(auth_injection: Mapping[str, Any] | AuthInjectionSpec) -> AuthInjectionSpec:
    if isinstance(auth_injection, AuthInjectionSpec):
        return auth_injection
    if not isinstance(auth_injection, Mapping):
        raise CredentialMaterializationError("auth_injection must be mapping")
    try:
        return AuthInjectionSpec.model_validate(dict(auth_injection))
    except ValueError as exc:
        raise CredentialMaterializationError(str(exc)) from exc


def _secret_text(material: SecretMaterial, *, mode: str) -> str:
    try:
        value = material.reveal_for_runner().decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CredentialMaterializationError(f"{mode} materialization requires UTF-8 text secret") from exc
    if not value:
        raise CredentialMaterializationError(f"{mode} materialization requires non-empty text secret")
    if "\x00" in value or "\r" in value or "\n" in value:
        raise CredentialMaterializationError(f"{mode} materialization secret must be a single-line value")
    return value


def _redacted_names(values: Mapping[str, str]) -> list[dict[str, Any]]:
    return [
        {"name": name, "present": True, "redacted": True}
        for name in sorted(values)
    ]
