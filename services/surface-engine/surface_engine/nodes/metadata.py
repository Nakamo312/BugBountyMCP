from __future__ import annotations

from typing import Any, Mapping


def metadata_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def metadata_value(metadata: Mapping[str, Any], *paths: str) -> Any:
    for path in paths:
        current: Any = metadata
        found = True
        for part in path.split("."):
            if isinstance(current, Mapping) and part in current:
                current = current[part]
                continue
            found = False
            break
        if found:
            return current
    return None


def metadata_text(metadata: Mapping[str, Any], *paths: str) -> str | None:
    return optional_text(metadata_value(metadata, *paths))


def metadata_list(metadata: Mapping[str, Any], *paths: str) -> list[str]:
    value = metadata_value(metadata, *paths)
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return sorted(str(item).strip() for item in value if str(item).strip())
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def metadata_string_mapping(metadata: Mapping[str, Any], *paths: str) -> dict[str, str] | None:
    value = metadata_value(metadata, *paths)
    if isinstance(value, Mapping):
        return {str(key): str(val) for key, val in value.items()}
    return None


def header_names(headers: Any, fallback: Any = None) -> list[str]:
    if fallback:
        return [str(item) for item in fallback if str(item).strip()]
    if not headers:
        return []
    names: list[str] = []
    for header in headers:
        if isinstance(header, Mapping):
            name = header.get("name")
        else:
            name = header
        if name:
            names.append(str(name))
    return names


def optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def required_text(row: Mapping[str, Any], key: str) -> str:
    value = optional_text(row.get(key))
    if not value:
        raise ValueError(f"missing required observation field: {key}")
    return value


def optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def url_from_parts(row: Mapping[str, Any]) -> str:
    scheme = optional_text(row.get("scheme")) or "http"
    host = optional_text(row.get("host")) or ""
    path = optional_text(row.get("path")) or "/"
    return f"{scheme}://{host}{path}" if host else path
