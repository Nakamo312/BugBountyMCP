from dataclasses import dataclass
from typing import Dict, List, Optional

@dataclass(frozen=True)
class HTTPXResult:
    host: str
    primary_ip: str
    extra_ips: List[str]
    scheme: str
    port: int
    technologies: Dict[str, bool]
    path: str
    method: str
    status_code: Optional[int]
