from __future__ import annotations

import math
import re
import shlex
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

_MAX_ARG_CHARS = 4096
_MAX_STDIN_SUMMARY_CHARS = 64
_MAX_TIMEOUT_SECONDS = 86_400
_MAX_ENV_VALUE_CHARS = 8192
_ENV_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

_SENSITIVE_OPTION_NAMES = frozenset(
    {
        "--authorization",
        "--auth",
        "--bearer",
        "--cookie",
        "--header",
        "--password",
        "--secret",
        "--session",
        "--token",
        "--api-key",
        "--apikey",
        "-H",
    }
)

_SENSITIVE_INLINE_PATTERNS = (
    re.compile(r"^(?P<key>--?(?:authorization|auth|bearer|cookie|header|password|secret|session|token|api[-_]?key))=(?P<value>.*)$", re.IGNORECASE),
    re.compile(r"^(?P<key>authorization|cookie|x-api-key|api-key|token):(?P<value>.*)$", re.IGNORECASE),
)


@dataclass(frozen=True, slots=True)
class CommandInvocation:
    """Validated command execution contract for infrastructure runners.

    This object is intentionally infrastructure-scoped. Application-level
    ToolInvocation and RunnerInvocationContext carry action lineage, policy,
    budget, and target context. CommandInvocation carries only the sanitized
    process-execution boundary: argv, optional stdin, timeout, and opaque future
    credential references that must not contain secret material.
    """

    argv: tuple[str, ...]
    stdin: str | None = None
    timeout: int | float = 600
    env: Mapping[str, str] = MappingProxyType({})
    credential_refs: tuple[str, ...] = ()

    def __init__(
        self,
        argv: Sequence[str],
        *,
        stdin: str | None = None,
        timeout: int | float = 600,
        env: Mapping[str, str] | None = None,
        credential_refs: Sequence[str] = (),
    ) -> None:
        object.__setattr__(self, "argv", tuple(validate_command_argv(argv)))
        object.__setattr__(self, "stdin", validate_command_stdin(stdin))
        object.__setattr__(self, "timeout", validate_command_timeout(timeout))
        object.__setattr__(self, "env", MappingProxyType(validate_command_env(env)))
        object.__setattr__(
            self,
            "credential_refs",
            tuple(validate_command_credential_refs(credential_refs)),
        )

    @property
    def stdin_summary(self) -> str:
        return summarize_stdin_for_log(self.stdin)

    @property
    def command_for_log(self) -> str:
        return format_command_for_log(self.argv)

    @property
    def env_audit_view(self) -> list[dict[str, Any]]:
        return redact_command_env(self.env)

    def process_env(self, base_env: Mapping[str, str]) -> dict[str, str]:
        return build_process_env(base_env, self.env)


def command_invocation(
    argv: Sequence[str],
    *,
    stdin: str | None = None,
    timeout: int | float = 600,
    env: Mapping[str, str] | None = None,
    credential_refs: Sequence[str] = (),
) -> CommandInvocation:
    return CommandInvocation(
        argv,
        stdin=stdin,
        timeout=timeout,
        env=env,
        credential_refs=credential_refs,
    )


def validate_command_argv(command: Sequence[str]) -> list[str]:
    if isinstance(command, (str, bytes)) or not isinstance(command, Sequence):
        raise ValueError("command must be a non-empty argv sequence")
    if not command:
        raise ValueError("command must not be empty")

    argv: list[str] = []
    for index, arg in enumerate(command):
        if not isinstance(arg, str):
            raise ValueError(f"command argument {index} must be a string")
        if not arg:
            raise ValueError(f"command argument {index} must not be empty")
        if "\x00" in arg:
            raise ValueError(f"command argument {index} must not contain NUL bytes")
        if len(arg) > _MAX_ARG_CHARS:
            raise ValueError(f"command argument {index} is too long")
        argv.append(arg)
    return argv


def validate_command_stdin(stdin: str | None) -> str | None:
    if stdin is not None and not isinstance(stdin, str):
        raise ValueError("command stdin must be a string when provided")
    if stdin is not None and "\x00" in stdin:
        raise ValueError("command stdin must not contain NUL bytes")
    return stdin


def validate_command_env(env: Mapping[str, str] | None) -> dict[str, str]:
    if env is None:
        return {}
    if not isinstance(env, Mapping):
        raise ValueError("command env must be a mapping of environment variable names to string values")

    validated: dict[str, str] = {}
    for key, value in env.items():
        if not isinstance(key, str):
            raise ValueError("command env names must be strings")
        if not key or "\x00" in key or not _ENV_NAME_PATTERN.fullmatch(key):
            raise ValueError(f"command env name is invalid: {key!r}")
        if not isinstance(value, str):
            raise ValueError(f"command env value for {key!r} must be a string")
        if "\x00" in value:
            raise ValueError(f"command env value for {key!r} must not contain NUL bytes")
        if len(value) > _MAX_ENV_VALUE_CHARS:
            raise ValueError(f"command env value for {key!r} is too long")
        validated[key] = value
    return validated


def build_process_env(base_env: Mapping[str, str], overlay: Mapping[str, str] | None) -> dict[str, str]:
    if not isinstance(base_env, Mapping):
        raise ValueError("base env must be a mapping")
    base = _copy_process_base_env(base_env)
    base.update(validate_command_env(overlay))
    return base


def _copy_process_base_env(base_env: Mapping[str, str]) -> dict[str, str]:
    copied: dict[str, str] = {}
    for key, value in base_env.items():
        if not isinstance(key, str) or not key or "\x00" in key:
            raise ValueError(f"base env name is invalid: {key!r}")
        if not isinstance(value, str):
            raise ValueError(f"base env value for {key!r} must be a string")
        if "\x00" in value:
            raise ValueError(f"base env value for {key!r} must not contain NUL bytes")
        copied[key] = value
    return copied


def redact_command_env(env: Mapping[str, str] | None) -> list[dict[str, Any]]:
    return [
        {"name": name, "present": True, "redacted": True}
        for name in sorted(validate_command_env(env))
    ]


def summarize_env_for_log(env: Mapping[str, str] | None) -> str:
    names = sorted(validate_command_env(env))
    if not names:
        return "absent"
    return "present(names=" + ",".join(names) + ")"


def validate_command_credential_refs(credential_refs: Sequence[str]) -> list[str]:
    if isinstance(credential_refs, (str, bytes)) or not isinstance(credential_refs, Sequence):
        raise ValueError("credential_refs must be a sequence of opaque reference strings")

    refs: list[str] = []
    for index, ref in enumerate(credential_refs):
        if not isinstance(ref, str):
            raise ValueError(f"credential ref {index} must be a string")
        if not ref:
            raise ValueError(f"credential ref {index} must not be empty")
        if "\x00" in ref:
            raise ValueError(f"credential ref {index} must not contain NUL bytes")
        if len(ref) > 256:
            raise ValueError(f"credential ref {index} is too long")
        refs.append(ref)
    return refs


def validate_command_timeout(timeout: int | float) -> int | float:
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)):
        raise ValueError("timeout must be a positive number of seconds")
    if not math.isfinite(float(timeout)) or timeout <= 0:
        raise ValueError("timeout must be a positive finite number of seconds")
    if timeout > _MAX_TIMEOUT_SECONDS:
        raise ValueError("timeout exceeds maximum allowed command duration")
    return timeout


def redact_command_argv(command: Sequence[str]) -> list[str]:
    argv = validate_command_argv(command)
    redacted: list[str] = []
    redact_next = False

    for arg in argv:
        if redact_next:
            redacted.append("<redacted>")
            redact_next = False
            continue

        inline = _redact_inline_secret(arg)
        redacted.append(inline)

        if arg in _SENSITIVE_OPTION_NAMES:
            redact_next = True

    return redacted


def format_command_for_log(command: Sequence[str]) -> str:
    return shlex.join(redact_command_argv(command))


def summarize_stdin_for_log(stdin: str | None) -> str:
    if stdin is None:
        return "absent"
    line_count = 0 if stdin == "" else stdin.count("\n") + 1
    if len(stdin) <= _MAX_STDIN_SUMMARY_CHARS and "\n" not in stdin:
        shape = f"chars={len(stdin)}"
    else:
        shape = f"chars={len(stdin)} lines={line_count}"
    return f"present({shape})"


def _redact_inline_secret(arg: str) -> str:
    for pattern in _SENSITIVE_INLINE_PATTERNS:
        match = pattern.match(arg)
        if match:
            return f"{match.group('key')}=<redacted>" if "=" in arg else f"{match.group('key')}: <redacted>"
    return arg
