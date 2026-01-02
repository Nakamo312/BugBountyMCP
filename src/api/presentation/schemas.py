"""Presentation layer schemas - API request/response models"""
from typing import List, Optional, Union
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# Request Schemas
class HTTPXScanRequest(BaseModel):
    """HTTP request schema for HTTPX scan"""
    program_id: str = Field(..., description="Program UUID as string")
    targets: Union[str, List[str]] = Field(..., description="Single target or list")
    timeout: Optional[int] = Field(default=600, ge=1, le=3600)
    
    model_config = ConfigDict(
        json_schema_extra = {
            "example": {
                "program_id": "123e4567-e89b-12d3-a456-426614174000",
                "targets": ["https://example.com"],
                "timeout": 600
            }
        }
    )


class SubfinderScanRequest(BaseModel):
    """HTTP request schema for Subfinder scan"""
    program_id: str = Field(..., description="Program UUID as string")
    domain: str = Field(..., min_length=1)
    probe: bool = Field(default=True)
    timeout: Optional[int] = Field(default=600, ge=1, le=3600)

    model_config = ConfigDict(
        json_schema_extra = {
            "example": {
                "program_id": "123e4567-e89b-12d3-a456-426614174000",
                "domain": "example.com",
                "probe": True,
                "timeout": 600
            }
        }
    )


class GAUScanRequest(BaseModel):
    """HTTP request schema for GAU scan"""
    program_id: str = Field(..., description="Program UUID as string")
    domain: str = Field(..., min_length=1)
    include_subs: bool = Field(default=True)
    timeout: Optional[int] = Field(default=600, ge=1, le=3600)

    model_config = ConfigDict(
        json_schema_extra = {
            "example": {
                "program_id": "123e4567-e89b-12d3-a456-426614174000",
                "domain": "example.com",
                "include_subs": True,
                "timeout": 600
            }
        }
    )


class KatanaScanRequest(BaseModel):
    """HTTP request schema for Katana scan"""
    program_id: str = Field(..., description="Program UUID as string")
    targets: Union[str, List[str]] = Field(..., description="Single target or list of target URLs")
    depth: int = Field(default=3, ge=1, le=10)
    js_crawl: bool = Field(default=True)
    headless: bool = Field(default=False)
    timeout: Optional[int] = Field(default=600, ge=1, le=3600)

    model_config = ConfigDict(
        json_schema_extra = {
            "example": {
                "program_id": "123e4567-e89b-12d3-a456-426614174000",
                "targets": ["https://example.com", "https://api.example.com"],
                "depth": 3,
                "js_crawl": True,
                "headless": False,
                "timeout": 600
            }
        }
    )


class LinkFinderScanRequest(BaseModel):
    """HTTP request schema for LinkFinder scan"""
    program_id: str = Field(..., description="Program UUID as string")
    targets: Union[str, List[str]] = Field(..., description="JS URL or list of JS URLs to analyze")
    timeout: Optional[int] = Field(default=15, ge=1, le=60)

    model_config = ConfigDict(
        json_schema_extra = {
            "example": {
                "program_id": "123e4567-e89b-12d3-a456-426614174000",
                "targets": ["https://example.com/app.js", "https://example.com/bundle.js"],
                "timeout": 15
            }
        }
    )


# Response Schemas
class ScanResponse(BaseModel):
    """Generic scan response wrapper"""
    status: str = Field(..., description="success or error")
    message: str
    model_config = ConfigDict(
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
    )


class ErrorResponse(BaseModel):
    """Error response schema"""
    detail: str
    code: str

    model_config = ConfigDict(
        json_schema_extra = {
            "example": {
                "detail": "Scan execution failed",
                "code": "SCAN_FAILED"
            }
        }
    )
