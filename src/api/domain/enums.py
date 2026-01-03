from enum import Enum, auto


class ScopeAction(str, Enum):
    """Scope rule action"""
    INCLUDE = "include"
    EXCLUDE = "exclude"


class RuleType(str, Enum):
    """Scope rule match types"""
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
