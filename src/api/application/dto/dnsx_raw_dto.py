from typing import Any, Optional

from pydantic import BaseModel


class DNSxRawResultDTO(BaseModel):
    host: Optional[str] = None
    a: list[str] = []
    aaaa: list[str] = []
    cname: list[str] = []
    mx: list[str] = []
    txt: list[str] = []
    ns: list[str] = []
    soa: list[dict[str, Any]] = []
    ptr: list[str] = []
    ttl: Optional[int] = None
    timestamp: Optional[str] = None
    resolver: Optional[list[str]] = []
    wildcard: Optional[bool] = False
    status_code: Optional[str] = None
