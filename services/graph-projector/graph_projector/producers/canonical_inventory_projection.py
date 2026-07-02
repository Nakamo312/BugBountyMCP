from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping
from uuid import UUID

from ..row_codec import (
    optional_bool,
    optional_int,
    optional_text,
    optional_uuid_text,
    required_row_uuid,
)
from .canonical_inventory_keys import canonical_ip_address, inventory_service_key


@dataclass(frozen=True)
class CanonicalInventoryRow:
    program_id: UUID
    host_id: str | None
    hostname: str
    ip_id: str | None
    ip_address: str
    host_ip_source: str | None
    service: tuple[str, str, int] | None
    service_id: str | None
    technologies: list[str]
    cidr_id: str | None
    cidr: str | None
    cidr_ip_count: int | None
    cidr_in_scope: bool | None
    asn_id: str | None
    asn_number: int | None
    asn_name: str | None
    asn_country: str | None


def parse_canonical_inventory_row(row: Mapping[str, Any]) -> CanonicalInventoryRow | None:
    hostname = _optional_hostname(row.get("hostname"))
    ip_address = _optional_ip_address(row.get("ip_address"))
    cidr = optional_text(row.get("cidr"))
    asn_number = optional_int(row.get("asn_number"))
    if hostname is None and ip_address is None and cidr is None and asn_number is None:
        return None
    return CanonicalInventoryRow(
        program_id=required_row_uuid(row, "program_id", context="canonical inventory row"),
        host_id=optional_uuid_text(row.get("host_id")),
        hostname=hostname or "",
        ip_id=optional_uuid_text(row.get("ip_id")),
        ip_address=ip_address or "",
        host_ip_source=optional_text(row.get("host_ip_source")),
        service=_optional_service(row, hostname, ip_address),
        service_id=optional_uuid_text(row.get("service_id")),
        technologies=_technology_names(row.get("technologies")),
        cidr_id=optional_uuid_text(row.get("cidr_id")),
        cidr=cidr,
        cidr_ip_count=optional_int(row.get("cidr_ip_count")),
        cidr_in_scope=optional_bool(row.get("cidr_in_scope")),
        asn_id=optional_uuid_text(row.get("asn_id")),
        asn_number=asn_number,
        asn_name=optional_text(row.get("asn_name")),
        asn_country=optional_text(row.get("asn_country")),
    )


def _optional_hostname(value: Any) -> str | None:
    text = optional_text(value)
    if text is None:
        return None
    hostname = text.lower().rstrip(".")
    return hostname or None


def _optional_ip_address(value: Any) -> str | None:
    text = optional_text(value)
    if text is None:
        return None
    return canonical_ip_address(text)


def _optional_service(row: Mapping[str, Any], hostname: str | None, ip_address: str | None) -> tuple[str, str, int] | None:
    if row.get("service_id") is None and row.get("service_scheme") is None and row.get("service_port") is None:
        return None
    scheme = optional_text(row.get("service_scheme"))
    if scheme is None or row.get("service_port") is None:
        return None
    origin = hostname or ip_address
    if not origin:
        return None
    port = int(row["service_port"])
    scheme = scheme.lower()
    return inventory_service_key(origin=origin, port=port, scheme=scheme), scheme, port


def _technology_names(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, Mapping):
        return sorted(str(key).strip().lower() for key, enabled in value.items() if enabled and str(key).strip())
    if isinstance(value, (list, tuple, set)):
        return sorted(str(item).strip().lower() for item in value if str(item).strip())
    text = optional_text(value)
    return [text.lower()] if text is not None else []
