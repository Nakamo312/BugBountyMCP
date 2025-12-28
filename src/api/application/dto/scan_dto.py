"""DTOs for scan services"""
from typing import List, Optional, Union
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class HTTPXScanInputDTO(BaseModel):
    """Input DTO for HTTPX scan service"""
    program_id: UUID = Field(..., description="Program UUID")
    targets: Union[str, List[str]] = Field(..., description="Single target or list of targets")
    timeout: Optional[int] = Field(default=600, description="Scan timeout in seconds", ge=1, le=3600)
    
    @field_validator('targets')
    @classmethod
    def validate_targets(cls, v):
        """Ensure targets is always a list"""
        if isinstance(v, str):
            return [v]
        return v

    model_config = ConfigDict(
        json_schema_extra = {
            "example": {
                "program_id": "123e4567-e89b-12d3-a456-426614174000",
                "targets": ["https://example.com", "https://test.com"],
                "timeout": 600
            }
        }
    )


class HTTPXScanOutputDTO(BaseModel):
    """Output DTO for HTTPX scan service"""
    status: str = Field(..., description="Scan status")
    message: str = Field(..., description="Status message")
    scanner: str = Field(..., description="Scanner name")
    targets_count: int = Field(..., description="Number of targets to scan")

    model_config = ConfigDict(
        json_schema_extra = {
            "example": {
                "status": "started",
                "message": "HTTPX scan started for 10 targets",
                "scanner": "httpx",
                "targets_count": 10
            }
        }
    )


class SubfinderScanInputDTO(BaseModel):
    """Input DTO for Subfinder scan service"""
    program_id: UUID = Field(..., description="Program UUID")
    domain: str = Field(..., description="Target domain", min_length=1)
    probe: bool = Field(default=True, description="Probe discovered subdomains with HTTPX")
    timeout: Optional[int] = Field(default=600, description="Scan timeout in seconds", ge=1, le=3600)
    
    @field_validator('domain')
    @classmethod
    def validate_domain(cls, v):
        """Basic domain validation"""
        if not v or v.isspace():
            raise ValueError("Domain cannot be empty")
        return v.strip()

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


class SubfinderScanOutputDTO(BaseModel):
    """Output DTO for Subfinder scan service"""
    status: str = Field(..., description="Scan status")
    message: str = Field(..., description="Status message")
    scanner: str = Field(..., description="Scanner name")
    domain: str = Field(..., description="Target domain")

    model_config = ConfigDict(
        json_schema_extra = {
            "example": {
                "status": "started",
                "message": "Subfinder scan started for example.com",
                "scanner": "subfinder",
                "domain": "example.com"
            }
        }
    )


class ScanResultDTO(BaseModel):
    """Generic scan result wrapper"""
    status: str = Field(..., description="Scan status (success/error)")
    message: str = Field(..., description="Human-readable message")
    data: Union[HTTPXScanOutputDTO, SubfinderScanOutputDTO] = Field(..., description="Scan results")
    
    model_config = ConfigDict(
        json_schema_extra = {
            "example": {
                "status": "success",
                "message": "Scan completed successfully",
                "data": {
                    "scanner": "httpx",
                    "hosts": 10,
                    "endpoints": 45
                }
            }
        }
    )
