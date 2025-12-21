"""Tests for SubfinderScanService"""
import pytest
from unittest.mock import AsyncMock, patch
from uuid import UUID

from api.application.services.subfinder import SubfinderScanService
from api.infrastructure.database.models import HostModel, IPAddressModel
from api.application.dto import SubfinderScanInputDTO, HTTPXScanOutputDTO
from sqlalchemy import select


@pytest.mark.asyncio
class TestSubfinderScanService:
    """Test SubfinderScanService functionality"""

    async def test_execute_scan_yields_subdomains(self, subfinder_service):
        """Test that execute_scan properly yields discovered subdomains"""
        
        # Mock the exec_stream to return fake subdomain data
        fake_subdomains = [
            "api.example.com",
            "www.example.com",
            "mail.example.com",
            "invalid.domain",  # Invalid domain should be filtered
        ]
        
        async def mock_exec_stream(*args, **kwargs):
            for subdomain in fake_subdomains:
                yield subdomain
        
        subfinder_service.exec_stream = mock_exec_stream
        
        # Collect results
        results = []
        async for subdomain in subfinder_service.execute_scan("example.com"):
            results.append(subdomain)
        
        # Verify only valid subdomains are yielded
        assert len(results) == 4
        assert "api.example.com" in results
        assert "www.example.com" in results
        assert "mail.example.com" in results
        assert "" not in results


    async def test_execute_with_probe_true(
        self, 
        subfinder_service, 
        program, 
        session
    ):
        """Test execute with probing - should call httpx_service"""
        
        program_uuid = program.id
        
        # Mock subfinder scan
        async def mock_subfinder_scan(*args, **kwargs):
            yield "api.example.com"
            yield "www.example.com"
        
        subfinder_service.execute_scan = mock_subfinder_scan
        
        # Mock httpx service execute
        httpx_mock_result = HTTPXScanOutputDTO(
            scanner="httpx",
            hosts=2,
            endpoints=5
        )
        subfinder_service.httpx_service.execute = AsyncMock(
            return_value=httpx_mock_result
        )
        
        # Create input DTO
        input_dto = SubfinderScanInputDTO(
            program_id=program_uuid,
            domain="example.com",
            probe=True,
            timeout=600
        )
        
        # Execute with probing
        result = await subfinder_service.execute(input_dto)
        await session.commit()
        
        # Verify httpx_service.execute was called
        subfinder_service.httpx_service.execute.assert_awaited_once()
        
        # Verify result includes probe data
        assert result.scanner == "subfinder"
        assert result.domain == "example.com"
        assert result.subdomains == 2
        assert result.probed is True
        assert result.httpx_results is not None
        assert result.httpx_results.hosts == 2
        assert result.httpx_results.endpoints == 5

    async def test_execute_deduplicates_subdomains(
        self, 
        subfinder_service, 
        program, 
        session
    ):
        """Test that duplicate subdomains are deduplicated"""
        
        program_uuid = program.id
        
        # Mock scan with duplicates
        async def mock_execute_scan(*args, **kwargs):
            yield "api.example.com"
            yield "www.example.com"
            yield "api.example.com"  # Duplicate
            yield "www.example.com"  # Duplicate
            yield "mail.example.com"
        
        subfinder_service.execute_scan = mock_execute_scan
        
        # Create input DTO
        input_dto = SubfinderScanInputDTO(
            program_id=program_uuid,
            domain="example.com",
            probe=True,
            timeout=600
        )
        
        # Execute without probing
        result = await subfinder_service.execute(input_dto)
        await session.commit()
        
        # Verify only unique hosts were created
        hosts = await session.execute(
            select(HostModel).where(HostModel.program_id == program_uuid)
        )
        all_hosts = hosts.scalars().all()
        
        assert len(all_hosts) == 3
        assert result.subdomains == 5  # Total discovered including dupes

    async def test_execute_with_empty_results(
        self, 
        subfinder_service, 
        program, 
        session
    ):
        """Test execute when no subdomains are found"""
        
        program_uuid = program.id
        
        # Mock scan with no results
        async def mock_execute_scan(*args, **kwargs):
            # Empty generator
            if False:
                yield
        
        subfinder_service.execute_scan = mock_execute_scan
        
        # Create input DTO
        input_dto = SubfinderScanInputDTO(
            program_id=program_uuid,
            domain="nonexistent.com",
            probe=False,
            timeout=600
        )
        
        # Execute
        result = await subfinder_service.execute(input_dto)
        await session.commit()
        
        # Verify no hosts were created
        hosts = await session.execute(
            select(HostModel).where(HostModel.program_id == program_uuid)
        )
        all_hosts = hosts.scalars().all()
        
        assert len(all_hosts) == 0
        assert result.subdomains == 0
        assert result.probed is False

    async def test_execute_with_existing_hosts(
        self, 
        subfinder_service, 
        program, 
        session,
        host_repository
    ):
        """Test that existing hosts are not duplicated"""
        
        program_uuid = program.id
        
        # Create existing host
        await host_repository.create({
            "program_id": program_uuid,
            "host": "existing.example.com",
            "in_scope": True,
            "cname": []
        })
        await session.commit()
        
        # Mock scan that includes the existing host
        async def mock_execute_scan(*args, **kwargs):
            yield "existing.example.com"
            yield "new.example.com"
        
        subfinder_service.execute_scan = mock_execute_scan
        
        # Create input DTO
        input_dto = SubfinderScanInputDTO(
            program_id=program_uuid,
            domain="example.com",
            probe=False,
            timeout=600
        )
        
        # Execute
        result = await subfinder_service.execute(input_dto)
        await session.commit()
        
        # Verify total hosts is 2 (1 existing + 1 new)
        hosts = await session.execute(
            select(HostModel).where(HostModel.program_id == program_uuid)
        )
        all_hosts = hosts.scalars().all()
        
        assert len(all_hosts) == 2
        hostnames = {h.host for h in all_hosts}
        assert "existing.example.com" in hostnames
        assert "new.example.com" in hostnames
        assert result.subdomains == 2


    async def test_integration_subfinder_with_httpx_probe(
        self,
        subfinder_service,
        program,
        session
    ):
        """Integration test: Subfinder discovers hosts, HTTPX probes them"""
        
        program_uuid = program.id
        
        # Mock subfinder to find subdomains
        async def mock_execute_scan(*args, **kwargs):
            yield "api.example.com"
            yield "web.example.com"
        
        subfinder_service.execute_scan = mock_execute_scan
        
        # Mock httpx service execute
        httpx_mock_result = HTTPXScanOutputDTO(
            scanner="httpx",
            hosts=2,
            endpoints=8
        )
        subfinder_service.httpx_service.execute = AsyncMock(
            return_value=httpx_mock_result
        )
        
        # Create input DTO
        input_dto = SubfinderScanInputDTO(
            program_id=program_uuid,
            domain="example.com",
            probe=True,
            timeout=600
        )
        
        # Execute with probing
        result = await subfinder_service.execute(input_dto)
        await session.commit()
        
        # Verify hosts were created
        hosts = await session.execute(
            select(HostModel).where(HostModel.program_id == program_uuid)
        )
        all_hosts = hosts.scalars().all()
        assert len(all_hosts) == 2
        
        # Verify result
        assert result.scanner == "subfinder"
        assert result.domain == "example.com"
        assert result.subdomains == 2
        assert result.probed is True
        assert result.httpx_results is not None
        assert result.httpx_results.hosts == 2
        assert result.httpx_results.endpoints == 8