"""Domain entities - Pure business objects without framework dependencies"""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional, Dict, Any
from uuid import UUID, uuid4


# ==================== ENUMS ====================

class RuleType(str, Enum):
    """Scope rule types"""
    DOMAIN = "domain"
    IP_RANGE = "ip_range"
    REGEX = "regex"


class InputType(str, Enum):
    """Root input types"""
    DOMAIN = "domain"
    IP = "ip"
    URL = "url"


class HttpMethod(str, Enum):
    """HTTP methods"""
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    DELETE = "DELETE"
    PATCH = "PATCH"
    HEAD = "HEAD"
    OPTIONS = "OPTIONS"


class ParamLocation(str, Enum):
    """Parameter locations"""
    QUERY = "query"
    BODY = "body"
    HEADER = "header"
    COOKIE = "cookie"
    PATH = "path"


class Severity(str, Enum):
    """Vulnerability severity levels"""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class ScanStatus(str, Enum):
    """Scan execution status"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# ==================== CORE ENTITIES ====================

@dataclass
class Program:
    """Bug bounty program"""
    name: str
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class ScopeRule:
    """Program scope rule"""
    program_id: UUID
    rule_type: RuleType
    pattern: str
    id: UUID = field(default_factory=uuid4)


@dataclass
class RootInput:
    """Program root input (seed target)"""
    program_id: UUID
    value: str
    input_type: InputType
    id: UUID = field(default_factory=uuid4)


@dataclass
class Host:
    """Discovered host/domain"""
    program_id: UUID
    host: str
    in_scope: bool = True
    cname: List[str] = field(default_factory=list)
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class IPAddress:
    """IP address"""
    program_id: UUID
    address: str
    in_scope: bool = True
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class HostIP:
    """Host to IP mapping"""
    host_id: UUID
    ip_id: UUID
    source: str  # Tool that discovered this mapping
    id: UUID = field(default_factory=uuid4)


@dataclass
class Service:
    """Network service (HTTP/HTTPS endpoint)"""
    ip_id: UUID
    scheme: str  # http/https
    port: int
    technologies: Dict[str, bool] = field(default_factory=dict)  # {"nginx": True, "php": True}
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class Endpoint:
    """HTTP endpoint"""
    host_id: UUID
    service_id: UUID
    path: str
    normalized_path: str
    methods: List[str] = field(default_factory=list)  # ["GET", "POST"]
    status_code: Optional[int] = None
    content_length: Optional[int] = None
    title: Optional[str] = None
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class InputParameter:
    """Input parameter (query/body/header)"""
    endpoint_id: UUID
    name: str
    location: ParamLocation
    param_type: str = "string"  # string, int, bool, array, object
    reflected: bool = False
    is_array: bool = False
    example_value: Optional[str] = None
    id: UUID = field(default_factory=uuid4)


@dataclass
class Header:
    """HTTP response header"""
    endpoint_id: UUID
    name: str
    value: str
    id: UUID = field(default_factory=uuid4)


# ==================== VULNERABILITY TYPES ====================

@dataclass
class VulnType:
    """Vulnerability type definition"""
    code: str
    severity: Severity
    category: str
    id: UUID = field(default_factory=uuid4)


@dataclass
class LeakType:
    """Information leak type definition"""
    code: str
    severity: Severity
    category: str
    id: UUID = field(default_factory=uuid4)


# ==================== SCANNING ====================

@dataclass
class ScannerTemplate:
    """Scanner configuration template"""
    name: str
    tool: str
    command_template: str
    category: str
    enabled: bool = True
    id: UUID = field(default_factory=uuid4)


@dataclass
class ScannerExecution:
    """Scan execution record"""
    scanner_id: UUID
    target: str
    status: ScanStatus
    started_at: datetime
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    results_count: int = 0
    id: UUID = field(default_factory=uuid4)


@dataclass
class Payload:
    """Attack payload"""
    vuln_type_id: UUID
    payload: str
    description: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    id: UUID = field(default_factory=uuid4)


# ==================== RESULTS ====================

@dataclass
class Finding:
    """Vulnerability finding"""
    program_id: UUID
    vuln_type_id: UUID
    endpoint_id: Optional[UUID]
    parameter_id: Optional[UUID]
    severity: Severity
    title: str
    description: str
    evidence: Dict[str, Any] = field(default_factory=dict)
    cvss_score: Optional[float] = None
    verified: bool = False
    false_positive: bool = False
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class Leak:
    """Information leak"""
    program_id: UUID
    leak_type_id: UUID
    endpoint_id: Optional[UUID]
    severity: Severity
    content: str
    context: Dict[str, Any] = field(default_factory=dict)
    verified: bool = False
    false_positive: bool = False
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=datetime.utcnow)
