from enum import Enum


class ScopePolicy(str, Enum):
    NONE = "none"
    STRICT = "strict"
    CONFIDENCE = "confidence"
    APPROVAL_REQUIRED = "approval_required"

