"""Curated Postgres MCP tools.

This module deliberately exposes fixed artifact readers only. Do not add a
generic SQL execution tool here.
"""
from __future__ import annotations

import uuid
from typing import Any, Awaitable, Callable

from api.infrastructure.artifacts.postgres_reader import PostgresArtifactReader

ToolHandler = Callable[[PostgresArtifactReader, dict[str, Any]], Awaitable[Any]]


def _uuid_arg(args: dict[str, Any], name: str) -> uuid.UUID:
    value = args.get(name)
    if not value:
        raise ValueError(f"{name} is required")
    return uuid.UUID(str(value))


def _optional_uuid_arg(args: dict[str, Any], name: str) -> uuid.UUID | None:
    value = args.get(name)
    return uuid.UUID(str(value)) if value else None


def _dump(result: Any) -> Any:
    if isinstance(result, list):
        return [item.model_dump(mode="json") for item in result]
    if result is None:
        return None
    return result.model_dump(mode="json")


async def list_hosts(reader: PostgresArtifactReader, args: dict[str, Any]) -> Any:
    return _dump(await reader.list_hosts(
        program_id=_uuid_arg(args, "program_id"),
        q=args.get("q"),
        in_scope=args.get("in_scope"),
        limit=args.get("limit"),
        offset=args.get("offset"),
    ))


async def list_ips(reader: PostgresArtifactReader, args: dict[str, Any]) -> Any:
    return _dump(await reader.list_ips(
        program_id=_uuid_arg(args, "program_id"),
        q=args.get("q"),
        in_scope=args.get("in_scope"),
        limit=args.get("limit"),
        offset=args.get("offset"),
    ))


async def list_services(reader: PostgresArtifactReader, args: dict[str, Any]) -> Any:
    return _dump(await reader.list_services(
        program_id=_uuid_arg(args, "program_id"),
        host_id=_optional_uuid_arg(args, "host_id"),
        port=args.get("port"),
        scheme=args.get("scheme"),
        tech=args.get("tech"),
        limit=args.get("limit"),
        offset=args.get("offset"),
    ))


async def list_endpoints(reader: PostgresArtifactReader, args: dict[str, Any]) -> Any:
    return _dump(await reader.list_endpoints(
        program_id=_uuid_arg(args, "program_id"),
        host_id=_optional_uuid_arg(args, "host_id"),
        method=args.get("method"),
        status=args.get("status"),
        q=args.get("q"),
        limit=args.get("limit"),
        offset=args.get("offset"),
    ))


async def get_endpoint_detail(reader: PostgresArtifactReader, args: dict[str, Any]) -> Any:
    return _dump(await reader.get_endpoint_detail(_uuid_arg(args, "endpoint_id")))


async def list_parameters(reader: PostgresArtifactReader, args: dict[str, Any]) -> Any:
    return _dump(await reader.list_parameters(
        endpoint_id=_optional_uuid_arg(args, "endpoint_id"),
        program_id=_optional_uuid_arg(args, "program_id"),
        location=args.get("location"),
        name=args.get("name"),
        reflected=args.get("reflected"),
        limit=args.get("limit"),
        offset=args.get("offset"),
    ))


async def list_headers(reader: PostgresArtifactReader, args: dict[str, Any]) -> Any:
    return _dump(await reader.list_headers(
        endpoint_id=_optional_uuid_arg(args, "endpoint_id"),
        program_id=_optional_uuid_arg(args, "program_id"),
        name=args.get("name"),
        limit=args.get("limit"),
        offset=args.get("offset"),
    ))


async def list_bodies(reader: PostgresArtifactReader, args: dict[str, Any]) -> Any:
    return _dump(await reader.list_bodies(
        endpoint_id=_optional_uuid_arg(args, "endpoint_id"),
        program_id=_optional_uuid_arg(args, "program_id"),
        body_hash=args.get("body_hash"),
        limit=args.get("limit"),
        offset=args.get("offset"),
    ))


async def list_dns_records(reader: PostgresArtifactReader, args: dict[str, Any]) -> Any:
    return _dump(await reader.list_dns_records(
        program_id=_uuid_arg(args, "program_id"),
        host_id=_optional_uuid_arg(args, "host_id"),
        record_type=args.get("record_type"),
        q=args.get("q"),
        limit=args.get("limit"),
        offset=args.get("offset"),
    ))


async def list_findings(reader: PostgresArtifactReader, args: dict[str, Any]) -> Any:
    return _dump(await reader.list_findings(
        program_id=_uuid_arg(args, "program_id"),
        severity=args.get("severity"),
        verified=args.get("verified"),
        limit=args.get("limit"),
        offset=args.get("offset"),
    ))


async def list_leaks(reader: PostgresArtifactReader, args: dict[str, Any]) -> Any:
    return _dump(await reader.list_leaks(
        program_id=_uuid_arg(args, "program_id"),
        verified=args.get("verified"),
        limit=args.get("limit"),
        offset=args.get("offset"),
    ))


async def list_events(reader: PostgresArtifactReader, args: dict[str, Any]) -> Any:
    return _dump(await reader.list_events(
        program_id=_uuid_arg(args, "program_id"),
        event_type=args.get("event_type"),
        profile=args.get("profile"),
        limit=args.get("limit"),
        offset=args.get("offset"),
    ))


COMMON_PAGING = {
    "limit": {"type": "integer", "minimum": 1, "maximum": 100},
    "offset": {"type": "integer", "minimum": 0},
}


TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "list_hosts",
        "description": "List scoped host/domain artifacts for a program.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "program_id": {"type": "string", "format": "uuid"},
                "q": {"type": "string"},
                "in_scope": {"type": "boolean"},
                **COMMON_PAGING,
            },
            "required": ["program_id"],
        },
    },
    {
        "name": "list_ips",
        "description": "List IP artifacts for a program.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "program_id": {"type": "string", "format": "uuid"},
                "q": {"type": "string"},
                "in_scope": {"type": "boolean"},
                **COMMON_PAGING,
            },
            "required": ["program_id"],
        },
    },
    {
        "name": "list_services",
        "description": "List service, port, scheme, and technology artifacts.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "program_id": {"type": "string", "format": "uuid"},
                "host_id": {"type": "string", "format": "uuid"},
                "port": {"type": "integer", "minimum": 1, "maximum": 65535},
                "scheme": {"type": "string", "enum": ["http", "https"]},
                "tech": {"type": "string"},
                **COMMON_PAGING,
            },
            "required": ["program_id"],
        },
    },
    {
        "name": "list_endpoints",
        "description": "List endpoint artifacts with host, path, normalized path, methods, and status.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "program_id": {"type": "string", "format": "uuid"},
                "host_id": {"type": "string", "format": "uuid"},
                "method": {"type": "string"},
                "status": {"type": "integer", "minimum": 100, "maximum": 599},
                "q": {"type": "string"},
                **COMMON_PAGING,
            },
            "required": ["program_id"],
        },
    },
    {
        "name": "get_endpoint_detail",
        "description": "Get one endpoint with parameters, headers, and body refs.",
        "inputSchema": {
            "type": "object",
            "properties": {"endpoint_id": {"type": "string", "format": "uuid"}},
            "required": ["endpoint_id"],
        },
    },
    {
        "name": "list_parameters",
        "description": "List input parameters by endpoint or program.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "endpoint_id": {"type": "string", "format": "uuid"},
                "program_id": {"type": "string", "format": "uuid"},
                "location": {"type": "string", "enum": ["query", "body", "path", "header", "cookie"]},
                "name": {"type": "string"},
                "reflected": {"type": "boolean"},
                **COMMON_PAGING,
            },
        },
    },
    {
        "name": "list_headers",
        "description": "List response headers by endpoint or program.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "endpoint_id": {"type": "string", "format": "uuid"},
                "program_id": {"type": "string", "format": "uuid"},
                "name": {"type": "string"},
                **COMMON_PAGING,
            },
        },
    },
    {
        "name": "list_bodies",
        "description": "List body refs and sanitized previews by endpoint or program; full content is not exposed.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "endpoint_id": {"type": "string", "format": "uuid"},
                "program_id": {"type": "string", "format": "uuid"},
                "body_hash": {"type": "string"},
                **COMMON_PAGING,
            },
        },
    },
    {
        "name": "list_dns_records",
        "description": "List DNS records by program, host, type, or text query.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "program_id": {"type": "string", "format": "uuid"},
                "host_id": {"type": "string", "format": "uuid"},
                "record_type": {"type": "string", "enum": ["A", "AAAA", "CNAME", "MX", "TXT", "NS", "SOA", "PTR"]},
                "q": {"type": "string"},
                **COMMON_PAGING,
            },
            "required": ["program_id"],
        },
    },
    {
        "name": "list_findings",
        "description": "List findings with severity and verification filters.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "program_id": {"type": "string", "format": "uuid"},
                "severity": {"type": "string", "enum": ["critical", "high", "medium", "low", "info"]},
                "verified": {"type": "boolean"},
                **COMMON_PAGING,
            },
            "required": ["program_id"],
        },
    },
    {
        "name": "list_leaks",
        "description": "List leak artifacts with verification filters.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "program_id": {"type": "string", "format": "uuid"},
                "verified": {"type": "boolean"},
                **COMMON_PAGING,
            },
            "required": ["program_id"],
        },
    },
    {
        "name": "list_events",
        "description": "List job/run/event-store artifacts as evidence trail.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "program_id": {"type": "string", "format": "uuid"},
                "event_type": {"type": "string"},
                "profile": {"type": "string"},
                **COMMON_PAGING,
            },
            "required": ["program_id"],
        },
    },
]

TOOL_HANDLERS: dict[str, ToolHandler] = {
    "list_hosts": list_hosts,
    "list_ips": list_ips,
    "list_services": list_services,
    "list_endpoints": list_endpoints,
    "get_endpoint_detail": get_endpoint_detail,
    "list_parameters": list_parameters,
    "list_headers": list_headers,
    "list_bodies": list_bodies,
    "list_dns_records": list_dns_records,
    "list_findings": list_findings,
    "list_leaks": list_leaks,
    "list_events": list_events,
}


async def call_tool(reader: PostgresArtifactReader, name: str, arguments: dict[str, Any]) -> Any:
    try:
        handler = TOOL_HANDLERS[name]
    except KeyError as exc:
        raise ValueError(f"Unknown MCP tool: {name}") from exc
    return await handler(reader, arguments)
