"""Mapper configuration for SQLAlchemy Core tables to domain models"""
from sqlalchemy.orm import registry

from api.domain.models import (
    ProgramModel, ScopeRuleModel, RootInputModel, HostModel,
    IPAddressModel, HostIPModel, ServiceModel, EndpointModel,
    InputParameterModel, HeaderModel, VulnTypeModel,
    ScannerTemplateModel, ScannerExecutionModel, PayloadModel,
    FindingModel, LeakModel
)

from api.infrastructure.adapters.orm import (
    metadata, programs, scope_rules, root_inputs, hosts, ip_addresses,
    host_ips, services, endpoints, input_parameters, headers,
    vuln_types, scanner_templates, scanner_executions, payloads,
    findings, leaks
)

# Create mapper registry
mapper_registry = registry(metadata=metadata)


def start_mappers():
    """
    Map all domain models to ORM models, for purpose of using domain models directly during work with the database,
    according to DDD.
    """

    # ==================== CORE ENTITIES ====================

    mapper_registry.map_imperatively(
        class_=ProgramModel,
        local_table=programs,
        properties={
            'scope_rules': mapper_registry.relationship(
                ScopeRuleModel,
                backref='program',
                cascade='all, delete-orphan',
                lazy='select'
            ),
            'root_inputs': mapper_registry.relationship(
                RootInputModel,
                backref='program',
                cascade='all, delete-orphan',
                lazy='select'
            ),
            'hosts': mapper_registry.relationship(
                HostModel,
                backref='program',
                cascade='all, delete-orphan',
                lazy='select'
            ),
            'ip_addresses': mapper_registry.relationship(
                IPAddressModel,
                backref='program',
                cascade='all, delete-orphan',
                lazy='select'
            ),
            'findings': mapper_registry.relationship(
                FindingModel,
                backref='program',
                cascade='all, delete-orphan',
                lazy='select'
            ),
            'leaks': mapper_registry.relationship(
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
            'ips': mapper_registry.relationship(
                IPAddressModel,
                secondary=host_ips,
                backref='hosts',
                lazy='select'
            ),
            'endpoints': mapper_registry.relationship(
                EndpointModel,
                backref='host',
                cascade='all, delete-orphan',
                lazy='select'
            ),
            'input_parameters': mapper_registry.relationship(
                InputParameterModel,
                secondary=endpoints,  # Through endpoints
                primaryjoin=(hosts.c.id == endpoints.c.host_id),
                secondaryjoin=(endpoints.c.id == input_parameters.c.endpoint_id),
                viewonly=True,
                lazy='select'
            ),
        }
    )

    mapper_registry.map_imperatively(
        class_=IPAddressModel,
        local_table=ip_addresses,
        properties={
            'services': mapper_registry.relationship(
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
            'host': mapper_registry.relationship(
                HostModel,
                backref='host_ip_links',
                lazy='select'
            ),
            'ip': mapper_registry.relationship(
                IPAddressModel,
                backref='host_ip_links',
                lazy='select'
            ),
        }
    )

    mapper_registry.map_imperatively(
        class_=ServiceModel,
        local_table=services,
        properties={
            'endpoints': mapper_registry.relationship(
                EndpointModel,
                backref='service',
                cascade='all, delete-orphan',
                lazy='select'
            ),
            'input_parameters': mapper_registry.relationship(
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
            'input_parameters': mapper_registry.relationship(
                InputParameterModel,
                backref='endpoint',
                cascade='all, delete-orphan',
                lazy='select'
            ),
            'headers': mapper_registry.relationship(
                HeaderModel,
                backref='endpoint',
                cascade='all, delete-orphan',
                lazy='select'
            ),
            'findings': mapper_registry.relationship(
                FindingModel,
                backref='endpoint',
                cascade='all, delete-orphan',
                lazy='select'
            ),
            'leaks': mapper_registry.relationship(
                LeakModel,
                backref='endpoint',
                cascade='all, delete-orphan',
                lazy='select'
            ),
            'scanner_executions': mapper_registry.relationship(
                ScannerExecutionModel,
                backref='endpoint',
                cascade='all, delete-orphan',
                lazy='select'
            ),
        }
    )

    # ==================== ENRICHMENT ENTITIES ====================

    mapper_registry.map_imperatively(
        class_=InputParameterModel,
        local_table=input_parameters,
        properties={
            'findings': mapper_registry.relationship(
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

    # ==================== TYPE ENTITIES ====================

    mapper_registry.map_imperatively(
        class_=VulnTypeModel,
        local_table=vuln_types,
        properties={
            'payloads': mapper_registry.relationship(
                PayloadModel,
                backref='vuln_type',
                cascade='all, delete-orphan',
                lazy='select'
            ),
            'findings': mapper_registry.relationship(
                FindingModel,
                backref='vuln_type',
                cascade='all, delete-orphan',
                lazy='select'
            ),
        }
    )

    # ==================== SCANNER ENTITIES ====================

    mapper_registry.map_imperatively(
        class_=ScannerTemplateModel,
        local_table=scanner_templates,
        properties={
            'executions': mapper_registry.relationship(
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
            'findings': mapper_registry.relationship(
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
            'findings': mapper_registry.relationship(
                FindingModel,
                backref='payload',
                cascade='all, delete-orphan',
                lazy='select'
            ),
        }
    )

    # ==================== RESULTS ENTITIES ====================

    mapper_registry.map_imperatively(
        class_=FindingModel,
        local_table=findings
    )

    mapper_registry.map_imperatively(
        class_=LeakModel,
        local_table=leaks
    )


# Convenience function to get all mapped classes
def get_mapped_classes():
    """Return all mapped domain model classes"""
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
    }


# For Alembic autogenerate support
def get_metadata():
    """Return metadata for Alembic"""
    return metadata