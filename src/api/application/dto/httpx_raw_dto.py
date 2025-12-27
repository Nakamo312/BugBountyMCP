from pydantic import BaseModel
from typing import List, Optional

class HTTPXRawResultDTO(BaseModel):
    host: Optional[str] = None
    input: Optional[str] = None
    host_ip: Optional[str] = None
    a: List[str] = []
    scheme: str = "http"
    port: int = 80
    tech: List[str] = []
    path: str = "/"
    method: str = "GET"
    status_code: Optional[int] = None
