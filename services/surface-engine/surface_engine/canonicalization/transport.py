from __future__ import annotations

from .body import normalize_name, normalize_names
from .models import TransportShape
from ..fingerprints import build_transport_fingerprint


def build_transport_shape(
    *,
    scheme: str | None,
    protocol_family: str | None,
    port: int | None,
    http_version: str | None,
    tls: bool | None,
    alpn: str | None,
    transport_protocol: str | None,
    connection_features: list[str] | tuple[str, ...] | None,
) -> TransportShape:
    normalized_http_version = normalize_http_version(http_version)
    normalized_tls = normalize_tls(tls, scheme)
    normalized_alpn = normalize_name(alpn) if alpn else None
    normalized_transport_protocol = normalize_transport_protocol(
        transport_protocol,
        scheme=scheme,
        http_version=normalized_http_version,
        alpn=normalized_alpn,
    )
    normalized_connection_features = normalize_names(list(connection_features or []))
    transport_fingerprint = build_transport_fingerprint(
        scheme=scheme,
        protocol_family=protocol_family,
        port=port,
        http_version=normalized_http_version,
        tls=normalized_tls,
        alpn=normalized_alpn,
        transport_protocol=normalized_transport_protocol,
        connection_features=normalized_connection_features,
    )
    return TransportShape(
        scheme=scheme,
        protocol_family=protocol_family,
        port=port,
        http_version=normalized_http_version,
        tls=normalized_tls,
        alpn=normalized_alpn,
        transport_protocol=normalized_transport_protocol,
        connection_features=normalized_connection_features,
        transport_fingerprint=transport_fingerprint,
    )


def normalize_http_version(http_version: str | None) -> str | None:
    if not http_version:
        return None
    normalized = http_version.strip().lower().replace(" ", "")
    aliases = {
        "1": "http/1.0",
        "1.0": "http/1.0",
        "http1": "http/1.0",
        "http/1": "http/1.0",
        "h1": "http/1.1",
        "1.1": "http/1.1",
        "http1.1": "http/1.1",
        "http/1.1": "http/1.1",
        "h2": "http/2",
        "2": "http/2",
        "2.0": "http/2",
        "http2": "http/2",
        "http/2": "http/2",
        "h3": "http/3",
        "3": "http/3",
        "3.0": "http/3",
        "http3": "http/3",
        "http/3": "http/3",
    }
    return aliases.get(normalized, normalized or None)


def normalize_tls(tls: bool | None, scheme: str | None) -> bool | None:
    if tls is not None:
        return bool(tls)
    if scheme in {"https", "wss"}:
        return True
    if scheme in {"http", "ws"}:
        return False
    return None


def normalize_transport_protocol(
    transport_protocol: str | None,
    *,
    scheme: str | None,
    http_version: str | None,
    alpn: str | None,
) -> str | None:
    if transport_protocol:
        normalized = normalize_name(transport_protocol)
        return normalized or None
    if scheme in {"http", "https", "ws", "wss"}:
        if http_version == "http/3" or alpn == "h3":
            return "quic"
        return "tcp"
    return None
