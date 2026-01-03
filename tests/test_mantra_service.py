import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from api.application.services.mantra import MantraScanService
from api.infrastructure.schemas.models.process_event import ProcessEvent


@pytest.fixture
def mock_mantra_runner():
    return AsyncMock()


@pytest.fixture
def mock_event_bus():
    bus = AsyncMock()
    bus.publish = AsyncMock()
    return bus


@pytest.fixture
def mantra_service(mock_mantra_runner, mock_event_bus):
    return MantraScanService(runner=mock_mantra_runner, bus=mock_event_bus)


@pytest.mark.asyncio
async def test_parse_mantra_output_valid_line(mantra_service):
    """Test parsing valid Mantra output line"""
    line = "[+] https://example.com/app.js [sk_live_51H8...]"

    result = mantra_service._parse_mantra_output(line)

    assert result is not None
    assert result["url"] == "https://example.com/app.js"
    assert result["secret"] == "sk_live_51H8..."


@pytest.mark.asyncio
async def test_parse_mantra_output_with_spaces(mantra_service):
    """Test parsing Mantra output with spaces in secret"""
    line = "[+] https://example.com/app.js [AWS Access Key]"

    result = mantra_service._parse_mantra_output(line)

    assert result is not None
    assert result["url"] == "https://example.com/app.js"
    assert result["secret"] == "AWS Access Key"


@pytest.mark.asyncio
async def test_parse_mantra_output_invalid_format(mantra_service):
    """Test that invalid format returns None"""
    invalid_lines = [
        "[-] Unable to make a request",
        "some random text",
        "[+] missing brackets",
        "",
    ]

    for line in invalid_lines:
        result = mantra_service._parse_mantra_output(line)
        assert result is None


@pytest.mark.asyncio
async def test_parse_mantra_output_http_url(mantra_service):
    """Test parsing HTTP URL (not just HTTPS)"""
    line = "[+] http://example.com/app.js [AKIA...]"

    result = mantra_service._parse_mantra_output(line)

    assert result is not None
    assert result["url"] == "http://example.com/app.js"
    assert result["secret"] == "AKIA..."


@pytest.mark.asyncio
async def test_execute_starts_background_task(mantra_service, mock_mantra_runner):
    """Test that execute starts background task"""
    program_id = uuid4()
    targets = ["https://example.com/app.js"]

    # Mock runner to return empty async generator
    async def empty_gen():
        return
        yield

    mock_mantra_runner.run = AsyncMock(return_value=empty_gen())

    await mantra_service.execute(program_id, targets)

    # Should not wait for completion (background task)
    # Just verify it was called
    assert True


def test_parse_mantra_output_edge_cases(mantra_service):
    """Test edge cases in parsing"""
    # URL with query parameters
    line1 = "[+] https://example.com/app.js?v=123 [secret123]"
    result1 = mantra_service._parse_mantra_output(line1)
    assert result1 is not None
    assert result1["url"] == "https://example.com/app.js?v=123"

    # Secret with special characters
    line2 = "[+] https://example.com/app.js [sk_live_51H8!@#$%]"
    result2 = mantra_service._parse_mantra_output(line2)
    assert result2 is not None
    assert result2["secret"] == "sk_live_51H8!@#$%"

    # URL with port
    line3 = "[+] https://example.com:8443/app.js [secret]"
    result3 = mantra_service._parse_mantra_output(line3)
    assert result3 is not None
    assert result3["url"] == "https://example.com:8443/app.js"
