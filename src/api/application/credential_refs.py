"""Typed credential-reference contracts for authenticated actions.

This module intentionally models only opaque references and injection intent.
It does not resolve, store, decrypt, or materialize secret values.
"""
from __future__ import annotations

import re
from typing import Any, Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


CredentialInjectionMode = Literal[
    "header",
    "cookie",
    "cookie_jar",
    "env",
    "cli_flag",
    "cli_flag_equals",
    "config_file",
    "browser_context",
    "mtls_cert",
    "proxy_auth",
]
CredentialInjectionPlacement = Literal[
    "separate_arg",
    "equals",
]

AUTH_INJECTION_MODES = frozenset(
    {
        "header",
        "cookie",
        "cookie_jar",
        "env",
        "cli_flag",
        "cli_flag_equals",
        "config_file",
        "browser_context",
        "mtls_cert",
        "proxy_auth",
    }
)
CLI_AUTH_INJECTION_MODES = frozenset({"cli_flag", "cli_flag_equals"})

_CREDENTIAL_REF_RE = re.compile(r"^credref:[A-Za-z0-9][A-Za-z0-9._:/@-]{0,247}$")
_HEADER_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9!#$%&'*+.^_`|~-]{0,127}$")
_ENV_NAME_RE = re.compile(r"^[A-Z_][A-Z0-9_]{0,127}$")
_SLOT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@-]{0,127}$")
_CLI_FLAG_RE = re.compile(r"^-{1,2}[A-Za-z][A-Za-z0-9._-]{0,127}$")

_RAW_CREDENTIAL_OPTION_KEYS = frozenset(
    {
        "api-key",
        "api_key",
        "apikey",
        "auth",
        "authorization",
        "bearer",
        "cookie",
        "cookies",
        "header",
        "headers",
        "password",
        "secret",
        "session",
        "token",
    }
)
_RAW_CREDENTIAL_VALUE_PATTERNS = (
    re.compile(r"(?i)\bauthorization\s*:\s*(?:bearer\s+)?\S+"),
    re.compile(r"(?i)\bproxy-authorization\s*:\s*(?:bearer\s+)?\S+"),
    re.compile(r"(?i)\bcookie\s*:\s*\S+"),
    re.compile(r"(?i)\b(?:access_token|api[_-]?key|apikey|refresh_token|sessionid|token)\s*=\s*\S+"),
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/-]+=*"),
)


class AuthInjectionSpec(BaseModel):
    """How a future lease injector should materialize a credential for a runner.

    The spec contains placement metadata only. It never contains the token,
    cookie, header value, API key, or session payload.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    mode: CredentialInjectionMode
    slot: str | None = Field(default=None, min_length=1, max_length=128)
    flag: str | None = Field(default=None, min_length=2, max_length=129)
    placement: CredentialInjectionPlacement | None = None

    @model_validator(mode="before")
    @classmethod
    def normalize_slot_aliases(cls, data: Any) -> Any:
        if not isinstance(data, Mapping):
            return data
        payload = dict(data)
        if "slot" not in payload:
            for alias in (
                "header_name",
                "cookie_name",
                "env_name",
                "config_key",
                "cookie_jar_name",
                "browser_context_name",
            ):
                if alias in payload:
                    payload["slot"] = payload.pop(alias)
                    break
        mode = payload.get("mode")
        if mode == "cli_flag" and "placement" not in payload:
            payload["placement"] = "separate_arg"
        if mode == "cli_flag_equals" and "placement" not in payload:
            payload["placement"] = "equals"
        return payload

    @field_validator("slot")
    @classmethod
    def slot_must_be_bounded_metadata(cls, value: str | None) -> str | None:
        if value is None:
            return value
        if "\x00" in value or "\n" in value or "\r" in value:
            raise ValueError("slot must not contain control characters")
        return value

    @field_validator("flag")
    @classmethod
    def flag_must_be_cli_metadata(cls, value: str | None) -> str | None:
        if value is None:
            return value
        if "\x00" in value or "\n" in value or "\r" in value:
            raise ValueError("flag must not contain control characters")
        if not _CLI_FLAG_RE.fullmatch(value):
            raise ValueError("flag must be a bounded CLI flag name")
        return value

    @model_validator(mode="after")
    def validate_mode_contract(self) -> "AuthInjectionSpec":
        if self.mode in {"header", "cookie", "env", "config_file"} and not self.slot:
            raise ValueError(f"{self.mode} injection requires slot")
        if self.mode == "header" and self.slot and not _HEADER_NAME_RE.fullmatch(self.slot):
            raise ValueError("header injection slot must be a valid header name")
        if self.mode == "env" and self.slot and not _ENV_NAME_RE.fullmatch(self.slot):
            raise ValueError("env injection slot must be a valid environment variable name")
        if self.mode in {"cookie", "config_file", "cookie_jar", "browser_context", "mtls_cert", "proxy_auth"} and self.slot:
            if not _SLOT_RE.fullmatch(self.slot):
                raise ValueError(f"{self.mode} injection slot is invalid")
        if self.mode in CLI_AUTH_INJECTION_MODES:
            if not self.flag:
                raise ValueError(f"{self.mode} injection requires flag")
            expected = "equals" if self.mode == "cli_flag_equals" else "separate_arg"
            if self.placement != expected:
                raise ValueError(f"{self.mode} injection requires {expected} placement")
        else:
            if self.flag is not None:
                raise ValueError(f"{self.mode} injection must not declare CLI flag")
            if self.placement is not None:
                raise ValueError(f"{self.mode} injection must not declare CLI placement")
        return self


def validate_cli_auth_flag(flag: str) -> str:
    """Validate a CLI flag name that may later receive leased secret material."""
    if not isinstance(flag, str) or not _CLI_FLAG_RE.fullmatch(flag):
        raise ValueError("allowed_cli_flags must contain bounded CLI flag names")
    return flag


def normalize_credential_ref(name: str, value: Any) -> str:
    """Validate an opaque credential reference carried in action options."""
    if not isinstance(value, str):
        raise ValueError(f"{name} must be credential_ref")
    if "\x00" in value or not _CREDENTIAL_REF_RE.fullmatch(value):
        raise ValueError(f"{name} must be an opaque credential_ref")
    return value


def normalize_auth_injection_spec(name: str, value: Any) -> dict[str, Any]:
    """Validate and normalize auth injection metadata for action options."""
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be auth_injection")
    return AuthInjectionSpec.model_validate(dict(value)).model_dump(exclude_none=True)


def reject_raw_credential_option(name: str, value: Any) -> None:
    """Reject raw credential-looking action options before persistence/events.

    Authenticated scans should use credential_ref + auth_injection metadata.
    This guard blocks the common accidental bypass: putting tokens, cookies,
    Authorization headers, or API keys directly into action options.
    """
    lowered = name.strip().lower()
    if lowered in _RAW_CREDENTIAL_OPTION_KEYS:
        raise ValueError(
            f"{name} is a raw credential option; use credential_ref and auth_injection"
        )
    _reject_raw_credential_value(path=name, value=value)


def _reject_raw_credential_value(*, path: str, value: Any) -> None:
    if isinstance(value, str):
        if "\x00" in value:
            raise ValueError(f"{path} must not contain NUL bytes")
        if _looks_like_raw_credential(value):
            raise ValueError(
                f"{path} looks like raw credential material; use credential_ref"
            )
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            key_text = str(key)
            lowered = key_text.strip().lower()
            if lowered in _RAW_CREDENTIAL_OPTION_KEYS or lowered in {"value", "secret_value"}:
                raise ValueError(
                    f"{path}.{key_text} looks like raw credential material; use credential_ref"
                )
            _reject_raw_credential_value(path=f"{path}.{key_text}", value=item)
        return
    if isinstance(value, (list, tuple, set)):
        for index, item in enumerate(value):
            _reject_raw_credential_value(path=f"{path}[{index}]", value=item)


def _looks_like_raw_credential(value: str) -> bool:
    return any(pattern.search(value) for pattern in _RAW_CREDENTIAL_VALUE_PATTERNS)
