"""Mapper configuration for SQLAlchemy Core tables to domain models"""
from sqlalchemy.orm import registry, relationship

from api.domain.models import (ASNModel, CIDRModel, DNSRecordModel,
                               EndpointModel, FindingModel, HeaderModel,
                               HostIPModel, HostModel, InputParameterModel,
                               IPAddressModel, LeakModel,
                               OrganizationModel, PayloadModel, ProgramModel,
                               RawBodyModel, RootInputModel, ScannerExecutionModel,
                               ScannerTemplateModel, ScopeRuleModel,
                               ServiceModel, VulnTypeModel)
from api.infrastructure.adapters.orm import (asns, cidrs, dns_records,
                                             endpoints, findings, headers,
                                             host_ips, hosts, input_parameters,
                                             ip_addresses, leaks, metadata,
                                             organizations, payloads, programs,
                                             raw_body, root_inputs, scanner_executions,
                                             scanner_templates, scope_rules,
                                             services, vuln_types)

mapper_registry = registry(metadata=metadata)

def start_mappers():
    mapper_registry.map_imperatively(
        class_=ProgramModel,
        local_table=programs,
        properties={
            'scope_rules': relationship(
                ScopeRuleModel,
                backref='program',
                cascade='all, delete-orphan',
                lazy='select'
            ),
            'root_inputs': relationship(
                RootInputModel,
                backref='program',
                cascade='all, delete-orphan',
                lazy='select'
            ),
            'hosts': relationship(
                HostModel,
                backref='program',
                cascade='all, delete-orphan',
                lazy='select'
            ),
            'ip_addresses': relationship(
                IPAddressModel,
                backref='program',
                cascade='all, delete-orphan',
                lazy='select'
            ),
            'findings': relationship(
                FindingModel,
                backref='program',
                cascade='all, delete-orphan',
                lazy='select'
            ),
            'leaks': relationship(
                LeakModel,
                backref='program',
                cascade='all, delete-orphan',
                lazy='select'
            ),
        }
    )

    mapper_registry.map_imperatively(
        class_=ScopeRuleModel,
        local_table=scope_rules
    )

    mapper_registry.map_imperatively(
        class_=RootInputModel,
        local_table=root_inputs
    )

    mapper_registry.map_imperatively(
        class_=HostModel,
        local_table=hosts,
        properties={
            'ips': relationship(
                IPAddressModel,
                secondary=host_ips,
                backref='hosts',
                lazy='select',
                overlaps="hosts,ips"
            ),
            'endpoints': relationship(
                EndpointModel,
                backref='host',
                cascade='all, delete-orphan',
                lazy='select'
            ),
            'input_parameters': relationship(
                InputParameterModel,
                secondary=endpoints,
                primaryjoin=(hosts.c.id == endpoints.c.host_id),
                secondaryjoin=(endpoints.c.id == input_parameters.c.endpoint_id),
                viewonly=True,
                lazy='select'
            ),
            'dns_records': relationship(
                DNSRecordModel,
                backref='host',
                cascade='all, delete-orphan',
                lazy='select'
            ),
        }
    )

    mapper_registry.map_imperatively(
        class_=IPAddressModel,
        local_table=ip_addresses,
        properties={
            'services': relationship(
                ServiceModel,
                backref='ip',
                cascade='all, delete-orphan',
                lazy='select'
            ),
        }
    )

    mapper_registry.map_imperatively(
        class_=HostIPModel,
        local_table=host_ips,
        properties={
            'host': relationship(
                HostModel,
                foreign_keys=[host_ips.c.host_id],
                lazy='select',
                overlaps="host_ip_links,hosts,ips"
            ),
            'ip': relationship(
                IPAddressModel,
                foreign_keys=[host_ips.c.ip_id],
                lazy='select',
                overlaps="host_ip_links,hosts,ips"
            ),
        }
    )

    mapper_registry.map_imperatively(
        class_=ServiceModel,
        local_table=services,
        properties={
            'endpoints': relationship(
                EndpointModel,
                backref='service',
                cascade='all, delete-orphan',
                lazy='select'
            ),
            'input_parameters': relationship(
                InputParameterModel,
                backref='service',
                cascade='all, delete-orphan',
                lazy='select'
            ),
        }
    )

    mapper_registry.map_imperatively(
        class_=EndpointModel,
        local_table=endpoints,
        properties={
            'input_parameters': relationship(
                InputParameterModel,
                backref='endpoint',
                cascade='all, delete-orphan',
                lazy='select'
            ),
            'headers': relationship(
                HeaderModel,
                backref='endpoint',
                cascade='all, delete-orphan',
                lazy='select'
            ),
            'raw_bodies': relationship(
                RawBodyModel,
                backref='endpoint',
                cascade='all, delete-orphan',
                lazy='select'
            ),
            'findings': relationship(
                FindingModel,
                backref='endpoint',
                cascade='all, delete-orphan',
                lazy='select'
            ),
            'leaks': relationship(
                LeakModel,
                backref='endpoint',
                cascade='all, delete-orphan',
                lazy='select'
            ),
            'scanner_executions': relationship(
                ScannerExecutionModel,
                backref='endpoint',
                cascade='all, delete-orphan',
                lazy='select'
            ),
        }
    )

    mapper_registry.map_imperatively(
        class_=InputParameterModel,
        local_table=input_parameters,
        properties={
            'findings': relationship(
                FindingModel,
                backref='parameter',
                cascade='all, delete-orphan',
                lazy='select'
            ),
        }
    )

    mapper_registry.map_imperatively(
        class_=HeaderModel,
        local_table=headers
    )

    mapper_registry.map_imperatively(
        class_=RawBodyModel,
        local_table=raw_body
    )

    mapper_registry.map_imperatively(
        class_=VulnTypeModel,
        local_table=vuln_types,
        properties={
            'payloads': relationship(
                PayloadModel,
                backref='vuln_type',
                cascade='all, delete-orphan',
                lazy='select'
            ),
            'findings': relationship(
                FindingModel,
                backref='vuln_type',
                cascade='all, delete-orphan',
                lazy='select'
            ),
        }
    )

    mapper_registry.map_imperatively(
        class_=ScannerTemplateModel,
        local_table=scanner_templates,
        properties={
            'executions': relationship(
                ScannerExecutionModel,
                backref='template',
                cascade='all, delete-orphan',
                lazy='select'
            ),
        }
    )

    mapper_registry.map_imperatively(
        class_=ScannerExecutionModel,
        local_table=scanner_executions,
        properties={
            'findings': relationship(
                FindingModel,
                backref='execution',
                cascade='all, delete-orphan',
                lazy='select'
            ),
        }
    )

    mapper_registry.map_imperatively(
        class_=PayloadModel,
        local_table=payloads,
        properties={
            'findings': relationship(
                FindingModel,
                backref='payload',
                cascade='all, delete-orphan',
                lazy='select'
            ),
        }
    )

    mapper_registry.map_imperatively(
        class_=FindingModel,
        local_table=findings
    )

    mapper_registry.map_imperatively(
        class_=LeakModel,
        local_table=leaks
    )

    mapper_registry.map_imperatively(
        class_=DNSRecordModel,
        local_table=dns_records
    )

    mapper_registry.map_imperatively(
        class_=OrganizationModel,
        local_table=organizations,
        properties={
            'asns': relationship(
                ASNModel,
                backref='organization',
                cascade='all, delete-orphan',
                lazy='select'
            ),
        }
    )

    mapper_registry.map_imperatively(
        class_=ASNModel,
        local_table=asns,
        properties={
            'cidrs': relationship(
                CIDRModel,
                backref='asn',
                cascade='all, delete-orphan',
                lazy='select'
            ),
        }
    )

    mapper_registry.map_imperatively(
        class_=CIDRModel,
        local_table=cidrs
    )

def get_mapped_classes():
    return {
        ProgramModel,
        ScopeRuleModel,
        RootInputModel,
        HostModel,
        IPAddressModel,
        HostIPModel,
        ServiceModel,
        EndpointModel,
        InputParameterModel,
        HeaderModel,
        VulnTypeModel,
        ScannerTemplateModel,
        ScannerExecutionModel,
        PayloadModel,
        FindingModel,
        LeakModel,
        DNSRecordModel,
    }

def get_metadata():
    return metadata