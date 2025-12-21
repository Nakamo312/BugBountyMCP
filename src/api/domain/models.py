"""Domain entities - Pure business objects without framework dependencies"""
from abc import ABC
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional, Dict, Any, Set
from uuid import UUID, uuid4

from src.api.domain.enums import HttpMethod, InputType, ParamLocation, RuleType, ScanStatus, Severity


@dataclass
class AbstractModel(ABC):
    """
    Base model, from which any domain model should be inherited.
    """

    async def to_dict(
            self,
            exclude: Optional[Set[str]] = None,
            include: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:

        """
        Create a dictionary representation of the model.

        exclude: set of model fields, which should be excluded from dictionary representation.
        include: set of model fields, which should be included into dictionary representation.
        """

        data: Dict[str, Any] = asdict(self)
        if exclude:
            for key in exclude:
                try:
                    del data[key]
                except KeyError:
                    pass

        if include:
            data.update(include)

        return data

@dataclass
class ProgramModel(AbstractModel):
    """Bug bounty program"""
    name: str
    id: UUID = field(default_factory=uuid4)

@dataclass
class ScopeRuleModel(AbstractModel):
    """Program scope rule"""
    program_id: UUID
    rule_type: RuleType
    pattern: str
    id: UUID = field(default_factory=uuid4)


@dataclass
class RootInputModel(AbstractModel):
    """Program root input (seed target)"""
    program_id: UUID
    value: str
    input_type: InputType
    id: UUID = field(default_factory=uuid4)


@dataclass
class HostModel(AbstractModel):
    """Discovered host/domain"""
    program_id: UUID
    host: str
    in_scope: bool = True
    cname: List[str] = field(default_factory=list)
    id: UUID = field(default_factory=uuid4)


@dataclass
class IPAddressModel(AbstractModel):
    """IP address"""
    program_id: UUID
    address: str
    in_scope: bool = True
    id: UUID = field(default_factory=uuid4)


@dataclass
class HostIPModel(AbstractModel):
    """Host to IP mapping"""
    host_id: UUID
    ip_id: UUID
    source: str  
    id: UUID = field(default_factory=uuid4)


@dataclass
class ServiceModel(AbstractModel):
    """Network service (HTTP/HTTPS endpoint)"""
    ip_id: UUID
    scheme: str  # http/https
    port: int
    technologies: Dict[str, bool] = field(default_factory=dict)  # {"nginx": True, "php": True}
    id: UUID = field(default_factory=uuid4)


@dataclass
class EndpointModel(AbstractModel):
    """HTTP endpoint"""
    host_id: UUID
    service_id: UUID
    path: str
    normalized_path: str
    methods: List[HttpMethod] = field(default_factory=list)  # ["GET", "POST"]
    status_code: Optional[int] = None
    id: UUID = field(default_factory=uuid4)



@dataclass
class InputParameterModel(AbstractModel):
    """Input parameter (query/body/header)"""
    endpoint_id: UUID
    name: str
    location: ParamLocation
    param_type: str = "string"  # string, int, bool, array, object
    reflected: bool = False
    is_array: bool = False
    example_value: Optional[str] = None
    id: UUID = field(default_factory=uuid4)
    service_id: UUID
    


@dataclass
class HeaderModel(AbstractModel):
    """HTTP response header"""
    endpoint_id: UUID
    name: str
    value: str
    id: UUID = field(default_factory=uuid4)



@dataclass
class VulnTypeModel(AbstractModel):
    """Vulnerability type definition"""
    code: str
    severity: Severity
    category: str
    id: UUID = field(default_factory=uuid4)



@dataclass
class ScannerTemplateModel(AbstractModel):
    """Scanner configuration template"""
    name: str
    tool: str
    command_template: str
    category: str
    enabled: bool = True
    id: UUID = field(default_factory=uuid4)

@dataclass
class ScannerExecutionModel(AbstractModel):
    """Scan execution record"""
    program_id: str
    status: ScanStatus
    template_id: Optional[UUID]
    endpoint_id: UUID
    error_message: Optional[str] = None
    id: UUID = field(default_factory=uuid4)

@dataclass
class PayloadModel(AbstractModel):
    """Attack payload"""
    vuln_type_id: UUID
    payload: str
    description: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    id: UUID = field(default_factory=uuid4)

@dataclass
class FindingModel(AbstractModel):
    """Vulnerability finding"""
    program_id: UUID
    vuln_type_id: UUID
    endpoint_id: Optional[UUID]
    parameter_id: Optional[UUID]
    payload_id: Optional[UUID]
    execution_id: Optional[UUID]
    description: str
    evidence: Dict[str, Any] = field(default_factory=dict)
    verified: bool = False
    false_positive: bool = False
    id: UUID = field(default_factory=uuid4)


@dataclass
class LeakModel(AbstractModel):
    """Information leak"""
    program_id: UUID
    endpoint_id: Optional[UUID]
    content: str
    verified: bool = False
    false_positive: bool = False
    id: UUID = field(default_factory=uuid4)
