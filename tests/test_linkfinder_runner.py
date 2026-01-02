import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from api.infrastructure.runners.linkfinder_cli import LinkFinderCliRunner
from api.infrastructure.schemas.models.process_event import ProcessEvent


@pytest.fixture
def linkfinder_runner():
    """LinkFinderCliRunner instance"""
    return LinkFinderCliRunner(linkfinder_path="linkfinder", timeout=15)


@pytest.mark.asyncio
async def test_run_domain_scan_uses_d_flag(linkfinder_runner):
    """Test run uses -d flag for domain scans"""
    targets = ["https://example.com"]

    with patch.object(linkfinder_runner, '_normalize_url', return_value="https://example.com/api"):
        with patch.object(linkfinder_runner, '_is_valid_url', return_value=True):
            mock_executor = AsyncMock()
            mock_executor.run = AsyncMock()

            stdout_event = ProcessEvent(type="stdout", payload="/api/users")
            async def mock_run():
                yield stdout_event

            mock_executor.run = mock_run

            with patch('api.infrastructure.runners.linkfinder_cli.CommandExecutor', return_value=mock_executor):
                results = []
                async for result in linkfinder_runner.run(targets):
                    results.append(result)

                # Check that CommandExecutor was called with -d flag
                from api.infrastructure.runners.linkfinder_cli import CommandExecutor
                call_args = CommandExecutor.call_args[0][0]
                assert "-d" in call_args
                assert "-i" in call_args
                assert "-o" in call_args
                assert "cli" in call_args


@pytest.mark.asyncio
async def test_run_js_file_scan_no_d_flag(linkfinder_runner):
    """Test run does not use -d flag for JS file scans"""
    targets = ["https://example.com/app.js"]

    with patch.object(linkfinder_runner, '_normalize_url', return_value="https://example.com/api"):
        with patch.object(linkfinder_runner, '_is_valid_url', return_value=True):
            mock_executor = AsyncMock()

            stdout_event = ProcessEvent(type="stdout", payload="/api/users")
            async def mock_run():
                yield stdout_event

            mock_executor.run = mock_run

            with patch('api.infrastructure.runners.linkfinder_cli.CommandExecutor', return_value=mock_executor):
                results = []
                async for result in linkfinder_runner.run(targets):
                    results.append(result)

                from api.infrastructure.runners.linkfinder_cli import CommandExecutor
                call_args = CommandExecutor.call_args[0][0]
                assert "-d" not in call_args


@pytest.mark.asyncio
async def test_run_wildcard_uses_d_flag(linkfinder_runner):
    """Test run uses -d flag for wildcard patterns"""
    targets = ["https://example.com/*.js"]

    with patch.object(linkfinder_runner, '_normalize_url', return_value="https://example.com/api"):
        with patch.object(linkfinder_runner, '_is_valid_url', return_value=True):
            mock_executor = AsyncMock()

            stdout_event = ProcessEvent(type="stdout", payload="/api/users")
            async def mock_run():
                yield stdout_event

            mock_executor.run = mock_run

            with patch('api.infrastructure.runners.linkfinder_cli.CommandExecutor', return_value=mock_executor):
                results = []
                async for result in linkfinder_runner.run(targets):
                    results.append(result)

                from api.infrastructure.runners.linkfinder_cli import CommandExecutor
                call_args = CommandExecutor.call_args[0][0]
                assert "-d" in call_args


@pytest.mark.asyncio
async def test_run_extracts_host_from_url(linkfinder_runner):
    """Test run extracts host from target URL"""
    targets = ["https://example.com/app.js"]

    mock_executor = AsyncMock()

    stdout_event = ProcessEvent(type="stdout", payload="/api/users")
    async def mock_run():
        yield stdout_event

    mock_executor.run = mock_run

    with patch('api.infrastructure.runners.linkfinder_cli.CommandExecutor', return_value=mock_executor):
        results = []
        async for result in linkfinder_runner.run(targets):
            results.append(result)

        assert len(results) == 1
        assert results[0].payload["host"] == "example.com"


@pytest.mark.asyncio
async def test_run_skips_urls_without_host(linkfinder_runner):
    """Test run skips targets without hostname"""
    targets = ["/relative/path"]

    results = []
    async for result in linkfinder_runner.run(targets):
        results.append(result)

    assert len(results) == 0


@pytest.mark.asyncio
async def test_normalize_url_handles_protocol_relative(linkfinder_runner):
    """Test _normalize_url handles protocol-relative URLs"""
    result = linkfinder_runner._normalize_url("//cdn.example.com/api", "example.com")
    assert result == "https://cdn.example.com/api"


@pytest.mark.asyncio
async def test_normalize_url_handles_absolute_path(linkfinder_runner):
    """Test _normalize_url handles absolute paths"""
    result = linkfinder_runner._normalize_url("/api/users", "example.com")
    assert result == "https://example.com/api/users"


@pytest.mark.asyncio
async def test_normalize_url_handles_full_url(linkfinder_runner):
    """Test _normalize_url preserves full URLs"""
    result = linkfinder_runner._normalize_url("https://example.com/api", "example.com")
    assert result == "https://example.com/api"


@pytest.mark.asyncio
async def test_normalize_url_returns_none_for_invalid(linkfinder_runner):
    """Test _normalize_url returns None for invalid URLs"""
    result = linkfinder_runner._normalize_url("javascript:void(0)", "example.com")
    assert result is None


@pytest.mark.asyncio
async def test_is_valid_url_accepts_http(linkfinder_runner):
    """Test _is_valid_url accepts http URLs"""
    assert linkfinder_runner._is_valid_url("http://example.com/api") is True


@pytest.mark.asyncio
async def test_is_valid_url_accepts_https(linkfinder_runner):
    """Test _is_valid_url accepts https URLs"""
    assert linkfinder_runner._is_valid_url("https://example.com/api") is True


@pytest.mark.asyncio
async def test_is_valid_url_rejects_static_files(linkfinder_runner):
    """Test _is_valid_url filters static file extensions"""
    assert linkfinder_runner._is_valid_url("https://example.com/style.css") is False
    assert linkfinder_runner._is_valid_url("https://example.com/image.png") is False
    assert linkfinder_runner._is_valid_url("https://example.com/icon.svg") is False
    assert linkfinder_runner._is_valid_url("https://example.com/font.woff") is False
    assert linkfinder_runner._is_valid_url("https://example.com/doc.pdf") is False


@pytest.mark.asyncio
async def test_is_valid_url_rejects_non_http(linkfinder_runner):
    """Test _is_valid_url rejects non-http URLs"""
    assert linkfinder_runner._is_valid_url("ftp://example.com/file") is False
    assert linkfinder_runner._is_valid_url("javascript:void(0)") is False
    assert linkfinder_runner._is_valid_url("") is False
    assert linkfinder_runner._is_valid_url(None) is False


@pytest.mark.asyncio
async def test_run_yields_result_event(linkfinder_runner):
    """Test run yields ProcessEvent with result type"""
    targets = ["https://example.com/app.js"]

    mock_executor = AsyncMock()

    stdout_event = ProcessEvent(type="stdout", payload="/api/users")
    async def mock_run():
        yield stdout_event

    mock_executor.run = mock_run

    with patch('api.infrastructure.runners.linkfinder_cli.CommandExecutor', return_value=mock_executor):
        results = []
        async for result in linkfinder_runner.run(targets):
            results.append(result)

        assert len(results) == 1
        assert results[0].type == "result"
        assert "urls" in results[0].payload
        assert "source_js" in results[0].payload
        assert "host" in results[0].payload


@pytest.mark.asyncio
async def test_run_handles_timeout(linkfinder_runner):
    """Test run handles timeout gracefully"""
    targets = ["https://example.com/app.js"]

    mock_executor = AsyncMock()

    async def mock_run():
        raise Exception("Timeout")
        yield

    mock_executor.run = mock_run

    with patch('api.infrastructure.runners.linkfinder_cli.CommandExecutor', return_value=mock_executor):
        results = []
        async for result in linkfinder_runner.run(targets):
            results.append(result)

        # Should not yield any results on error
        assert len(results) == 0


@pytest.mark.asyncio
async def test_run_processes_multiple_targets(linkfinder_runner):
    """Test run processes multiple JS files"""
    targets = ["https://example.com/app.js", "https://example.com/vendor.js"]

    mock_executor = AsyncMock()

    stdout_event = ProcessEvent(type="stdout", payload="/api/users")
    async def mock_run():
        yield stdout_event

    mock_executor.run = mock_run

    with patch('api.infrastructure.runners.linkfinder_cli.CommandExecutor', return_value=mock_executor):
        results = []
        async for result in linkfinder_runner.run(targets):
            results.append(result)

        # Should process both targets
        assert len(results) == 2


@pytest.mark.asyncio
async def test_run_filters_invalid_urls(linkfinder_runner):
    """Test run filters out invalid URLs"""
    targets = ["https://example.com/app.js"]

    mock_executor = AsyncMock()

    async def mock_run():
        yield ProcessEvent(type="stdout", payload="/api/users")
        yield ProcessEvent(type="stdout", payload="/style.css")
        yield ProcessEvent(type="stdout", payload="javascript:void(0)")

    mock_executor.run = mock_run

    with patch('api.infrastructure.runners.linkfinder_cli.CommandExecutor', return_value=mock_executor):
        results = []
        async for result in linkfinder_runner.run(targets):
            results.append(result)

        # Should only include valid /api/users URL
        assert len(results) == 1
        assert len(results[0].payload["urls"]) == 1
        assert "api/users" in results[0].payload["urls"][0]
