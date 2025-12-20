"""Domain layer - enums and repository interfaces only"""

from .enums import (
    RuleType,
    InputType,
    IPVersion,
    HTTPMethod,
    ParamLocation,
    ParamType,
    Severity,
    FindingState,
    ScanStatus,
)

__all__ = [
    "RuleType",
    "InputType",
    "IPVersion",
    "HTTPMethod",
    "ParamLocation",
    "ParamType",
    "Severity",
    "FindingState",
    "ScanStatus",
]
