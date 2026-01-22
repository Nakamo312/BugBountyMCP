from enum import Enum

class ScopePolicy(str, Enum):
    NONE = "none"                  # вообще не чекать
    STRICT = "strict"              # только in-scope
    CONFIDENCE = "confidence"      # считать confidence