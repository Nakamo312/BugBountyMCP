from typing import List, Optional
from pydantic import BaseModel, Field, ConfigDict

class HTTPXScanRequest(BaseModel):
    """HTTP request schema for HTTPX scan"""
    program_id: str = Field(..., description="Program UUID as string")
    targets: List[str] = Field(..., description="List of target URLs/domains", min_items=1)
    timeout: Optional[int] = Field(default=600, ge=1, le=3600)

    model_config = ConfigDict(
        json_schema_extra={
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
    targets: List[str] = Field(..., description="List of target domains", min_items=1)
    probe: bool = Field(default=True)
    timeout: Optional[int] = Field(default=600, ge=1, le=3600)

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "program_id": "123e4567-e89b-12d3-a456-426614174000",
                "targets": ["example.com"],
                "probe": True,
                "timeout": 600
            }
        }
    )


class GAUScanRequest(BaseModel):
    """HTTP request schema for GAU scan"""
    program_id: str = Field(..., description="Program UUID as string")
    targets: List[str] = Field(..., description="List of target domains", min_items=1)
    include_subs: bool = Field(default=True)
    timeout: Optional[int] = Field(default=600, ge=1, le=3600)

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "program_id": "123e4567-e89b-12d3-a456-426614174000",
                "targets": ["example.com"],
                "include_subs": True,
                "timeout": 600
            }
        }
    )


class KatanaScanRequest(BaseModel):
    """HTTP request schema for Katana scan"""
    program_id: str = Field(..., description="Program UUID as string")
    targets: List[str] = Field(..., description="List of target URLs", min_items=1)
    depth: int = Field(default=3, ge=1, le=10)
    js_crawl: bool = Field(default=True)
    headless: bool = Field(default=False)
    timeout: Optional[int] = Field(default=600, ge=1, le=3600)

    model_config = ConfigDict(
        json_schema_extra={
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
    targets: List[str] = Field(..., description="List of JS URLs to analyze", min_items=1)
    timeout: Optional[int] = Field(default=15, ge=1, le=60)

    model_config = ConfigDict(
        json_schema_extra={
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
    targets: List[str] = Field(..., description="List of JS URLs to scan for secrets", min_items=1)
    timeout: Optional[int] = Field(default=300, ge=1, le=3600)

    model_config = ConfigDict(
        json_schema_extra={
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
    targets: List[str] = Field(..., description="List of URLs to fuzz", min_items=1)
    timeout: Optional[int] = Field(default=600, ge=1, le=3600)

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "program_id": "123e4567-e89b-12d3-a456-426614174000",
                "targets": ["https://example.com", "https://api.example.com"],
                "timeout": 600
            }
        }
    )


class AmassScanRequest(BaseModel):
    """HTTP request schema for Amass scan"""
    program_id: str = Field(..., description="Program UUID as string")
    targets: List[str] = Field(..., description="List of target domains for enumeration", min_items=1)
    active: bool = Field(default=False, description="Enable active enumeration (zone transfers, brute force)")
    timeout: Optional[int] = Field(default=1800, ge=1, le=7200)

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "program_id": "123e4567-e89b-12d3-a456-426614174000",
                "targets": ["example.com", "test.org"],
                "active": True,
                "timeout": 1800
            }
        }
    )


class DNSxScanRequest(BaseModel):
    """HTTP request schema for DNSx scan"""
    program_id: str = Field(..., description="Program UUID as string")
    targets: List[str] = Field(..., description="List of domains/hosts or IPs", min_items=1)
    mode: str = Field(default="default", description="Scan mode: default (A, AAAA, CNAME, MX, TXT, NS, SOA) or ptr (reverse DNS)")
    timeout: Optional[int] = Field(default=600, ge=1, le=3600)

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "program_id": "123e4567-e89b-12d3-a456-426614174000",
                "targets": ["example.com", "api.example.com"],
                "mode": "default",
                "timeout": 600
            }
        }
    )


class SubjackScanRequest(BaseModel):
    """HTTP request schema for Subjack scan"""
    program_id: str = Field(..., description="Program UUID as string")
    targets: List[str] = Field(..., description="List of domains to check for subdomain takeover", min_items=1)
    timeout: Optional[int] = Field(default=300, ge=1, le=3600)

    model_config = ConfigDict(
        json_schema_extra={
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
    targets: List[str] = Field(..., description="List of domains, ASNs, or organizations", min_items=1)
    mode: str = Field(default="domain", description="Scan mode: domain, asn, or organization")
    timeout: Optional[int] = Field(default=300, ge=1, le=3600)

    model_config = ConfigDict(
        json_schema_extra={
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
    cidrs: List[str] = Field(..., description="List of CIDRs to process", min_items=1)
    operation: str = Field(default="expand", description="Operation: expand, slice_count, slice_host, aggregate")
    count: Optional[int] = Field(default=None, description="For slice_count: number of subnets")
    host_count: Optional[int] = Field(default=None, description="For slice_host: hosts per subnet")
    skip_base: bool = Field(default=False, description="Skip base IPs ending in .0")
    skip_broadcast: bool = Field(default=False, description="Skip broadcast IPs ending in .255")
    shuffle: bool = Field(default=False, description="Shuffle IPs in random order")
    timeout: Optional[int] = Field(default=300, ge=1, le=3600)

    model_config = ConfigDict(
        json_schema_extra={
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
    targets: List[str] = Field(..., description="List of hosts/IPs to scan", min_items=1)
    scan_mode: str = Field(default="active", description="Scan mode: active, passive, or nmap")
    ports: Optional[str] = Field(default=None, description="Port specification or None for top-ports")
    top_ports: str = Field(default="1000", description="Top ports preset: 100, 1000, or full")
    rate: int = Field(default=1000, ge=1, le=10000, description="Packets per second")
    scan_type: str = Field(default="c", description="Scan type: s (SYN) or c (CONNECT)")
    exclude_cdn: bool = Field(default=True, description="Skip full port scans for CDN/WAF")
    nmap_cli: Optional[str] = Field(default="nmap -sV", description="Nmap command for service detection (nmap mode only)")
    timeout: Optional[int] = Field(default=600, ge=1, le=3600)

    model_config = ConfigDict(
        json_schema_extra={
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
