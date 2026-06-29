"""Legacy classical SQLAlchemy mapper configuration.

Most new persistence code in this project uses explicit Core stores. Keep this
module as a compatibility boundary for the older domain model mapping only; do
not add new orchestration/read-model entities here.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import registry, relationship

from api.domain.models import (
    ASNModel,
    CIDRModel,
    DNSRecordModel,
    EndpointModel,
    FindingModel,
    HeaderModel,
    HostIPModel,
    HostModel,
    HTTPObservationHeaderModel,
    HTTPObservationModel,
    InputParameterModel,
    IPAddressModel,
    JavaScriptReferenceModel,
    LeakModel,
    OrganizationModel,
    PayloadModel,
    ProgramModel,
    RawBodyModel,
    RootInputModel,
    ScannerExecutionModel,
    ScannerTemplateModel,
    ScopeRuleModel,
    ServiceModel,
    VulnTypeModel,
)
from api.infrastructure.adapters.orm import (
    asns,
    cidrs,
    dns_records,
    endpoints,
    findings,
    headers,
    host_ips,
    hosts,
    http_observation_headers,
    http_observations,
    input_parameters,
    ip_addresses,
    javascript_references,
    leaks,
    metadata,
    organizations,
    payloads,
    programs,
    raw_body,
    root_inputs,
    scanner_executions,
    scanner_templates,
    scope_rules,
    services,
    vuln_types,
)

mapper_registry = registry(metadata=metadata)

_CASCADE_DELETE = "all, delete-orphan"
_SELECT = "select"


@dataclass(frozen=True)
class MapperSpec:
    model: type
    table: Any
    properties: dict[str, Any] | None = None


def _owns(model: type, *, backref: str) -> Any:
    return relationship(model, backref=backref, cascade=_CASCADE_DELETE, lazy=_SELECT)


def _program_mapper_specs() -> tuple[MapperSpec, ...]:
    return (
        MapperSpec(
            ProgramModel,
            programs,
            {
                "scope_rules": _owns(ScopeRuleModel, backref="program"),
                "root_inputs": _owns(RootInputModel, backref="program"),
                "hosts": _owns(HostModel, backref="program"),
                "ip_addresses": _owns(IPAddressModel, backref="program"),
                "findings": _owns(FindingModel, backref="program"),
                "leaks": _owns(LeakModel, backref="program"),
            },
        ),
        MapperSpec(ScopeRuleModel, scope_rules),
        MapperSpec(RootInputModel, root_inputs),
    )


def _network_mapper_specs() -> tuple[MapperSpec, ...]:
    return (
        MapperSpec(
            HostModel,
            hosts,
            {
                "ips": relationship(
                    IPAddressModel,
                    secondary=host_ips,
                    backref="hosts",
                    lazy=_SELECT,
                    overlaps="hosts,ips",
                ),
                "endpoints": _owns(EndpointModel, backref="host"),
                "input_parameters": relationship(
                    InputParameterModel,
                    secondary=endpoints,
                    primaryjoin=(hosts.c.id == endpoints.c.host_id),
                    secondaryjoin=(endpoints.c.id == input_parameters.c.endpoint_id),
                    viewonly=True,
                    lazy=_SELECT,
                ),
                "dns_records": _owns(DNSRecordModel, backref="host"),
            },
        ),
        MapperSpec(IPAddressModel, ip_addresses, {"services": _owns(ServiceModel, backref="ip")}),
        MapperSpec(
            HostIPModel,
            host_ips,
            {
                "host": relationship(
                    HostModel,
                    foreign_keys=[host_ips.c.host_id],
                    lazy=_SELECT,
                    overlaps="host_ip_links,hosts,ips",
                ),
                "ip": relationship(
                    IPAddressModel,
                    foreign_keys=[host_ips.c.ip_id],
                    lazy=_SELECT,
                    overlaps="host_ip_links,hosts,ips",
                ),
            },
        ),
        MapperSpec(DNSRecordModel, dns_records),
    )


def _http_mapper_specs() -> tuple[MapperSpec, ...]:
    return (
        MapperSpec(
            ServiceModel,
            services,
            {
                "endpoints": _owns(EndpointModel, backref="service"),
                "input_parameters": _owns(InputParameterModel, backref="service"),
            },
        ),
        MapperSpec(
            EndpointModel,
            endpoints,
            {
                "input_parameters": _owns(InputParameterModel, backref="endpoint"),
                "headers": _owns(HeaderModel, backref="endpoint"),
                "raw_bodies": _owns(RawBodyModel, backref="endpoint"),
                "findings": _owns(FindingModel, backref="endpoint"),
                "leaks": _owns(LeakModel, backref="endpoint"),
                "scanner_executions": _owns(ScannerExecutionModel, backref="endpoint"),
            },
        ),
        MapperSpec(InputParameterModel, input_parameters, {"findings": _owns(FindingModel, backref="parameter")}),
        MapperSpec(HeaderModel, headers),
        MapperSpec(RawBodyModel, raw_body),
        MapperSpec(
            HTTPObservationModel,
            http_observations,
            {"headers": _owns(HTTPObservationHeaderModel, backref="observation")},
        ),
        MapperSpec(HTTPObservationHeaderModel, http_observation_headers),
        MapperSpec(JavaScriptReferenceModel, javascript_references),
    )


def _finding_mapper_specs() -> tuple[MapperSpec, ...]:
    return (
        MapperSpec(
            VulnTypeModel,
            vuln_types,
            {
                "payloads": _owns(PayloadModel, backref="vuln_type"),
                "findings": _owns(FindingModel, backref="vuln_type"),
            },
        ),
        MapperSpec(ScannerTemplateModel, scanner_templates, {"executions": _owns(ScannerExecutionModel, backref="template")}),
        MapperSpec(ScannerExecutionModel, scanner_executions, {"findings": _owns(FindingModel, backref="execution")}),
        MapperSpec(PayloadModel, payloads, {"findings": _owns(FindingModel, backref="payload")}),
        MapperSpec(FindingModel, findings),
        MapperSpec(LeakModel, leaks),
    )


def _organization_mapper_specs() -> tuple[MapperSpec, ...]:
    return (
        MapperSpec(OrganizationModel, organizations, {"asns": _owns(ASNModel, backref="organization")}),
        MapperSpec(ASNModel, asns, {"cidrs": _owns(CIDRModel, backref="asn")}),
        MapperSpec(CIDRModel, cidrs),
    )


def _mapper_specs() -> tuple[MapperSpec, ...]:
    return (
        *_program_mapper_specs(),
        *_network_mapper_specs(),
        *_http_mapper_specs(),
        *_finding_mapper_specs(),
        *_organization_mapper_specs(),
    )


def start_mappers() -> None:
    """Register legacy domain mappings with SQLAlchemy."""
    for spec in _mapper_specs():
        mapper_registry.map_imperatively(
            class_=spec.model,
            local_table=spec.table,
            properties=spec.properties,
        )


def get_mapped_classes():
    return {spec.model for spec in _mapper_specs()}


def get_metadata():
    return metadata
