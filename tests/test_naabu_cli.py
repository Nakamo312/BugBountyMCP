"""Tests for Naabu CLI Runner"""

import pytest
import json
from unittest.mock import AsyncMock, MagicMock, patch

from api.infrastructure.runners.naabu_cli import NaabuCliRunner
from api.infrastructure.commands.command_executor import ProcessEvent


@pytest.fixture
def naabu_runner():
    return NaabuCliRunner(naabu_path="/usr/bin/naabu", timeout=600)


@pytest.fixture
def sample_naabu_output():
    return [
        '{"host":"8.8.8.8","ip":"8.8.8.8","port":53,"protocol":"tcp"}',
        '{"host":"8.8.8.8","ip":"8.8.8.8","port":443,"protocol":"tcp"}',
        '{"host":"1.1.1.1","ip":"1.1.1.1","port":80,"protocol":"tcp"}',
    ]


@pytest.mark.asyncio
async def test_scan_single_host(naabu_runner, sample_naabu_output):
    """Test active scan with single host"""
    async def mock_run():
        for line in sample_naabu_output:
            yield ProcessEvent(type="stdout", payload=line)

    mock_executor = AsyncMock()
    mock_executor.run = mock_run

    with patch('api.infrastructure.runners.naabu_cli.CommandExecutor', return_value=mock_executor):
        results = []
        async for event in naabu_runner.scan(hosts="8.8.8.8", top_ports="1000"):
            if event.type == "result":
                results.append(event.payload)

        assert len(results) == 3
        assert results[0]["port"] == 53
        assert results[1]["port"] == 443
        assert results[2]["host"] == "1.1.1.1"


@pytest.mark.asyncio
async def test_scan_multiple_hosts(naabu_runner):
    """Test active scan with multiple hosts"""
    hosts = ["8.8.8.8", "1.1.1.1", "cloudflare.com"]

    mock_executor = AsyncMock()
    mock_executor.run = AsyncMock()

    async def mock_run():
        yield ProcessEvent(type="stdout", payload='{"host":"8.8.8.8","ip":"8.8.8.8","port":53,"protocol":"tcp"}')

    mock_executor.run = mock_run

    with patch('api.infrastructure.runners.naabu_cli.CommandExecutor', return_value=mock_executor) as mock_cmd:
        results = []
        async for event in naabu_runner.scan(hosts=hosts, top_ports="100", rate=500):
            if event.type == "result":
                results.append(event.payload)

        call_args = mock_cmd.call_args
        assert call_args[1]["stdin"] == "8.8.8.8\n1.1.1.1\ncloudflare.com"
        command = call_args[0][0]
        assert "-top-ports" in command
        assert "100" in command
        assert "-rate" in command
        assert "500" in command


@pytest.mark.asyncio
async def test_scan_with_custom_ports(naabu_runner):
    """Test scan with custom port specification"""
    mock_executor = AsyncMock()
    mock_executor.run = AsyncMock()

    async def mock_run():
        yield ProcessEvent(type="stdout", payload='{"host":"example.com","ip":"93.184.216.34","port":80,"protocol":"tcp"}')

    mock_executor.run = mock_run

    with patch('api.infrastructure.runners.naabu_cli.CommandExecutor', return_value=mock_executor) as mock_cmd:
        results = []
        async for event in naabu_runner.scan(
            hosts="example.com",
            ports="80,443,8080-8090",
            scan_type="s",
            exclude_cdn=False
        ):
            if event.type == "result":
                results.append(event.payload)

        command = mock_cmd.call_args[0][0]
        assert "-p" in command
        assert "80,443,8080-8090" in command
        assert "-s" in command
        assert "s" in command
        assert "-exclude-cdn" not in command


@pytest.mark.asyncio
async def test_scan_exclude_cdn(naabu_runner):
    """Test scan with CDN exclusion enabled"""
    mock_executor = AsyncMock()
    mock_executor.run = AsyncMock()

    async def mock_run():
        yield ProcessEvent(type="stdout", payload='{"host":"8.8.8.8","ip":"8.8.8.8","port":443,"protocol":"tcp"}')

    mock_executor.run = mock_run

    with patch('api.infrastructure.runners.naabu_cli.CommandExecutor', return_value=mock_executor) as mock_cmd:
        async for event in naabu_runner.scan(hosts="8.8.8.8", exclude_cdn=True):
            pass

        command = mock_cmd.call_args[0][0]
        assert "-exclude-cdn" in command


@pytest.mark.asyncio
async def test_scan_with_nmap(naabu_runner):
    """Test scan with nmap service detection"""
    mock_executor = AsyncMock()
    mock_executor.run = AsyncMock()

    async def mock_run():
        yield ProcessEvent(type="stdout", payload='{"host":"8.8.8.8","ip":"8.8.8.8","port":53,"protocol":"tcp"}')
        yield ProcessEvent(type="stdout", payload='{"host":"8.8.8.8","ip":"8.8.8.8","port":443,"protocol":"tcp"}')

    mock_executor.run = mock_run

    with patch('api.infrastructure.runners.naabu_cli.CommandExecutor', return_value=mock_executor) as mock_cmd:
        results = []
        async for event in naabu_runner.scan_with_nmap(
            hosts=["8.8.8.8", "1.1.1.1"],
            nmap_cli="nmap -sV -sC",
            top_ports="1000",
            rate=1000
        ):
            if event.type == "result":
                results.append(event.payload)

        assert len(results) == 2
        command = mock_cmd.call_args[0][0]
        assert "-nmap-cli" in command
        assert "nmap -sV -sC" in command
        assert "-top-ports" in command
        assert "1000" in command


@pytest.mark.asyncio
async def test_passive_scan(naabu_runner):
    """Test passive port enumeration"""
    mock_executor = AsyncMock()
    mock_executor.run = AsyncMock()

    async def mock_run():
        yield ProcessEvent(type="stdout", payload='{"host":"8.8.8.8","ip":"8.8.8.8","port":53,"protocol":"tcp"}')
        yield ProcessEvent(type="stdout", payload='{"host":"8.8.8.8","ip":"8.8.8.8","port":80,"protocol":"tcp"}')
        yield ProcessEvent(type="stdout", payload='{"host":"8.8.8.8","ip":"8.8.8.8","port":443,"protocol":"tcp"}')

    mock_executor.run = mock_run

    with patch('api.infrastructure.runners.naabu_cli.CommandExecutor', return_value=mock_executor) as mock_cmd:
        results = []
        async for event in naabu_runner.passive_scan(hosts=["8.8.8.8", "1.1.1.1"]):
            if event.type == "result":
                results.append(event.payload)

        assert len(results) == 3
        command = mock_cmd.call_args[0][0]
        assert "-passive" in command
        assert "-json" in command
        assert "-silent" in command


@pytest.mark.asyncio
async def test_scan_handles_non_json_output(naabu_runner):
    """Test that non-JSON output lines are skipped"""
    mock_executor = AsyncMock()
    mock_executor.run = AsyncMock()

    async def mock_run():
        yield ProcessEvent(type="stdout", payload="[INF] Starting scan...")
        yield ProcessEvent(type="stdout", payload='{"host":"8.8.8.8","ip":"8.8.8.8","port":53,"protocol":"tcp"}')
        yield ProcessEvent(type="stdout", payload="Not a JSON line")
        yield ProcessEvent(type="stdout", payload='{"host":"1.1.1.1","ip":"1.1.1.1","port":443,"protocol":"tcp"}')

    mock_executor.run = mock_run

    with patch('api.infrastructure.runners.naabu_cli.CommandExecutor', return_value=mock_executor):
        results = []
        async for event in naabu_runner.scan(hosts="8.8.8.8"):
            if event.type == "result":
                results.append(event.payload)

        assert len(results) == 2
        assert results[0]["port"] == 53
        assert results[1]["port"] == 443


@pytest.mark.asyncio
async def test_scan_handles_stderr(naabu_runner):
    """Test that stderr output is logged but doesn't break execution"""
    mock_executor = AsyncMock()
    mock_executor.run = AsyncMock()

    async def mock_run():
        yield ProcessEvent(type="stderr", payload="[WRN] Some warning message")
        yield ProcessEvent(type="stdout", payload='{"host":"8.8.8.8","ip":"8.8.8.8","port":53,"protocol":"tcp"}')
        yield ProcessEvent(type="stderr", payload="[ERR] Non-critical error")
        yield ProcessEvent(type="stdout", payload='{"host":"8.8.8.8","ip":"8.8.8.8","port":443,"protocol":"tcp"}')

    mock_executor.run = mock_run

    with patch('api.infrastructure.runners.naabu_cli.CommandExecutor', return_value=mock_executor):
        results = []
        async for event in naabu_runner.scan(hosts="8.8.8.8"):
            if event.type == "result":
                results.append(event.payload)

        assert len(results) == 2


@pytest.mark.asyncio
async def test_scan_empty_results(naabu_runner):
    """Test scan with no open ports found"""
    mock_executor = AsyncMock()
    mock_executor.run = AsyncMock()

    async def mock_run():
        yield ProcessEvent(type="stdout", payload="")

    mock_executor.run = mock_run

    with patch('api.infrastructure.runners.naabu_cli.CommandExecutor', return_value=mock_executor):
        results = []
        async for event in naabu_runner.scan(hosts="192.168.1.1"):
            if event.type == "result":
                results.append(event.payload)

        assert len(results) == 0


@pytest.mark.asyncio
async def test_scan_all_scan_types(naabu_runner):
    """Test different scan types (SYN vs CONNECT)"""
    async def mock_run():
        yield ProcessEvent(type="stdout", payload='{"host":"8.8.8.8","ip":"8.8.8.8","port":53,"protocol":"tcp"}')

    for scan_type in ["s", "c"]:
        mock_executor = AsyncMock()
        mock_executor.run = mock_run

        with patch('api.infrastructure.runners.naabu_cli.CommandExecutor', return_value=mock_executor) as mock_cmd:
            async for event in naabu_runner.scan(hosts="8.8.8.8", scan_type=scan_type):
                pass

            command = mock_cmd.call_args[0][0]
            assert "-s" in command
            assert scan_type in command


@pytest.mark.asyncio
async def test_scan_command_structure(naabu_runner):
    """Test that command is built correctly"""
    mock_executor = AsyncMock()
    mock_executor.run = AsyncMock()

    async def mock_run():
        yield ProcessEvent(type="stdout", payload='{"host":"8.8.8.8","ip":"8.8.8.8","port":53,"protocol":"tcp"}')

    mock_executor.run = mock_run

    with patch('api.infrastructure.runners.naabu_cli.CommandExecutor', return_value=mock_executor) as mock_cmd:
        async for event in naabu_runner.scan(
            hosts="8.8.8.8",
            top_ports="100",
            rate=2000,
            scan_type="c",
            exclude_cdn=True
        ):
            pass

        command = mock_cmd.call_args[0][0]
        assert command[0] == "/usr/bin/naabu"
        assert "-json" in command
        assert "-silent" in command
        assert "-s" in command
        assert "c" in command
        assert "-rate" in command
        assert "2000" in command
        assert "-top-ports" in command
        assert "100" in command
        assert "-exclude-cdn" in command
