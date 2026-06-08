from __future__ import annotations

import hashlib
import json
import math
import re
from typing import Any
from urllib.parse import unquote, urlparse

VALID_LOCATIONS = {
    "query",
    "path",
    "header",
    "cookie",
    "form_body",
    "json_body",
    "xml_body",
    "response_body",
}

SENSITIVE_NAMES = {
    "access_token",
    "api_key",
    "apikey",
    "authorization",
    "cookie",
    "password",
    "passwd",
    "pwd",
    "refresh_token",
    "secret",
    "session",
    "set-cookie",
    "token",
    "x-api-key",
    "x-auth-token",
}

OBJECT_IDENTIFIER_TERMS = ("id", "uuid", "user", "account", "tenant", "org")
STATE_CHANGING_TERMS = ("create", "update", "delete", "reset", "invite", "upload", "import", "export")
REDIRECT_TERMS = ("redirect", "return", "next", "callback")
SCHEMA_KEYS = {"openapi", "swagger", "paths", "components", "definitions", "graphql"}

EMAIL_RE = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
PHONE_RE = re.compile(r"(?<!\d)(?:\+?\d[\d .()\-]{7,}\d)(?!\d)")
SECRET_PAIR_RE = re.compile(
    r"(?i)\b(password|passwd|pwd|token|access_token|refresh_token|api[_-]?key|apikey|secret|session)=([^&\s]+)"
)
TOKEN_SPLIT_RE = re.compile(r"[^\w]+")
JWT_RE = re.compile(r"^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$")
BASE64_RE = re.compile(r"^[A-Za-z0-9+/=_-]{20,}$")
PHP_OBJECT_RE = re.compile(r'^O:\d+:"[^"]+":\d+:\{')
GRAPHQL_RE = re.compile(r"(?is)\b(query|mutation|subscription)\b\s*(?:[A-Za-z_][\w]*)?\s*\{")


def extract_safe_features(
    *,
    path: str | None,
    title: str | None,
    content_type: str | None,
    headers: dict[str, Any] | None,
    query_params: dict[str, Any] | None,
    body_preview: str | None,
) -> dict[str, Any]:
    normalized_headers = {str(name).strip().lower(): value for name, value in (headers or {}).items()}
    params = query_params or {}
    json_keys = _json_object_keys(body_preview)

    query_shapes = [
        extract_value_shape(
            name=str(name),
            location="query",
            field_path=f"query.{name}",
            value=str(value),
        )
        for name, value in params.items()
    ]

    body_shape_markers = ["schema_like"] if SCHEMA_KEYS.intersection(json_keys) else []

    return {
        "path_tokens": _tokens(path or ""),
        "title_tokens": _tokens(title or ""),
        "content_type": (content_type or "").strip().lower() or None,
        "header_names": sorted(normalized_headers),
        "query_params": [{"name": str(name), "shape": shape} for name, shape in zip(params, query_shapes)],
        "object_identifier_terms": sorted(_matching_names(params.keys(), OBJECT_IDENTIFIER_TERMS)),
        "state_changing_terms": sorted(set(_tokens(path or "")).intersection(STATE_CHANGING_TERMS)),
        "redirect_terms": sorted(_matching_names(params.keys(), REDIRECT_TERMS)),
        "json_keys": sorted(json_keys),
        "shape_markers": body_shape_markers,
        "reflection": [],
        "error_markers": [],
    }


def extract_value_shape(
    *,
    name: str,
    location: str,
    value: str,
    field_path: str | None = None,
    observation_ref: dict[str, str] | None = None,
) -> dict[str, Any]:
    if location not in VALID_LOCATIONS:
        raise ValueError(f"unsupported value location: {location}")

    text = str(value or "")
    decoded = unquote(text)
    encodings: list[str] = []
    classes: list[str] = []
    markers: list[str] = []
    redaction_rules: list[str] = []

    if decoded != text:
        encodings.append("urlencoded")

    normalized_name = name.strip().lower()
    secret_name = _is_sensitive_name(normalized_name)
    secret_value = bool(SECRET_PAIR_RE.search(decoded))
    pii = _contains_pii(decoded) or normalized_name in {"email", "phone", "username", "name"}

    if secret_name:
        redaction_rules.append("sensitive_name")
    if secret_value:
        redaction_rules.append("secret_pair")
    if pii:
        redaction_rules.append("pii_marker")

    url = urlparse(decoded)
    is_absolute_url = url.scheme in {"http", "https"} and bool(url.netloc)
    if is_absolute_url:
        classes.append("absolute_url")
        markers.extend(["url_scheme", "external_host"])

    if JWT_RE.match(decoded) and not _looks_like_version(decoded):
        classes.append("jwt_like")
        markers.append("jwt_three_segments")

    if _is_base64_like(decoded):
        classes.append("base64_like")
        markers.append("base64_charset")
        if decoded.startswith("rO0AB"):
            classes.append("java_serialized_object")
            markers.append("java_serialized_magic")

    if PHP_OBJECT_RE.match(decoded):
        classes.append("php_serialized_object")
        markers.append("php_serialized_object_marker")

    if GRAPHQL_RE.search(decoded):
        classes.append("graphql_query")
        markers.extend(["graphql_operation", "curly_braces"])

    if "{{" in decoded and "}}" in decoded:
        classes.append("template_syntax")
        markers.extend(["template_delimiter", "curly_braces"])

    if _is_sql_like(decoded):
        classes.append("sql_like_expression")
        if "'" in decoded:
            markers.append("single_quote")
        if '"' in decoded:
            markers.append("double_quote")
        if "--" in decoded:
            markers.append("sql_comment_dash")
        if "#" in decoded:
            markers.append("sql_comment_hash")
        if re.search(r"(?i)\b(or|and)\b", decoded):
            markers.append("boolean_operator")

    markers.extend(_generic_markers(decoded))
    classes = _dedupe(classes)
    markers = _dedupe(markers)

    sample = _redacted_sample(
        decoded,
        classes=classes,
        secret=secret_name and "jwt_like" not in classes,
        pii=pii,
        is_absolute_url=is_absolute_url,
    )
    contains_secret = secret_name or (secret_value and not is_absolute_url)
    safe_for_external = not contains_secret and not pii
    safe_for_local = not contains_secret and not pii
    claim_type = _claim_type(classes, is_absolute_url)

    return {
        "name": name,
        "location": location,
        "field_path": field_path,
        "observation_ref": observation_ref,
        "classes": classes,
        "encodings": encodings,
        "markers": markers,
        "length_bucket": _length_bucket(decoded),
        "entropy_class": _entropy_class(decoded),
        "sample_redacted": sample,
        "sample_policy": "shape_only",
        "host_relation": "external" if is_absolute_url else None,
        "claim_type": claim_type,
        "fingerprint": _fingerprint(name, location, classes, decoded, is_absolute_url),
        "redaction_rules_triggered": sorted(set(redaction_rules)),
        "safety": {
            "safe_for_search": not contains_secret,
            "safe_for_embedding": safe_for_external,
            "safe_for_external_llm": safe_for_external,
            "safe_for_local_llm": safe_for_local,
            "safe_for_manual_review": True,
            "contains_secret": contains_secret,
            "contains_pii": pii,
        },
    }


def _tokens(value: str) -> list[str]:
    normalized = value.replace("{", "").replace("}", "")
    return [token.lower() for token in TOKEN_SPLIT_RE.split(normalized) if token]


def _matching_names(names: Any, needles: tuple[str, ...]) -> set[str]:
    matches: set[str] = set()
    for name in names:
        normalized = str(name).strip().lower()
        if any(needle in normalized for needle in needles):
            matches.add(normalized)
    return matches


def _json_object_keys(value: str | None) -> set[str]:
    try:
        parsed = json.loads(value or "")
    except (TypeError, ValueError):
        return set()
    if not isinstance(parsed, dict):
        return set()
    return {str(key).lower() for key in parsed.keys()}


def _is_sensitive_name(name: str) -> bool:
    return name in SENSITIVE_NAMES or any(part in SENSITIVE_NAMES for part in re.split(r"[\W_]+", name))


def _contains_pii(value: str) -> bool:
    return bool(EMAIL_RE.search(value) or PHONE_RE.search(value))


def _is_base64_like(value: str) -> bool:
    if not BASE64_RE.match(value):
        return False
    if "." in value:
        return False
    return len(value) >= 24


def _looks_like_version(value: str) -> bool:
    return bool(re.match(r"^\d+(?:\.\d+){1,3}$", value))


def _is_sql_like(value: str) -> bool:
    return bool(
        ("'" in value or '"' in value)
        and re.search(r"(?i)\b(or|and)\b", value)
        and re.search(r"\d+\s*=\s*\d+", value)
    ) or bool("--" in value and re.search(r"(?i)\b(select|union|where|or|and)\b", value))


def _generic_markers(value: str) -> list[str]:
    markers: list[str] = []
    if "`" in value:
        markers.append("backtick")
    if ";" in value:
        markers.append("semicolon")
    if "|" in value:
        markers.append("pipe")
    if "$" in value:
        markers.append("dollar")
    if "<" in value or ">" in value:
        markers.append("angle_brackets")
    if "../" in value or "..\\" in value:
        markers.append("path_traversal_sequence")
    if any(operator in value for operator in ("->", "::", "$.")):
        markers.append("json_operator")
    return markers


def _redacted_sample(value: str, *, classes: list[str], secret: bool, pii: bool, is_absolute_url: bool) -> str:
    if secret:
        return "<redacted-secret>"
    if "jwt_like" in classes:
        return "<jwt:header.payload.signature>"
    if "java_serialized_object" in classes:
        return "rO0AB<base64-java-serialized-object>"
    if "php_serialized_object" in classes:
        return "O:<n>:<class>:..."
    if is_absolute_url:
        parsed = urlparse(value)
        return f"{parsed.scheme}://<external-domain>{parsed.path or '/'}".rstrip("/")
    if "sql_like_expression" in classes:
        sample = re.sub(r"'", "<quote>", value)
        sample = re.sub(r"\b\d+\b", "<number>", sample)
        sample = sample.replace("--", "<comment>")
        return sample
    if pii:
        return "<redacted-pii>"
    if _is_base64_like(value):
        return "<base64-like:length=%d>" % len(value)
    if len(value) > 32:
        return f"{value[:8]}<redacted:length={len(value)}>"
    return value


def _claim_type(classes: list[str], is_absolute_url: bool) -> str:
    if is_absolute_url:
        return "param_value_has_external_url"
    if "sql_like_expression" in classes:
        return "param_value_has_sql_metacharacters"
    if "java_serialized_object" in classes or "php_serialized_object" in classes:
        return "param_value_looks_serialized"
    if "graphql_query" in classes:
        return "body_contains_graphql_query"
    return "value_shape_observed"


def _fingerprint(name: str, location: str, classes: list[str], value: str, is_absolute_url: bool) -> str:
    normalized_value = value
    if is_absolute_url:
        parsed = urlparse(value)
        normalized_value = f"{parsed.scheme}://<external-domain>{parsed.path or '/'}".rstrip("/")
    elif "jwt_like" in classes:
        normalized_value = "<jwt>"
    elif "java_serialized_object" in classes:
        normalized_value = "<java-serialized>"
    elif "php_serialized_object" in classes:
        normalized_value = "<php-serialized>"
    material = "|".join([location, name.lower(), ",".join(sorted(classes)), normalized_value])
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _length_bucket(value: str) -> str:
    length = len(value)
    if length == 0:
        return "empty"
    if length <= 8:
        return "short"
    if length <= 64:
        return "medium"
    if length <= 512:
        return "long"
    return "very_long"


def _entropy_class(value: str) -> str:
    if not value:
        return "empty"
    counts = {char: value.count(char) for char in set(value)}
    entropy = -sum((count / len(value)) * math.log2(count / len(value)) for count in counts.values())
    if entropy >= 4.5:
        return "high"
    if entropy >= 2.5:
        return "medium"
    return "low"


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))
