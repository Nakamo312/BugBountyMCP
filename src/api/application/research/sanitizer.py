from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

SANITIZER_VERSION = "research-sanitizer-v1"
REDACTION_POLICY_VERSION = "redaction-policy-v1"

SENSITIVE_HEADER_NAMES = {
    "authorization",
    "cookie",
    "proxy-authorization",
    "set-cookie",
    "x-api-key",
    "x-auth-token",
}

SENSITIVE_KEY_NAMES = SENSITIVE_HEADER_NAMES | {
    "access_token",
    "api_key",
    "apikey",
    "password",
    "passwd",
    "pwd",
    "refresh_token",
    "secret",
    "token",
}

SECRET_PAIR_RE = re.compile(
    r"(?i)\b("
    r"password|passwd|pwd|token|access_token|refresh_token|api[_-]?key|apikey|secret"
    r")=([^&\s]+)"
)


@dataclass(frozen=True)
class SanitizedText:
    safe_excerpt: str
    sanitizer_version: str = SANITIZER_VERSION
    redaction_policy_version: str = REDACTION_POLICY_VERSION
    sensitivity_level: str = "public"
    safe_for_search: bool = True
    safe_for_embedding: bool = True
    safe_for_llm: bool = True
    redaction_rules_triggered: tuple[str, ...] = field(default_factory=tuple)
    normalized_content_hash: str = ""
    sanitized_content_hash: str = ""


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _normalize(value: str) -> str:
    return value.replace("\r\n", "\n").replace("\r", "\n")


def _redact_secret_pairs(value: str) -> tuple[str, tuple[str, ...]]:
    rules: list[str] = []

    def replace_secret(match: re.Match[str]) -> str:
        rules.append("secret_pair")
        return f"{match.group(1)}=[redacted]"

    return SECRET_PAIR_RE.sub(replace_secret, value), tuple(sorted(set(rules)))


def sanitize_text(value: str | None, *, limit: int = 65_536) -> SanitizedText:
    normalized = _normalize(value or "")[:limit]
    sanitized, rules = _redact_secret_pairs(normalized)
    sensitivity_level = "credential_like" if rules else "public"
    safe_for_llm = not rules

    return SanitizedText(
        safe_excerpt=sanitized,
        sensitivity_level=sensitivity_level,
        safe_for_search=True,
        safe_for_embedding=safe_for_llm,
        safe_for_llm=safe_for_llm,
        redaction_rules_triggered=rules,
        normalized_content_hash=_sha256(normalized),
        sanitized_content_hash=_sha256(sanitized),
    )


def sanitize_header(name: str, value: str | None) -> SanitizedText:
    normalized_name = name.strip().lower()
    normalized_value = _normalize(value or "")
    if normalized_name in SENSITIVE_HEADER_NAMES:
        return SanitizedText(
            safe_excerpt="[redacted]",
            sensitivity_level="secret_confirmed",
            safe_for_search=False,
            safe_for_embedding=False,
            safe_for_llm=False,
            redaction_rules_triggered=("sensitive_header",),
            normalized_content_hash=_sha256(normalized_value),
            sanitized_content_hash=_sha256("[redacted]"),
        )
    return sanitize_text(normalized_value)


def sanitize_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if key_text.strip().lower() in SENSITIVE_KEY_NAMES:
                sanitized[key_text] = "[redacted]"
            else:
                sanitized[key_text] = sanitize_json(item)
        return sanitized
    if isinstance(value, list):
        return [sanitize_json(item) for item in value]
    if isinstance(value, tuple):
        return [sanitize_json(item) for item in value]
    if isinstance(value, str):
        return sanitize_text(value).safe_excerpt
    return value
