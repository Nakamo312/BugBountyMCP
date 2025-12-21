"""Tests for SubfinderScanService"""
import pytest
from unittest.mock import AsyncMock, patch
from uuid import UUID

from api.application.services.subfinder import SubfinderScanService
from api.infrastructure.database.models import HostModel, IPAddressModel
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
            "",  # Empty line should be filtered
            "invalid..domain",  # Invalid domain should be filtered
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
        assert len(results) == 3
        assert "api.example.com" in results
        assert "www.example.com" in results
        assert "mail.example.com" in results
        assert "" not in results

    async def test_execute_with_probe_false(
        self, 
        subfinder_service, 
        program, 
        session,
        host_repository
    ):
        """Test execute without probing - should only store subdomains"""
        
        program_uuid = program.id
        
        # Mock execute_scan to return subdomains
        async def mock_execute_scan(*args, **kwargs):
            yield "sub1.example.com"
            yield "sub2.example.com"
        
        subfinder_service.execute_scan = mock_execute_scan
        
        # Execute without probing
        result = await subfinder_service.execute(
            program_id=str(program_uuid),
            domain="example.com",
            probe=False
        )
        await session.commit()
        
        # Verify hosts were created
        hosts = await session.execute(
            select(HostModel).where(HostModel.program_id == program_uuid)
        )
        all_hosts = hosts.scalars().all()
        
        assert len(all_hosts) == 2
        hostnames = {h.host for h in all_hosts}
        assert "sub1.example.com" in hostnames
        assert "sub2.example.com" in hostnames
        
        # Verify result structure
        assert result["scanner"] == "subfinder"
        assert result["target"] == "example.com"
        assert result["total_found"] == 2
        assert result["probed"] == 0

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
        httpx_mock_result = {
            "scanner": "httpx",
            "hosts": 2,
            "endpoints": 5
        }
        subfinder_service.httpx_service.execute = AsyncMock(
            return_value=httpx_mock_result
        )
        
        # Execute with probing
        result = await subfinder_service.execute(
            program_id=str(program_uuid),
            domain="example.com",
            probe=True
        )
        await session.commit()
        
        # Verify httpx_service.execute was called
        subfinder_service.httpx_service.execute.assert_awaited_once()
        call_args = subfinder_service.httpx_service.execute.call_args
        
        # Verify it was called with correct arguments
        assert call_args.kwargs["program_id"] == str(program_uuid)
        assert set(call_args.kwargs["targets"]) == {
            "api.example.com",
            "www.example.com"
        }
        
        # Verify result includes probe data
        assert result["scanner"] == "subfinder"
        assert result["total_found"] == 2
        assert result["probed"] == 2
        assert result["probe_results"] == httpx_mock_result

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
        
        # Execute without probing
        result = await subfinder_service.execute(
            program_id=str(program_uuid),
            domain="example.com",
            probe=False
        )
        await session.commit()
        
        # Verify only unique hosts were created
        hosts = await session.execute(
            select(HostModel).where(HostModel.program_id == program_uuid)
        )
        all_hosts = hosts.scalars().all()
        
        assert len(all_hosts) == 3
        assert result["total_found"] == 5  # Total discovered including dupes
        
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
            return
            yield  # Empty generator
        
        subfinder_service.execute_scan = mock_execute_scan
        
        # Execute
        result = await subfinder_service.execute(
            program_id=str(program_uuid),
            domain="nonexistent.com",
            probe=False
        )
        await session.commit()
        
        # Verify no hosts were created
        hosts = await session.execute(
            select(HostModel).where(HostModel.program_id == program_uuid)
        )
        all_hosts = hosts.scalars().all()
        
        assert len(all_hosts) == 0
        assert result["total_found"] == 0
        assert result["probed"] == 0

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
            "in_scope": True
        })
        await session.commit()
        
        # Mock scan that includes the existing host
        async def mock_execute_scan(*args, **kwargs):
            yield "existing.example.com"
            yield "new.example.com"
        
        subfinder_service.execute_scan = mock_execute_scan
        
        # Execute
        result = await subfinder_service.execute(
            program_id=str(program_uuid),
            domain="example.com",
            probe=False
        )
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

    async def test_execute_scan_command_construction(self, subfinder_service):
        """Test that subfinder command is constructed correctly"""
        
        with patch.object(
            subfinder_service, 
            'exec_stream',
            new_callable=AsyncMock
        ) as mock_exec:
            # Setup mock to return empty generator
            async def empty_gen(*args, **kwargs):
                return
                yield
            mock_exec.return_value = empty_gen()
            
            # Execute scan
            result = []
            async for _ in subfinder_service.execute_scan("example.com"):
                result.append(_)
            
            # Verify exec_stream was called with correct command
            mock_exec.assert_called_once()
            call_args = mock_exec.call_args[0][0]  # First positional arg (command)
            
            assert call_args[0].endswith("subfinder")
            assert "-d" in call_args
            assert "example.com" in call_args
            assert "-silent" in call_args

    async def test_integration_subfinder_with_httpx_probe(
        self,
        subfinder_service,
        program,
        session
    ):
        """Integration test: Subfinder discovers hosts, HTTPX probes them"""
        
        program_uuid = program.id
        
        # Mock subfinder to find subdomains
        async def mock_subfinder(*args, **kwargs):
            yield "api.example.com"
            yield "web.example.com"
        
        subfinder_service.execute_scan = mock_subfinder
        
        # Mock httpx to return scan data
        async def mock_httpx_scan(*args, **kwargs):
            yield {
                "host": "api.example.com",
                "host_ip": "1.2.3.4",
                "scheme": "https",
                "port": 443,
                "path": "/",
                "status_code": 200,
                "tech": ["nginx"],
                "cname": [],
                "a": ["1.2.3.4"],
                "method": "GET"
            }
            yield {
                "host": "web.example.com",
                "host_ip": "1.2.3.5",
                "scheme": "http",
                "port": 80,
                "path": "/",
                "status_code": 200,
                "tech": [],
                "cname": [],
                "a": ["1.2.3.5"],
                "method": "GET"
            }
        
        subfinder_service.httpx_service.execute_scan = mock_httpx_scan
        
        # Execute with probing
        result = await subfinder_service.execute(
            program_id=str(program_uuid),
            domain="example.com",
            probe=True
        )
        await session.commit()
        
        # Verify hosts were created
        hosts = await session.execute(
            select(HostModel).where(HostModel.program_id == program_uuid)
        )
        all_hosts = hosts.scalars().all()
        assert len(all_hosts) == 2
        
        # Verify IPs were created during probing
        ips = await session.execute(
            select(IPAddressModel).where(
                IPAddressModel.program_id == program_uuid
            )
        )
        all_ips = ips.scalars().all()
        assert len(all_ips) == 2
        
        # Verify result
        assert result["total_found"] == 2
        assert result["probed"] == 2
        assert "probe_results" in result
