"""API Data Transfer Objects and Schemas"""
from pydantic import BaseModel, Field
from typing import List, Union, Optional, Any


class SubfinderScanRequest(BaseModel):
    program_id: str = Field(..., description="Program UUID", example="123e4567-e89b-12d3-a456-426614174000")
    domain: str = Field(..., description="Target domain to scan", example="tesla.com")
    probe: bool = Field(True, description="Run HTTPX probe on discovered subdomains?")

class HTTPXScanRequest(BaseModel):
    program_id: str = Field(..., description="Program UUID")
    targets: Union[List[str], str] = Field(..., description="Single URL or list of URLs/domains", example=["https://google.com", "sub.example.com"])


class ErrorResponse(BaseModel):
    detail: str = Field(..., description="Error description")
    code: str = Field(..., description="Internal error code")

class ScanResponse(BaseModel):
    status: str = Field("started", description="Task status")
    message: str = Field(..., description="Human readable message")
    results: Optional[Any] = Field(None, description="Scan results (if available immediately)")