"""Domain layer - Pure business logic without dependencies"""

from .entities import (
    # Enums
    RuleType,
    InputType,
    HttpMethod,
    ParamLocation,
    Severity,
    ScanStatus,
    
    # Core entities
    Program,
    ScopeRule,
    RootInput,
    Host,
    IPAddress,
    HostIP,
    Service,
    Endpoint,
    InputParameter,
    Header,
    
    # Types
    VulnType,
    LeakType,
    
    # Scanning
    ScannerTemplate,
    ScannerExecution,
    Payload,
    
    # Results
    Finding,
    Leak,
)

from .repositories import (
    IBaseRepository,
    IProgramRepository,
    IScopeRuleRepository,
    IRootInputRepository,
    IHostRepository,
    IIPAddressRepository,
    IHostIPRepository,
    IServiceRepository,
    IEndpointRepository,
    IInputParameterRepository,
    IHeaderRepository,
    IVulnTypeRepository,
    ILeakTypeRepository,
    IScannerTemplateRepository,
    IScannerExecutionRepository,
    IPayloadRepository,
    IFindingRepository,
    ILeakRepository,
)

__all__ = [
    # Enums
    "RuleType",
    "InputType",
    "HttpMethod",
    "ParamLocation",
    "Severity",
    "ScanStatus",
    
    # Entities
    "Program",
    "ScopeRule",
    "RootInput",
    "Host",
    "IPAddress",
    "HostIP",
    "Service",
    "Endpoint",
    "InputParameter",
    "Header",
    "VulnType",
    "LeakType",
    "ScannerTemplate",
    "ScannerExecution",
    "Payload",
    "Finding",
    "Leak",
    
    # Repository interfaces
    "IBaseRepository",
    "IProgramRepository",
    "IScopeRuleRepository",
    "IRootInputRepository",
    "IHostRepository",
    "IIPAddressRepository",
    "IHostIPRepository",
    "IServiceRepository",
    "IEndpointRepository",
    "IInputParameterRepository",
    "IHeaderRepository",
    "IVulnTypeRepository",
    "ILeakTypeRepository",
    "IScannerTemplateRepository",
    "IScannerExecutionRepository",
    "IPayloadRepository",
    "IFindingRepository",
    "ILeakRepository",
]
