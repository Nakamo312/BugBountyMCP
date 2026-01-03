import pytest
from unittest.mock import AsyncMock
from uuid import uuid4

from api.application.services.ffuf import FFUFScanService


@pytest.fixture
def mock_ffuf_runner():
    return AsyncMock()


@pytest.fixture
def mock_event_bus():
    bus = AsyncMock()
    bus.publish = AsyncMock()
    return bus


@pytest.fixture
def ffuf_service(mock_ffuf_runner, mock_event_bus):
    return FFUFScanService(runner=mock_ffuf_runner, bus=mock_event_bus)


@pytest.mark.asyncio
async def test_parse_ffuf_jsonline_valid(ffuf_service):
    """Test parsing valid FFUF JSON line"""
    line = '{"url":"https://example.com/admin","status":200,"length":1234,"words":100,"lines":50,"content-type":"text/html","redirectlocation":""}'

    result = ffuf_service._parse_ffuf_jsonline(line)

    assert result is not None
    assert result["url"] == "https://example.com/admin"
    assert result["status"] == 200
    assert result["length"] == 1234
    assert result["words"] == 100
    assert result["lines"] == 50
    assert result["content_type"] == "text/html"
    assert result["redirect_location"] == ""


@pytest.mark.asyncio
async def test_parse_ffuf_jsonline_with_redirect(ffuf_service):
    """Test parsing FFUF JSON with redirect location"""
    line = '{"url":"https://example.com/old","status":301,"length":0,"words":0,"lines":0,"redirectlocation":"https://example.com/new"}'

    result = ffuf_service._parse_ffuf_jsonline(line)

    assert result is not None
    assert result["url"] == "https://example.com/old"
    assert result["status"] == 301
    assert result["redirect_location"] == "https://example.com/new"


@pytest.mark.asyncio
async def test_parse_ffuf_jsonline_invalid_json(ffuf_service):
    """Test that invalid JSON returns None"""
    invalid_lines = [
        "not json at all",
        "{incomplete json",
        "",
        "   ",
    ]

    for line in invalid_lines:
        result = ffuf_service._parse_ffuf_jsonline(line)
        assert result is None


@pytest.mark.asyncio
async def test_parse_ffuf_jsonline_missing_fields(ffuf_service):
    """Test parsing JSON with missing optional fields"""
    line = '{"url":"https://example.com/page","status":200}'

    result = ffuf_service._parse_ffuf_jsonline(line)

    assert result is not None
    assert result["url"] == "https://example.com/page"
    assert result["status"] == 200
    assert result["content_type"] == ""
    assert result["redirect_location"] == ""


def test_filter_static_files_removes_extensions(ffuf_service):
    """Test that static file extensions are filtered out"""
    results = [
        {"url": "https://example.com/admin", "status": 200},
        {"url": "https://example.com/style.css", "status": 200},
        {"url": "https://example.com/logo.png", "status": 200},
        {"url": "https://example.com/api", "status": 200},
        {"url": "https://example.com/icon.svg", "status": 200},
    ]

    filtered = ffuf_service._filter_static_files(results)

    # .js is NOT filtered by FFUF (it filters .css, .png, .svg but keeps .js for endpoints)
    assert len(filtered) == 2
    assert filtered[0]["url"] == "https://example.com/admin"
    assert filtered[1]["url"] == "https://example.com/api"


def test_filter_static_files_case_insensitive(ffuf_service):
    """Test that filtering is case insensitive"""
    results = [
        {"url": "https://example.com/Style.CSS", "status": 200},
        {"url": "https://example.com/Image.PNG", "status": 200},
        {"url": "https://example.com/Admin.PHP", "status": 200},
    ]

    filtered = ffuf_service._filter_static_files(results)

    assert len(filtered) == 1
    assert filtered[0]["url"] == "https://example.com/Admin.PHP"


def test_filter_static_files_keeps_php_html(ffuf_service):
    """Test that .php and .html files are NOT filtered"""
    results = [
        {"url": "https://example.com/admin.php", "status": 200},
        {"url": "https://example.com/index.html", "status": 200},
        {"url": "https://example.com/page.aspx", "status": 200},
    ]

    filtered = ffuf_service._filter_static_files(results)

    assert len(filtered) == 3


def test_filter_static_files_handles_query_params(ffuf_service):
    """Test filtering with query parameters in URL - filters by extension before ?"""
    results = [
        {"url": "https://example.com/api?page=1", "status": 200},
        {"url": "https://example.com/image.png?v=123", "status": 200},
        {"url": "https://example.com/style.css?v=456", "status": 200},
    ]

    filtered = ffuf_service._filter_static_files(results)

    # Filters by checking if URL ends with extension OR path part ends with extension
    # "image.png?v=123" - path_with_query is "example.com/image.png?v=123", ends check fails, but endswith('.png') passes
    # Current implementation checks path_with_query which is everything after ://
    assert len(filtered) == 1
    assert filtered[0]["url"] == "https://example.com/api?page=1"


def test_filter_static_files_handles_paths_with_extension(ffuf_service):
    """Test filtering paths that end with static extensions"""
    results = [
        {"url": "https://example.com/files/doc.pdf", "status": 200},
        {"url": "https://example.com/assets/font.woff2", "status": 200},
        {"url": "https://example.com/admin/panel", "status": 200},
    ]

    filtered = ffuf_service._filter_static_files(results)

    assert len(filtered) == 1
    assert filtered[0]["url"] == "https://example.com/admin/panel"


def test_filter_static_files_handles_empty_url(ffuf_service):
    """Test that empty URLs are skipped"""
    results = [
        {"url": "", "status": 200},
        {"url": "https://example.com/admin", "status": 200},
        {"status": 200},  # Missing url field
    ]

    filtered = ffuf_service._filter_static_files(results)

    assert len(filtered) == 1
    assert filtered[0]["url"] == "https://example.com/admin"


def test_filter_static_files_all_extensions(ffuf_service):
    """Test all static extensions are filtered"""
    static_extensions = [
        '.css', '.png', '.jpg', '.jpeg', '.gif', '.svg', '.woff', '.woff2',
        '.ttf', '.eot', '.mp4', '.mp3', '.pdf', '.ico', '.webp', '.otf'
    ]

    results = [
        {"url": f"https://example.com/file{ext}", "status": 200}
        for ext in static_extensions
    ]
    results.append({"url": "https://example.com/api", "status": 200})

    filtered = ffuf_service._filter_static_files(results)

    assert len(filtered) == 1
    assert filtered[0]["url"] == "https://example.com/api"


@pytest.mark.asyncio
async def test_execute_returns_dto(ffuf_service, mock_ffuf_runner):
    """Test that execute returns FFUFScanOutputDTO immediately"""
    program_id = uuid4()
    targets = ["https://example.com"]

    async def empty_gen():
        return
        yield

    mock_ffuf_runner.run = AsyncMock(return_value=empty_gen())

    result = await ffuf_service.execute(program_id, targets)

    assert result.status == "started"
    assert result.scanner == "ffuf"
    assert result.targets_count == 1
    assert "FFUF scan started" in result.message


@pytest.mark.asyncio
async def test_execute_multiple_targets(ffuf_service, mock_ffuf_runner):
    """Test execute with multiple targets"""
    program_id = uuid4()
    targets = ["https://example.com", "https://test.com", "https://api.example.com"]

    async def empty_gen():
        return
        yield

    mock_ffuf_runner.run = AsyncMock(return_value=empty_gen())

    result = await ffuf_service.execute(program_id, targets)

    assert result.targets_count == 3
    assert "3 targets" in result.message


def test_filter_static_files_empty_list(ffuf_service):
    """Test filtering empty results list"""
    filtered = ffuf_service._filter_static_files([])

    assert filtered == []
