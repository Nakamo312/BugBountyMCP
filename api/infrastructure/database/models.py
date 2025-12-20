"""SQLAlchemy ORM models"""
from sqlalchemy import Column, String, Integer, Boolean, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import declarative_base, relationship
import uuid

Base = declarative_base()


# ==================== TYPE TABLES ====================

class VulnTypeModel(Base):
    __tablename__ = "vuln_types"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code = Column(String(50), unique=True, nullable=False, index=True)
    severity = Column(String(20), nullable=False)
    category = Column(String(50), nullable=False)


class LeakTypeModel(Base):
    __tablename__ = "leak_types"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code = Column(String(50), unique=True, nullable=False, index=True)
    severity = Column(String(20), nullable=False)
    category = Column(String(50), nullable=False)


# ==================== CORE TABLES ====================

class ProgramModel(Base):
    __tablename__ = "programs"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), unique=True, nullable=False, index=True)


class ScopeRuleModel(Base):
    __tablename__ = "scope_rules"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    program_id = Column(UUID(as_uuid=True), ForeignKey("programs.id", ondelete="CASCADE"), nullable=False, index=True)
    rule_type = Column(String(20), nullable=False)
    pattern = Column(String(500), nullable=False)


class RootInputModel(Base):
    __tablename__ = "root_inputs"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    program_id = Column(UUID(as_uuid=True), ForeignKey("programs.id", ondelete="CASCADE"), nullable=False, index=True)
    value = Column(String(500), nullable=False)
    input_type = Column(String(20), nullable=False)


class HostModel(Base):
    __tablename__ = "hosts"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    program_id = Column(UUID(as_uuid=True), ForeignKey("programs.id", ondelete="CASCADE"), nullable=False, index=True)
    host = Column(String(500), nullable=False, index=True)
    in_scope = Column(Boolean, default=True, nullable=False)


class IPAddressModel(Base):
    __tablename__ = "ip_addresses"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    program_id = Column(UUID(as_uuid=True), ForeignKey("programs.id", ondelete="CASCADE"), nullable=False, index=True)
    address = Column(String(45), nullable=False, index=True)
    version = Column(String(10), nullable=False)
    in_scope = Column(Boolean, default=True, nullable=False)


class HostIPModel(Base):
    __tablename__ = "host_ips"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    host_id = Column(UUID(as_uuid=True), ForeignKey("hosts.id", ondelete="CASCADE"), nullable=False, index=True)
    ip_id = Column(UUID(as_uuid=True), ForeignKey("ip_addresses.id", ondelete="CASCADE"), nullable=False, index=True)
    source = Column(String(100), nullable=False)


class ServiceModel(Base):
    __tablename__ = "services"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ip_id = Column(UUID(as_uuid=True), ForeignKey("ip_addresses.id", ondelete="CASCADE"), nullable=False, index=True)
    scheme = Column(String(20), nullable=False)
    port = Column(Integer, nullable=False)
    technologies = Column(JSONB, default={})


class EndpointModel(Base):
    __tablename__ = "endpoints"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    service_id = Column(UUID(as_uuid=True), ForeignKey("services.id", ondelete="CASCADE"), nullable=False, index=True)
    host_id = Column(UUID(as_uuid=True), ForeignKey("hosts.id", ondelete="CASCADE"), nullable=False, index=True)
    path = Column(Text, nullable=False)
    method = Column(String(10), nullable=False)
    status_code = Column(Integer, default=200)
    normalized_path = Column(Text, nullable=False, index=True)


# ==================== ENRICHMENT TABLES ====================

class InputParameterModel(Base):
    __tablename__ = "input_parameters"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    endpoint_id = Column(UUID(as_uuid=True), ForeignKey("endpoints.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    location = Column(String(20), nullable=False)
    param_type = Column(String(20), nullable=False)
    reflected = Column(Boolean, default=False)
    is_array = Column(Boolean, default=False)


class HeaderModel(Base):
    __tablename__ = "headers"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    endpoint_id = Column(UUID(as_uuid=True), ForeignKey("endpoints.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    value = Column(Text)


# ==================== SCANNER TABLES ====================

class ScannerTemplateModel(Base):
    __tablename__ = "scanner_templates"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    scanner = Column(String(100), nullable=False, index=True)
    metadata = Column(JSONB, default={})


class ScannerExecutionModel(Base):
    __tablename__ = "scanner_executions"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    template_id = Column(UUID(as_uuid=True), ForeignKey("scanner_templates.id", ondelete="CASCADE"), nullable=False, index=True)
    endpoint_id = Column(UUID(as_uuid=True), ForeignKey("endpoints.id", ondelete="CASCADE"), nullable=False, index=True)
    status = Column(String(20), nullable=False, index=True)
    started_at = Column(String(50))
    finished_at = Column(String(50))


class PayloadModel(Base):
    __tablename__ = "payloads"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    payload = Column(Text, nullable=False)
    category = Column(String(100), nullable=False, index=True)
    risk_level = Column(Integer, default=1)


# ==================== RESULTS TABLES ====================

class FindingModel(Base):
    __tablename__ = "findings"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    endpoint_id = Column(UUID(as_uuid=True), ForeignKey("endpoints.id", ondelete="CASCADE"), nullable=False, index=True)
    vuln_type_id = Column(UUID(as_uuid=True), ForeignKey("vuln_types.id", ondelete="CASCADE"), nullable=False, index=True)
    param_id = Column(UUID(as_uuid=True), ForeignKey("input_parameters.id", ondelete="SET NULL"), nullable=True)
    payload_id = Column(UUID(as_uuid=True), ForeignKey("payloads.id", ondelete="SET NULL"), nullable=True)
    execution_id = Column(UUID(as_uuid=True), ForeignKey("scanner_executions.id", ondelete="SET NULL"), nullable=True)
    state = Column(String(20), nullable=False, index=True)
    evidence = Column(JSONB, default={})


class LeakModel(Base):
    __tablename__ = "leaks"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    endpoint_id = Column(UUID(as_uuid=True), ForeignKey("endpoints.id", ondelete="CASCADE"), nullable=False, index=True)
    leak_type_id = Column(UUID(as_uuid=True), ForeignKey("leak_types.id", ondelete="CASCADE"), nullable=False, index=True)
    hash = Column(String(64), nullable=False, unique=True, index=True)
    location = Column(String(50), nullable=False)
    verified = Column(Boolean, default=False)
    metadata = Column(JSONB, default={})
