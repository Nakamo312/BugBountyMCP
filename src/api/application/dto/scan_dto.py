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


class GAUScanInputDTO(BaseModel):
    """Input DTO for GAU scan service"""
    program_id: UUID = Field(..., description="Program UUID")
    domain: str = Field(..., description="Target domain", min_length=1)
    include_subs: bool = Field(default=True, description="Include subdomains in URL discovery")
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
                "include_subs": True,
                "timeout": 600
            }
        }
    )


class GAUScanOutputDTO(BaseModel):
    """Output DTO for GAU scan service"""
    status: str = Field(..., description="Scan status")
    message: str = Field(..., description="Status message")
    scanner: str = Field(..., description="Scanner name")
    domain: str = Field(..., description="Target domain")

    model_config = ConfigDict(
        json_schema_extra = {
            "example": {
                "status": "started",
                "message": "GAU scan started for example.com",
                "scanner": "gau",
                "domain": "example.com"
            }
        }
    )


class KatanaScanInputDTO(BaseModel):
    """Input DTO for Katana scan service"""
    program_id: UUID = Field(..., description="Program UUID")
    target: str = Field(..., description="Target URL to crawl", min_length=1)
    depth: int = Field(default=3, description="Maximum crawl depth", ge=1, le=10)
    js_crawl: bool = Field(default=True, description="Enable JavaScript endpoint crawling")
    headless: bool = Field(default=False, description="Enable headless browser mode")
    timeout: Optional[int] = Field(default=600, description="Scan timeout in seconds", ge=1, le=3600)

    @field_validator('target')
    @classmethod
    def validate_target(cls, v):
        """Basic target URL validation"""
        if not v or v.isspace():
            raise ValueError("Target cannot be empty")
        v = v.strip()
        if not v.startswith(("http://", "https://")):
            raise ValueError("Target must be a valid URL starting with http:// or https://")
        return v

    model_config = ConfigDict(
        json_schema_extra = {
            "example": {
                "program_id": "123e4567-e89b-12d3-a456-426614174000",
                "target": "https://example.com",
                "depth": 3,
                "js_crawl": True,
                "headless": False,
                "timeout": 600
            }
        }
    )


class KatanaScanOutputDTO(BaseModel):
    """Output DTO for Katana scan service"""
    status: str = Field(..., description="Scan status")
    message: str = Field(..., description="Status message")
    scanner: str = Field(..., description="Scanner name")
    target: str = Field(..., description="Target URL")

    model_config = ConfigDict(
        json_schema_extra = {
            "example": {
                "status": "started",
                "message": "Katana crawl started for https://example.com",
                "scanner": "katana",
                "target": "https://example.com"
            }
        }
    )


class LinkFinderScanInputDTO(BaseModel):
    """Input DTO for LinkFinder scan service"""
    program_id: UUID = Field(..., description="Program UUID")
    target: Union[str, List[str]] = Field(..., description="Target URL (with JS files) or list of JS URLs")
    timeout: Optional[int] = Field(default=15, description="Scan timeout per JS file in seconds", ge=1, le=60)

    @field_validator('target')
    @classmethod
    def validate_target(cls, v):
        """Ensure target is always a list of URLs"""
        if isinstance(v, str):
            v = [v]
        for url in v:
            if not url or url.isspace():
                raise ValueError("Target URL cannot be empty")
            url = url.strip()
            if not url.startswith(("http://", "https://")):
                raise ValueError("Target must be a valid URL starting with http:// or https://")
        return v

    model_config = ConfigDict(
        json_schema_extra = {
            "example": {
                "program_id": "123e4567-e89b-12d3-a456-426614174000",
                "target": ["https://example.com/app.js", "https://example.com/bundle.js"],
                "timeout": 15
            }
        }
    )


class LinkFinderScanOutputDTO(BaseModel):
    """Output DTO for LinkFinder scan service"""
    status: str = Field(..., description="Scan status")
    message: str = Field(..., description="Status message")
    scanner: str = Field(..., description="Scanner name")
    targets_count: int = Field(..., description="Number of JS files to analyze")

    model_config = ConfigDict(
        json_schema_extra = {
            "example": {
                "status": "started",
                "message": "LinkFinder scan started for 5 JS files",
                "scanner": "linkfinder",
                "targets_count": 5
            }
        }
    )


class MantraScanOutputDTO(BaseModel):
    """Output DTO for Mantra scan service"""
    status: str = Field(..., description="Scan status")
    message: str = Field(..., description="Status message")
    scanner: str = Field(..., description="Scanner name")
    targets_count: int = Field(..., description="Number of JS files to scan")

    model_config = ConfigDict(
        json_schema_extra = {
            "example": {
                "status": "started",
                "message": "Mantra scan started for 5 JS files",
                "scanner": "mantra",
                "targets_count": 5
            }
        }
    )


class FFUFScanOutputDTO(BaseModel):
    """Output DTO for FFUF scan service"""
    status: str = Field(..., description="Scan status")
    message: str = Field(..., description="Status message")
    scanner: str = Field(..., description="Scanner name")
    targets_count: int = Field(..., description="Number of targets to fuzz")

    model_config = ConfigDict(
        json_schema_extra = {
            "example": {
                "status": "started",
                "message": "FFUF scan started for 3 targets",
                "scanner": "ffuf",
                "targets_count": 3
            }
        }
    )


class DNSxScanInputDTO(BaseModel):
    """Input DTO for DNSx scan service"""
    program_id: UUID = Field(..., description="Program UUID")
    targets: Union[str, List[str]] = Field(..., description="Single target or list of targets")
    mode: str = Field(default="basic", description="Scan mode: basic or deep")
    timeout: Optional[int] = Field(default=600, description="Scan timeout in seconds", ge=1, le=3600)

    @field_validator('targets')
    @classmethod
    def validate_targets(cls, v):
        """Ensure targets is always a list"""
        if isinstance(v, str):
            return [v]
        return v

    @field_validator('mode')
    @classmethod
    def validate_mode(cls, v):
        """Validate scan mode"""
        if v not in ["basic", "deep"]:
            raise ValueError("Mode must be 'basic' or 'deep'")
        return v

    model_config = ConfigDict(
        json_schema_extra = {
            "example": {
                "program_id": "123e4567-e89b-12d3-a456-426614174000",
                "targets": ["example.com", "api.example.com"],
                "mode": "basic",
                "timeout": 600
            }
        }
    )


class DNSxScanOutputDTO(BaseModel):
    """Output DTO for DNSx scan service"""
    status: str = Field(..., description="Scan status")
    message: str = Field(..., description="Status message")
    scanner: str = Field(..., description="Scanner name")
    targets_count: int = Field(..., description="Number of targets to scan")
    mode: str = Field(..., description="Scan mode (basic/deep)")

    model_config = ConfigDict(
        json_schema_extra = {
            "example": {
                "status": "completed",
                "message": "DNSx basic scan completed for 10 targets",
                "scanner": "dnsx",
                "targets_count": 10,
                "mode": "basic"
            }
        }
    )


class ScanResultDTO(BaseModel):
    """Generic scan result wrapper"""
    status: str = Field(..., description="Scan status (success/error)")
    message: str = Field(..., description="Human-readable message")
    data: Union[HTTPXScanOutputDTO, SubfinderScanOutputDTO, GAUScanOutputDTO, KatanaScanOutputDTO, LinkFinderScanOutputDTO] = Field(..., description="Scan results")

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
