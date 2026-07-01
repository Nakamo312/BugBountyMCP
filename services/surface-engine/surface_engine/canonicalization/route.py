from __future__ import annotations

from dataclasses import dataclass
import re
from urllib.parse import ParseResult

from .inputs import EndpointObservationInput

try:
    from api.infrastructure.normalization.path_normalizer import PathNormalizer
except ImportError as exc:  # pragma: no cover - exercised by integration setup
    raise ImportError(
        "surface_engine requires src/ on PYTHONPATH so it can reuse "
        "api.infrastructure.normalization.path_normalizer.PathNormalizer"
    ) from exc


@dataclass(frozen=True)
class RouteMaterial:
    normalized_method: str
    normalized_scheme: str | None
    normalized_host: str | None
    normalized_port: int | None
    protocol_family: str | None
    route_template: str
    safe_url: str
    route_key: str


_STATIC_ASSET_EXTENSIONS = {
    "css",
    "js",
    "mjs",
    "map",
    "png",
    "jpg",
    "jpeg",
    "gif",
    "svg",
    "ico",
    "webp",
    "woff",
    "woff2",
    "ttf",
    "eot",
    "pdf",
    "txt",
    "xml",
    "json",
}
_BASE64URL_RE = re.compile(r"^[A-Za-z0-9_-]+={0,2}$")
_HEX_RE = re.compile(r"^[0-9a-fA-F]+$")


def build_route_material(*, observation: EndpointObservationInput, parsed: ParseResult) -> RouteMaterial:
    transport = observation.transport
    normalized_method = normalize_method(observation.method)
    normalized_scheme = normalize_scheme(transport.scheme or parsed.scheme)
    normalized_host = normalize_host(observation.host or parsed.hostname)
    normalized_port = normalize_port(transport.port if transport.port is not None else parsed.port, normalized_scheme)
    protocol_family = protocol_family_for_scheme(normalized_scheme)
    raw_path = parsed.path or "/"
    route_template = normalize_route_template(observation.url or raw_path)
    safe_url = safe_canonical_url(
        scheme=normalized_scheme,
        host=normalized_host,
        explicit_port=explicit_port(port=transport.port, parsed_port=parsed.port, scheme=normalized_scheme),
        route_template=route_template,
    )
    return RouteMaterial(
        normalized_method=normalized_method,
        normalized_scheme=normalized_scheme,
        normalized_host=normalized_host,
        normalized_port=normalized_port,
        protocol_family=protocol_family,
        route_template=route_template,
        safe_url=safe_url,
        route_key=route_key(normalized_method, normalized_scheme, normalized_host, normalized_port, route_template),
    )


def normalize_route_template(url_or_path: str) -> str:
    """Normalize a URL/path using the shared normalizer plus surface-only wrappers."""

    normalized = PathNormalizer.normalize_path(url_or_path or "/")
    if normalized == "/":
        return normalized

    segments = [segment for segment in normalized.split("/") if segment]
    rewritten = [normalize_surface_segment(segment) for segment in segments]
    return "/" + "/".join(rewritten)


def normalize_surface_segment(segment: str) -> str:
    if not segment:
        return segment
    if segment.startswith("{") and segment.endswith("}"):
        return segment
    lowered = segment.lower()
    if looks_like_static_asset(lowered):
        return "{static_asset}"
    if looks_like_token_segment(segment):
        return "{token_like}"
    return segment


def looks_like_static_asset(segment: str) -> bool:
    if "." not in segment:
        return False
    suffix = segment.rsplit(".", 1)[-1]
    return suffix in _STATIC_ASSET_EXTENSIONS


def looks_like_token_segment(segment: str) -> bool:
    # JWT/JWS-like path segment: header.payload.signature.
    parts = segment.split(".")
    if len(parts) >= 3 and all(len(part) >= 6 and _BASE64URL_RE.fullmatch(part) for part in parts[:3]):
        return True

    compact = segment.strip("=")
    if len(compact) >= 32 and _BASE64URL_RE.fullmatch(segment):
        return True
    if len(compact) >= 32 and _HEX_RE.fullmatch(segment):
        return True
    return False


def explicit_port(*, port: int | str | None, parsed_port: int | None, scheme: str | None) -> int | None:
    raw = port if port is not None else parsed_port
    if raw is None:
        return None
    return normalize_port(raw, scheme)


def safe_canonical_url(*, scheme: str | None, host: str | None, explicit_port: int | None, route_template: str) -> str:
    """Return a queryless, fragmentless, userinfo-free canonical URL."""

    safe_path = route_template or "/"
    if not host:
        return safe_path
    authority = host
    if explicit_port is not None:
        authority = f"{authority}:{explicit_port}"
    if scheme:
        return f"{scheme}://{authority}{safe_path}"
    return f"{authority}{safe_path}"


def normalize_scheme(scheme: str | None) -> str | None:
    if not scheme:
        return None
    normalized = scheme.strip().lower()
    return normalized or None


def default_port(scheme: str | None) -> int | None:
    if scheme in {"http", "ws"}:
        return 80
    if scheme in {"https", "wss"}:
        return 443
    return None


def normalize_port(port: int | str | None, scheme: str | None) -> int | None:
    if port is None:
        return default_port(scheme)
    try:
        value = int(port)
    except (TypeError, ValueError):
        return default_port(scheme)
    if value <= 0 or value > 65535:
        return default_port(scheme)
    return value


def protocol_family_for_scheme(scheme: str | None) -> str | None:
    if scheme in {"http", "https"}:
        return "http"
    if scheme in {"ws", "wss"}:
        return "websocket"
    if scheme:
        return "other"
    return None


def normalize_method(method: str | None) -> str:
    normalized = (method or "GET").strip().upper()
    return normalized or "GET"


def normalize_host(host: str | None) -> str | None:
    if not host:
        return None
    normalized = host.strip().lower().rstrip(".")
    return normalized or None


def route_key(
    method: str,
    scheme: str | None,
    host: str | None,
    port: int | None,
    route_template: str,
) -> str:
    if host:
        authority = host
        if port is not None:
            authority = f"{authority}:{port}"
        if scheme:
            return f"{method} {scheme}://{authority}{route_template}"
        return f"{method} {authority}{route_template}"
    return f"{method} {route_template}"
