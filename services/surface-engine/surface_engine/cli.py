from __future__ import annotations

import argparse
import json

from .canonicalize import canonicalize_endpoint


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="surface-engine")
    subparsers = parser.add_subparsers(dest="command", required=True)

    canonicalize = subparsers.add_parser(
        "canonicalize-url",
        help="Print deterministic surface fingerprints for one URL.",
    )
    canonicalize.add_argument("url")
    canonicalize.add_argument("--method", default="GET")
    canonicalize.add_argument("--program-id")
    canonicalize.add_argument("--scheme", help="Optional scheme override, e.g. http, https, ws, wss.")
    canonicalize.add_argument("--port", type=int)
    canonicalize.add_argument("--http-version", help="Observed HTTP version, e.g. HTTP/1.1, h2, HTTP/3.")
    canonicalize.add_argument("--tls", choices=["true", "false"], help="Optional TLS override when scheme alone is not enough.")
    canonicalize.add_argument("--alpn", help="Observed ALPN token, e.g. http/1.1, h2, h3.")
    canonicalize.add_argument("--transport-protocol", help="Observed transport, e.g. tcp or quic.")
    canonicalize.add_argument("--connection-feature", action="append", default=[], help="Protocol/connection feature such as keep_alive, multiplexed, sse, websocket_upgrade, long_polling.")
    canonicalize.add_argument("--status-code", type=int)
    canonicalize.add_argument("--content-type", help="Backward-compatible response Content-Type alias.")
    canonicalize.add_argument("--request-content-type")
    canonicalize.add_argument("--request-body-field", action="append", default=[], help="Request body field as name=value; value is reduced to a type class.")
    canonicalize.add_argument("--request-json-key", action="append", default=[])
    canonicalize.add_argument("--request-xml-tag", action="append", default=[])
    canonicalize.add_argument("--response-content-type")
    canonicalize.add_argument("--json-key", action="append", default=[], help="Backward-compatible response JSON key alias.")
    canonicalize.add_argument("--response-json-key", action="append", default=[])
    canonicalize.add_argument("--response-xml-tag", action="append", default=[])
    canonicalize.add_argument("--header-name", action="append", default=[])
    canonicalize.set_defaults(func=_canonicalize_url)
    return parser


def _canonicalize_url(args: argparse.Namespace) -> int:
    endpoint = canonicalize_endpoint(
        url=args.url,
        method=args.method,
        program_id=args.program_id,
        scheme=args.scheme,
        port=args.port,
        http_version=args.http_version,
        tls=_parse_bool(args.tls),
        alpn=args.alpn,
        transport_protocol=args.transport_protocol,
        connection_features=args.connection_feature,
        status_code=args.status_code,
        content_type=args.content_type,
        request_content_type=args.request_content_type,
        request_body_fields=_parse_kv_args(args.request_body_field),
        request_json_keys=args.request_json_key,
        request_xml_tags=args.request_xml_tag,
        response_content_type=args.response_content_type,
        response_json_keys=args.response_json_key or args.json_key,
        response_xml_tags=args.response_xml_tag,
        header_names=args.header_name,
    )
    print(json.dumps(endpoint.to_features(), indent=2, sort_keys=True))
    return 0



def _parse_bool(value: str | None) -> bool | None:
    if value is None:
        return None
    return value.lower() == "true"


def _parse_kv_args(values: list[str]) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for item in values:
        if "=" in item:
            key, value = item.split("=", 1)
        else:
            key, value = item, ""
        key = key.strip()
        if key:
            parsed[key] = value
    return parsed


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)
