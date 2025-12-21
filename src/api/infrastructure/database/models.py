"""SQLAlchemy ORM models with cross-database support"""
from sqlalchemy import (
    Column, String, Integer, Boolean, ForeignKey, Text, 
    UniqueConstraint, Index, CheckConstraint
)
from sqlalchemy.orm import declarative_base
import uuid

# Import custom types for cross-database compatibility
from ...infrastructure.database.types import UUID, JSONType, ArrayType

Base = declarative_base()


# ==================== TYPE TABLES ====================

class VulnTypeModel(Base):
    __tablename__ = "vuln_types"
    
    id = Column(UUID(), primary_key=True, default=uuid.uuid4)
    code = Column(String(50), unique=True, nullable=False, index=True)
    severity = Column(String(20), nullable=False)
    category = Column(String(50), nullable=False)


class LeakTypeModel(Base):
    __tablename__ = "leak_types"
    
    id = Column(UUID(), primary_key=True, default=uuid.uuid4)
    code = Column(String(50), unique=True, nullable=False, index=True)
    severity = Column(String(20), nullable=False)
    category = Column(String(50), nullable=False)


# ==================== CORE TABLES ====================

class ProgramModel(Base):
    __tablename__ = "programs"
    
    id = Column(UUID(), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), unique=True, nullable=False, index=True)


class ScopeRuleModel(Base):
    __tablename__ = "scope_rules"
    
    id = Column(UUID(), primary_key=True, default=uuid.uuid4)
    program_id = Column(UUID(), ForeignKey("programs.id", ondelete="CASCADE"), nullable=False, index=True)
    rule_type = Column(String(20), nullable=False)
    pattern = Column(String(500), nullable=False)


class RootInputModel(Base):
    __tablename__ = "root_inputs"
    
    id = Column(UUID(), primary_key=True, default=uuid.uuid4)
    program_id = Column(UUID(), ForeignKey("programs.id", ondelete="CASCADE"), nullable=False, index=True)
    value = Column(String(500), nullable=False)
    input_type = Column(String(20), nullable=False)


class HostModel(Base):
    __tablename__ = "hosts"
    
    id = Column(UUID(), primary_key=True, default=uuid.uuid4)
    program_id = Column(UUID(), ForeignKey("programs.id", ondelete="CASCADE"), nullable=False, index=True)
    host = Column(String(500), nullable=False)
    in_scope = Column(Boolean, default=True, nullable=False)
    cname = Column(JSONType(), default=list)
    
    __table_args__ = (
        UniqueConstraint('program_id', 'host', name='uq_host_program_host'),
        Index('idx_host_lookup', 'program_id', 'host'),
    )


class IPAddressModel(Base):
    __tablename__ = "ip_addresses"
    
    id = Column(UUID(), primary_key=True, default=uuid.uuid4)
    program_id = Column(UUID(), ForeignKey("programs.id", ondelete="CASCADE"), nullable=False, index=True)
    address = Column(String(45), nullable=False)
    in_scope = Column(Boolean, default=True, nullable=False)
    
    __table_args__ = (
        UniqueConstraint('program_id', 'address', name='uq_ip_program_address'),
        Index('idx_ip_lookup', 'program_id', 'address'),
    )


class HostIPModel(Base):
    __tablename__ = "host_ips"
    
    id = Column(UUID(), primary_key=True, default=uuid.uuid4)
    host_id = Column(UUID(), ForeignKey("hosts.id", ondelete="CASCADE"), nullable=False, index=True)
    ip_id = Column(UUID(), ForeignKey("ip_addresses.id", ondelete="CASCADE"), nullable=False, index=True)
    source = Column(String(100), nullable=False)
    
    __table_args__ = (
        UniqueConstraint('host_id', 'ip_id', name='uq_host_ip'),
        Index('idx_host_ip_lookup', 'host_id', 'ip_id'),
    )


class ServiceModel(Base):
    __tablename__ = "services"
    
    id = Column(UUID(), primary_key=True, default=uuid.uuid4)
    ip_id = Column(UUID(), ForeignKey("ip_addresses.id", ondelete="CASCADE"), nullable=False, index=True)
    scheme = Column(String(20), nullable=False)
    port = Column(Integer, nullable=False)
    technologies = Column(JSONType(), default=dict)
    
    __table_args__ = (
        UniqueConstraint('ip_id', 'port', name='uq_service_ip_port'),
        Index('idx_service_lookup', 'ip_id', 'port'),
    )


class EndpointModel(Base):
    __tablename__ = "endpoints"
    
    id = Column(UUID(), primary_key=True, default=uuid.uuid4)
    service_id = Column(UUID(), ForeignKey("services.id", ondelete="CASCADE"), nullable=False, index=True)
    host_id = Column(UUID(), ForeignKey("hosts.id", ondelete="CASCADE"), nullable=False, index=True)
    path = Column(Text, nullable=False)
    methods = Column(ArrayType(String), nullable=False, default=list)  # Array of methods
    status_code = Column(Integer, default=200)
    normalized_path = Column(Text, nullable=False)
    
    __table_args__ = (
        UniqueConstraint('host_id', 'path', name='uq_endpoint_host_path'),
        Index('idx_endpoint_lookup', 'host_id', 'normalized_path'),
        Index('idx_endpoint_service', 'service_id'),
    )


# ==================== ENRICHMENT TABLES ====================

class InputParameterModel(Base):
    __tablename__ = "input_parameters"
    
    id = Column(UUID(), primary_key=True, default=uuid.uuid4)
    endpoint_id = Column(UUID(), ForeignKey("endpoints.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    location = Column(String(20), nullable=False)  # query, body, path, header, cookie
    param_type = Column(String(20), nullable=False)
    reflected = Column(Boolean, default=False)
    is_array = Column(Boolean, default=False)
    
    __table_args__ = (
        UniqueConstraint('endpoint_id', 'location', 'name', name='uq_param_endpoint_location_name'),
        Index('idx_param_lookup', 'endpoint_id', 'location', 'name'),
    )


class HeaderModel(Base):
    __tablename__ = "headers"
    
    id = Column(UUID(), primary_key=True, default=uuid.uuid4)
    endpoint_id = Column(UUID(), ForeignKey("endpoints.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    value = Column(Text)
    header_type = Column(String(20), nullable=False)  # request, response
    
    __table_args__ = (
        UniqueConstraint('endpoint_id', 'name', 'header_type', name='uq_header_endpoint_name_type'),
        Index('idx_header_lookup', 'endpoint_id', 'name', 'header_type'),
        CheckConstraint("header_type IN ('request', 'response')", name='ck_header_type'),
    )


# ==================== SCANNER TABLES ====================

class ScannerTemplateModel(Base):
    __tablename__ = "scanner_templates"
    
    id = Column(UUID(), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    scanner = Column(String(100), nullable=False, index=True)
    template_yaml = Column(Text, nullable=False) 


class ScannerExecutionModel(Base):
    __tablename__ = "scanner_executions"
    
    id = Column(UUID(), primary_key=True, default=uuid.uuid4)
    template_id = Column(UUID(), ForeignKey("scanner_templates.id", ondelete="CASCADE"), nullable=False, index=True)
    endpoint_id = Column(UUID(), ForeignKey("endpoints.id", ondelete="CASCADE"), nullable=False, index=True)
    status = Column(String(20), nullable=False, index=True)
    started_at = Column(String(50))
    finished_at = Column(String(50))


class PayloadModel(Base):
    __tablename__ = "payloads"
    
    id = Column(UUID(), primary_key=True, default=uuid.uuid4)
    payload = Column(Text, nullable=False)
    category = Column(String(100), nullable=False, index=True)
    risk_level = Column(Integer, default=1)


# ==================== RESULTS TABLES ====================

class FindingModel(Base):
    __tablename__ = "findings"
    
    id = Column(UUID(), primary_key=True, default=uuid.uuid4)
    endpoint_id = Column(UUID(), ForeignKey("endpoints.id", ondelete="CASCADE"), nullable=False, index=True)
    vuln_type_id = Column(UUID(), ForeignKey("vuln_types.id", ondelete="CASCADE"), nullable=False, index=True)
    param_id = Column(UUID(), ForeignKey("input_parameters.id", ondelete="SET NULL"), nullable=True)
    payload_id = Column(UUID(), ForeignKey("payloads.id", ondelete="SET NULL"), nullable=True)
    execution_id = Column(UUID(), ForeignKey("scanner_executions.id", ondelete="SET NULL"), nullable=True)
    state = Column(String(20), nullable=False, index=True)
    evidence = Column(JSONType(), default=dict)


class LeakModel(Base):
    __tablename__ = "leaks"
    
    id = Column(UUID(), primary_key=True, default=uuid.uuid4)
    endpoint_id = Column(UUID(), ForeignKey("endpoints.id", ondelete="CASCADE"), nullable=False, index=True)
    leak_type_id = Column(UUID(), ForeignKey("leak_types.id", ondelete="CASCADE"), nullable=False, index=True)
    hash = Column(String(64), nullable=False, unique=True, index=True)
    location = Column(String(50), nullable=False)
    verified = Column(Boolean, default=False)