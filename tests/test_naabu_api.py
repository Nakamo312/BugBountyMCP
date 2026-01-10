"""Tests for Naabu API Endpoint"""

import pytest
from uuid import UUID
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import HTTPException

from api.presentation.rest.routes.scan import scan_naabu
from api.presentation.schemas import NaabuScanRequest
from api.application.dto.scan_dto import NaabuScanOutputDTO


@pytest.fixture
def mock_naabu_service():
    service = AsyncMock()
    service.execute = AsyncMock()
    service.execute_passive = AsyncMock()
    service.execute_with_nmap = AsyncMock()
    return service


@pytest.mark.asyncio
async def test_scan_naabu_active_single_host(mock_naabu_service):
    """Test active scan with single host"""
    request = NaabuScanRequest(
        program_id="123e4567-e89b-12d3-a456-426614174000",
        targets="8.8.8.8",
        scan_mode="active",
        top_ports="1000",
        rate=1000,
        scan_type="c",
        exclude_cdn=True
    )

    mock_naabu_service.execute.return_value = NaabuScanOutputDTO(
        status="completed",
        message="Active scan completed: 1 hosts, 5 open ports discovered",
        scanner="naabu",
        targets_count=1,
        scan_mode="active"
    )

    response = await scan_naabu(request, mock_naabu_service)

    assert response.status == "success"
    assert "5 open ports" in response.message

    mock_naabu_service.execute.assert_called_once_with(
        program_id=UUID("123e4567-e89b-12d3-a456-426614174000"),
        hosts=["8.8.8.8"],
        ports=None,
        top_ports="1000",
        rate=1000,
        scan_type="c",
        exclude_cdn=True
    )


@pytest.mark.asyncio
async def test_scan_naabu_active_multiple_hosts(mock_naabu_service):
    """Test active scan with multiple hosts"""
    request = NaabuScanRequest(
        program_id="123e4567-e89b-12d3-a456-426614174000",
        targets=["8.8.8.8", "1.1.1.1", "cloudflare.com"],
        scan_mode="active",
        top_ports="100",
        rate=500,
        scan_type="s",
        exclude_cdn=False
    )

    mock_naabu_service.execute.return_value = NaabuScanOutputDTO(
        status="completed",
        message="Active scan completed: 3 hosts, 12 open ports discovered",
        scanner="naabu",
        targets_count=3,
        scan_mode="active"
    )

    response = await scan_naabu(request, mock_naabu_service)

    assert response.status == "success"

    mock_naabu_service.execute.assert_called_once_with(
        program_id=UUID("123e4567-e89b-12d3-a456-426614174000"),
        hosts=["8.8.8.8", "1.1.1.1", "cloudflare.com"],
        ports=None,
        top_ports="100",
        rate=500,
        scan_type="s",
        exclude_cdn=False
    )


@pytest.mark.asyncio
async def test_scan_naabu_with_custom_ports(mock_naabu_service):
    """Test active scan with custom port specification"""
    request = NaabuScanRequest(
        program_id="123e4567-e89b-12d3-a456-426614174000",
        targets="example.com",
        scan_mode="active",
        ports="80,443,8080-8090",
        top_ports="1000",
        rate=1000,
        scan_type="c",
        exclude_cdn=True
    )

    mock_naabu_service.execute.return_value = NaabuScanOutputDTO(
        status="completed",
        message="Active scan completed: 1 hosts, 3 open ports discovered",
        scanner="naabu",
        targets_count=1,
        scan_mode="active"
    )

    response = await scan_naabu(request, mock_naabu_service)

    assert response.status == "success"

    mock_naabu_service.execute.assert_called_once()
    call_args = mock_naabu_service.execute.call_args[1]
    assert call_args["ports"] == "80,443,8080-8090"


@pytest.mark.asyncio
async def test_scan_naabu_passive_mode(mock_naabu_service):
    """Test passive port enumeration"""
    request = NaabuScanRequest(
        program_id="123e4567-e89b-12d3-a456-426614174000",
        targets=["8.8.8.8", "1.1.1.1"],
        scan_mode="passive"
    )

    mock_naabu_service.execute_passive.return_value = NaabuScanOutputDTO(
        status="completed",
        message="Passive scan completed: 2 hosts, 8 ports discovered from Shodan",
        scanner="naabu",
        targets_count=2,
        scan_mode="passive"
    )

    response = await scan_naabu(request, mock_naabu_service)

    assert response.status == "success"
    assert "Shodan" in response.message

    mock_naabu_service.execute_passive.assert_called_once_with(
        program_id=UUID("123e4567-e89b-12d3-a456-426614174000"),
        hosts=["8.8.8.8", "1.1.1.1"]
    )

    mock_naabu_service.execute.assert_not_called()


@pytest.mark.asyncio
async def test_scan_naabu_nmap_mode(mock_naabu_service):
    """Test scan with nmap service detection"""
    request = NaabuScanRequest(
        program_id="123e4567-e89b-12d3-a456-426614174000",
        targets="8.8.8.8",
        scan_mode="nmap",
        nmap_cli="nmap -sV -sC",
        top_ports="100",
        rate=500
    )

    mock_naabu_service.execute_with_nmap.return_value = NaabuScanOutputDTO(
        status="completed",
        message="Nmap scan completed: 1 hosts, 5 results with service detection",
        scanner="naabu",
        targets_count=1,
        scan_mode="nmap"
    )

    response = await scan_naabu(request, mock_naabu_service)

    assert response.status == "success"
    assert "service detection" in response.message

    mock_naabu_service.execute_with_nmap.assert_called_once_with(
        program_id=UUID("123e4567-e89b-12d3-a456-426614174000"),
        hosts=["8.8.8.8"],
        nmap_cli="nmap -sV -sC",
        top_ports="100",
        rate=500
    )

    mock_naabu_service.execute.assert_not_called()


@pytest.mark.asyncio
async def test_scan_naabu_invalid_scan_mode(mock_naabu_service):
    """Test error handling for invalid scan mode"""
    request = NaabuScanRequest(
        program_id="123e4567-e89b-12d3-a456-426614174000",
        targets="8.8.8.8",
        scan_mode="invalid",
        top_ports="1000",
        rate=1000,
        scan_type="c",
        exclude_cdn=True
    )

    with pytest.raises(HTTPException) as exc_info:
        await scan_naabu(request, mock_naabu_service)

    assert exc_info.value.status_code == 400
    assert "Invalid scan_mode" in exc_info.value.detail


@pytest.mark.asyncio
async def test_scan_naabu_invalid_program_id(mock_naabu_service):
    """Test error handling for invalid program ID"""
    request = NaabuScanRequest(
        program_id="invalid-uuid",
        targets="8.8.8.8",
        scan_mode="active",
        top_ports="1000",
        rate=1000,
        scan_type="c",
        exclude_cdn=True
    )

    with pytest.raises(HTTPException) as exc_info:
        await scan_naabu(request, mock_naabu_service)

    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_scan_naabu_service_error(mock_naabu_service):
    """Test error handling when service raises exception"""
    request = NaabuScanRequest(
        program_id="123e4567-e89b-12d3-a456-426614174000",
        targets="8.8.8.8",
        scan_mode="active",
        top_ports="1000",
        rate=1000,
        scan_type="c",
        exclude_cdn=True
    )

    mock_naabu_service.execute.side_effect = ValueError("Naabu execution failed")

    with pytest.raises(HTTPException) as exc_info:
        await scan_naabu(request, mock_naabu_service)

    assert exc_info.value.status_code == 400
    assert "Naabu execution failed" in exc_info.value.detail


@pytest.mark.asyncio
async def test_scan_naabu_response_structure(mock_naabu_service):
    """Test response structure"""
    request = NaabuScanRequest(
        program_id="123e4567-e89b-12d3-a456-426614174000",
        targets="8.8.8.8",
        scan_mode="active",
        top_ports="1000",
        rate=1000,
        scan_type="c",
        exclude_cdn=True
    )

    mock_output = NaabuScanOutputDTO(
        status="completed",
        message="Active scan completed: 1 hosts, 3 open ports discovered",
        scanner="naabu",
        targets_count=1,
        scan_mode="active"
    )

    mock_naabu_service.execute.return_value = mock_output

    response = await scan_naabu(request, mock_naabu_service)

    assert response.status == "success"
    assert response.message == mock_output.message
    assert "status" in response.results
    assert "scanner" in response.results
    assert "targets_count" in response.results
    assert "scan_mode" in response.results


@pytest.mark.asyncio
async def test_scan_naabu_default_values(mock_naabu_service):
    """Test that default values are applied correctly"""
    request = NaabuScanRequest(
        program_id="123e4567-e89b-12d3-a456-426614174000",
        targets="8.8.8.8",
        scan_mode="active"
    )

    mock_naabu_service.execute.return_value = NaabuScanOutputDTO(
        status="completed",
        message="Active scan completed",
        scanner="naabu",
        targets_count=1,
        scan_mode="active"
    )

    await scan_naabu(request, mock_naabu_service)

    call_args = mock_naabu_service.execute.call_args[1]
    assert call_args["top_ports"] == "1000"
    assert call_args["rate"] == 1000
    assert call_args["scan_type"] == "c"
    assert call_args["exclude_cdn"] is True


@pytest.mark.asyncio
async def test_scan_naabu_syn_scan(mock_naabu_service):
    """Test SYN scan type"""
    request = NaabuScanRequest(
        program_id="123e4567-e89b-12d3-a456-426614174000",
        targets="8.8.8.8",
        scan_mode="active",
        scan_type="s",
        top_ports="1000",
        rate=1000,
        exclude_cdn=True
    )

    mock_naabu_service.execute.return_value = NaabuScanOutputDTO(
        status="completed",
        message="Active scan completed",
        scanner="naabu",
        targets_count=1,
        scan_mode="active"
    )

    await scan_naabu(request, mock_naabu_service)

    call_args = mock_naabu_service.execute.call_args[1]
    assert call_args["scan_type"] == "s"


@pytest.mark.asyncio
async def test_scan_naabu_top_ports_full(mock_naabu_service):
    """Test full port scan"""
    request = NaabuScanRequest(
        program_id="123e4567-e89b-12d3-a456-426614174000",
        targets="8.8.8.8",
        scan_mode="active",
        top_ports="full",
        rate=1000,
        scan_type="c",
        exclude_cdn=True
    )

    mock_naabu_service.execute.return_value = NaabuScanOutputDTO(
        status="completed",
        message="Active scan completed",
        scanner="naabu",
        targets_count=1,
        scan_mode="active"
    )

    await scan_naabu(request, mock_naabu_service)

    call_args = mock_naabu_service.execute.call_args[1]
    assert call_args["top_ports"] == "full"


@pytest.mark.asyncio
async def test_scan_naabu_high_rate(mock_naabu_service):
    """Test high rate scanning"""
    request = NaabuScanRequest(
        program_id="123e4567-e89b-12d3-a456-426614174000",
        targets="8.8.8.8",
        scan_mode="active",
        rate=5000,
        top_ports="1000",
        scan_type="c",
        exclude_cdn=True
    )

    mock_naabu_service.execute.return_value = NaabuScanOutputDTO(
        status="completed",
        message="Active scan completed",
        scanner="naabu",
        targets_count=1,
        scan_mode="active"
    )

    await scan_naabu(request, mock_naabu_service)

    call_args = mock_naabu_service.execute.call_args[1]
    assert call_args["rate"] == 5000


@pytest.mark.asyncio
async def test_scan_naabu_exclude_cdn_disabled(mock_naabu_service):
    """Test with CDN exclusion disabled"""
    request = NaabuScanRequest(
        program_id="123e4567-e89b-12d3-a456-426614174000",
        targets="cloudflare.com",
        scan_mode="active",
        exclude_cdn=False,
        top_ports="1000",
        rate=1000,
        scan_type="c"
    )

    mock_naabu_service.execute.return_value = NaabuScanOutputDTO(
        status="completed",
        message="Active scan completed",
        scanner="naabu",
        targets_count=1,
        scan_mode="active"
    )

    await scan_naabu(request, mock_naabu_service)

    call_args = mock_naabu_service.execute.call_args[1]
    assert call_args["exclude_cdn"] is False


@pytest.mark.asyncio
async def test_scan_naabu_nmap_default_cli(mock_naabu_service):
    """Test nmap mode with default CLI"""
    request = NaabuScanRequest(
        program_id="123e4567-e89b-12d3-a456-426614174000",
        targets="8.8.8.8",
        scan_mode="nmap",
        top_ports="1000",
        rate=1000
    )

    mock_naabu_service.execute_with_nmap.return_value = NaabuScanOutputDTO(
        status="completed",
        message="Nmap scan completed",
        scanner="naabu",
        targets_count=1,
        scan_mode="nmap"
    )

    await scan_naabu(request, mock_naabu_service)

    call_args = mock_naabu_service.execute_with_nmap.call_args[1]
    assert call_args["nmap_cli"] == "nmap -sV"
