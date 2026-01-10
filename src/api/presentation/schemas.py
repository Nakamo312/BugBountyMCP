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


class MantraScanRequest(BaseModel):
    """HTTP request schema for Mantra scan"""
    program_id: str = Field(..., description="Program UUID as string")
    targets: Union[str, List[str]] = Field(..., description="JS URL or list of JS URLs to scan for secrets")
    timeout: Optional[int] = Field(default=300, ge=1, le=3600)

    model_config = ConfigDict(
        json_schema_extra = {
            "example": {
                "program_id": "123e4567-e89b-12d3-a456-426614174000",
                "targets": ["https://example.com/app.js", "https://example.com/bundle.js"],
                "timeout": 300
            }
        }
    )


class FFUFScanRequest(BaseModel):
    """HTTP request schema for FFUF scan"""
    program_id: str = Field(..., description="Program UUID as string")
    targets: Union[str, List[str]] = Field(..., description="Base URL or list of URLs to fuzz")
    timeout: Optional[int] = Field(default=600, ge=1, le=3600)

    model_config = ConfigDict(
        json_schema_extra = {
            "example": {
                "program_id": "123e4567-e89b-12d3-a456-426614174000",
                "targets": ["https://example.com", "https://api.example.com"],
                "timeout": 600
            }
        }
    )


class DNSxScanRequest(BaseModel):
    """HTTP request schema for DNSx scan"""
    program_id: str = Field(..., description="Program UUID as string")
    targets: Union[str, List[str]] = Field(..., description="Single domain/host or list of domains/hosts (for basic/deep mode) OR IP addresses (for ptr mode)")
    mode: str = Field(default="basic", description="Scan mode: basic (A/AAAA/CNAME), deep (all records), or ptr (reverse DNS)")
    timeout: Optional[int] = Field(default=600, ge=1, le=3600)

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


class SubjackScanRequest(BaseModel):
    """HTTP request schema for Subjack scan"""
    program_id: str = Field(..., description="Program UUID as string")
    targets: Union[str, List[str]] = Field(..., description="Single domain or list of domains to check for subdomain takeover")
    timeout: Optional[int] = Field(default=300, ge=1, le=3600)

    model_config = ConfigDict(
        json_schema_extra = {
            "example": {
                "program_id": "123e4567-e89b-12d3-a456-426614174000",
                "targets": ["vulnerable.example.com", "test.example.com"],
                "timeout": 300
            }
        }
    )


class ASNMapScanRequest(BaseModel):
    """HTTP request schema for ASNMap scan"""
    program_id: str = Field(..., description="Program UUID as string")
    targets: Union[str, List[str]] = Field(..., description="Domains (mode=domain), ASN numbers (mode=asn), or organization names (mode=organization)")
    mode: str = Field(default="domain", description="Scan mode: domain, asn, or organization")
    timeout: Optional[int] = Field(default=300, ge=1, le=3600)

    model_config = ConfigDict(
        json_schema_extra = {
            "example": {
                "program_id": "123e4567-e89b-12d3-a456-426614174000",
                "targets": ["example.com", "google.com"],
                "mode": "domain",
                "timeout": 300
            }
        }
    )


class MapCIDRScanRequest(BaseModel):
    """HTTP request schema for MapCIDR scan"""
    program_id: str = Field(..., description="Program UUID as string")
    cidrs: Union[str, List[str]] = Field(..., description="Single CIDR or list of CIDRs to process")
    operation: str = Field(default="expand", description="Operation: expand, slice_count, slice_host, aggregate")
    count: Optional[int] = Field(default=None, description="For slice_count: number of subnets")
    host_count: Optional[int] = Field(default=None, description="For slice_host: hosts per subnet")
    skip_base: bool = Field(default=False, description="Skip base IPs ending in .0")
    skip_broadcast: bool = Field(default=False, description="Skip broadcast IPs ending in .255")
    shuffle: bool = Field(default=False, description="Shuffle IPs in random order")
    timeout: Optional[int] = Field(default=300, ge=1, le=3600)

    model_config = ConfigDict(
        json_schema_extra = {
            "example": {
                "program_id": "123e4567-e89b-12d3-a456-426614174000",
                "cidrs": ["192.168.1.0/24", "10.0.0.0/16"],
                "operation": "expand",
                "skip_base": True,
                "skip_broadcast": True,
                "timeout": 300
            }
        }
    )


class NaabuScanRequest(BaseModel):
    """HTTP request schema for Naabu port scan"""
    program_id: str = Field(..., description="Program UUID as string")
    targets: Union[str, List[str]] = Field(..., description="Single host/IP or list of hosts/IPs to scan")
    scan_mode: str = Field(default="active", description="Scan mode: active, passive, or nmap")
    ports: Optional[str] = Field(default=None, description="Port specification (e.g., '80,443,8080-8090') or None for top-ports")
    top_ports: str = Field(default="1000", description="Top ports preset: 100, 1000, or full")
    rate: int = Field(default=1000, ge=1, le=10000, description="Packets per second")
    scan_type: str = Field(default="c", description="Scan type: s (SYN) or c (CONNECT)")
    exclude_cdn: bool = Field(default=True, description="Skip full port scans for CDN/WAF, only scan 80,443")
    nmap_cli: Optional[str] = Field(default="nmap -sV", description="Nmap command for service detection (nmap mode only)")
    timeout: Optional[int] = Field(default=600, ge=1, le=3600)

    model_config = ConfigDict(
        json_schema_extra = {
            "example": {
                "program_id": "123e4567-e89b-12d3-a456-426614174000",
                "targets": ["192.168.1.1", "10.0.0.1"],
                "scan_mode": "active",
                "top_ports": "1000",
                "rate": 1000,
                "scan_type": "c",
                "exclude_cdn": True,
                "timeout": 600
            }
        }
    )


# Response Schemas
class ScanResponse(BaseModel):
    """Generic scan response wrapper"""
    status: str = Field(..., description="success or error")
    message: str
    results: Optional[dict] = Field(default=None, description="Scan results details")
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
