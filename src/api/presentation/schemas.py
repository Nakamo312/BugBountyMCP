"""Presentation layer schemas - API request/response models"""
from typing import Union, List, Optional
from uuid import UUID
from pydantic import BaseModel, Field


# Request Schemas
class HTTPXScanRequest(BaseModel):
    """HTTP request schema for HTTPX scan"""
    program_id: str = Field(..., description="Program UUID as string")
    targets: Union[str, List[str]] = Field(..., description="Single target or list")
    timeout: Optional[int] = Field(default=600, ge=1, le=3600)
    
    class Config:
        json_schema_extra = {
            "example": {
                "program_id": "123e4567-e89b-12d3-a456-426614174000",
                "targets": ["https://example.com"],
                "timeout": 600
            }
        }


class SubfinderScanRequest(BaseModel):
    """HTTP request schema for Subfinder scan"""
    program_id: str = Field(..., description="Program UUID as string")
    domain: str = Field(..., min_length=1)
    probe: bool = Field(default=True)
    timeout: Optional[int] = Field(default=600, ge=1, le=3600)
    
    class Config:
        json_schema_extra = {
            "example": {
                "program_id": "123e4567-e89b-12d3-a456-426614174000",
                "domain": "example.com",
                "probe": True,
                "timeout": 600
            }
        }


# Response Schemas
class ScanResponse(BaseModel):
    """Generic scan response wrapper"""
    status: str = Field(..., description="success or error")
    message: str
    results: dict = Field(..., description="Scan results")
    
    class Config:
        json_schema_extra = {
            "example": {
                "status": "success",
                "message": "Scan completed",
                "results": {
                    "scanner": "httpx",
                    "hosts": 10,
                    "endpoints": 45
                }
            }
        }


class ErrorResponse(BaseModel):
    """Error response schema"""
    detail: str
    code: str
    
    class Config:
        json_schema_extra = {
            "example": {
                "detail": "Scan execution failed",
                "code": "SCAN_FAILED"
            }
        }
