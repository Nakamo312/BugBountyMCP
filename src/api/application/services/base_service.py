import asyncio
import logging
import re
from abc import ABC, abstractmethod
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlparse

from api.application.exceptions import ScanExecutionError, ToolNotFoundError
from api.domain.enums import RuleType
from api.domain.models import ScopeRuleModel

logger = logging.getLogger(__name__)

# Constants
DEFAULT_SCAN_TIMEOUT = 600  # seconds


class CommandExecutionMixin:
    """Mixin for executing external commands"""
    
    async def exec_stream(
        self, 
        command: List[str], 
        stdin: Optional[str] = None,  
        timeout: int = DEFAULT_SCAN_TIMEOUT, 
        cwd: Optional[str] = None
    ) -> AsyncIterator[str]:
        """
        Execute command and stream output line by line.
        
        Args:
            command: Command and arguments to execute
            stdin: Optional input to send to process
            timeout: Maximum execution time in seconds
            cwd: Working directory for command
            
        Yields:
            Output lines from stdout
            
        Raises:
            ToolNotFoundError: If command binary not found
            ScanExecutionError: If process fails or times out
        """
        self.logger.info(f"Executing: {' '.join(command)}")
        
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                stdin=asyncio.subprocess.PIPE if stdin else None,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd
            )
        except FileNotFoundError:
            raise ToolNotFoundError(tool_name=command[0], path=command[0])
        except Exception as e:
            raise ScanExecutionError(f"Failed to start process: {str(e)}")

        # Send stdin if provided
        if stdin:
            try:
                process.stdin.write(stdin.encode())
                await process.stdin.drain()
                process.stdin.close()
            except Exception as e:
                process.kill()
                await process.wait()
                raise ScanExecutionError(f"Failed to write stdin: {str(e)}")

        try:
            # Stream stdout line by line
            async for line in process.stdout:
                decoded = line.decode(errors='ignore').strip()
                if decoded:
                    yield decoded

            # Wait for process to complete
            exit_code = await asyncio.wait_for(process.wait(), timeout=timeout)
            
            # Log errors if process failed
            if exit_code != 0:
                stderr = await process.stderr.read()
                error_msg = stderr.decode(errors='ignore')
                self.logger.error(f"Tool exited with code {exit_code}: {error_msg}")

        except asyncio.TimeoutError:
            self.logger.warning(f"Process timeout after {timeout}s")
            process.kill()
            await process.wait()
            raise ScanExecutionError(f"Process timed out after {timeout}s")
        except asyncio.CancelledError:
            self.logger.warning("Process cancelled by user")
            process.kill()
            await process.wait()
            raise
        except Exception as e:
            process.kill()
            await process.wait()
            raise ScanExecutionError(f"Process execution failed: {str(e)}")

    async def exec_command(
        self,
        command: List[str],
        timeout: int = DEFAULT_SCAN_TIMEOUT,
        cwd: Optional[str] = None
    ) -> Tuple[str, str, int]:
        """
        Execute command and return full output.
        
        Args:
            command: Command and arguments to execute
            timeout: Maximum execution time in seconds
            cwd: Working directory for command
            
        Returns:
            Tuple of (stdout, stderr, return_code)
            
        Raises:
            ToolNotFoundError: If command binary not found
            ScanExecutionError: If process times out
        """
        self.logger.info(f"Executing: {' '.join(command)}")
        
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd
            )
        except FileNotFoundError:
            raise ToolNotFoundError(tool_name=command[0], path=command[0])
        except Exception as e:
            raise ScanExecutionError(f"Failed to start process: {str(e)}")
            
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=timeout
            )
            return (
                stdout.decode(errors='ignore'),
                stderr.decode(errors='ignore'),
                process.returncode
            )
        except asyncio.TimeoutError:
            self.logger.warning(f"Process timeout after {timeout}s")
            process.kill()
            await process.wait()
            raise ScanExecutionError(f"Process timed out after {timeout}s")
        except asyncio.CancelledError:
            self.logger.warning("Process cancelled by user")
            process.kill()
            await process.wait()
            raise

        
class URLParseMixin:
    """Mixin for URL parsing utilities"""
    
    @staticmethod
    def split_path_and_params(full_path: str) -> Tuple[str, Dict[str, str]]:
        """
        Split path and query parameters from URL.
        
        Args:
            full_path: Full URL path with query string
            
        Returns:
            Tuple of (path, query_params_dict)
            
        Example:
            "/api/data?x=y&z=1" -> ("/api/data", {"x": "y", "z": "1"})
        """
        parsed = urlparse(full_path)
        path = parsed.path or "/"
        query_params = {k: v[0] for k, v in parse_qs(parsed.query).items()}
        return path, query_params
    

class URLUtilsMixin:
    """Mixin for URL filtering utilities"""
    
    # Static file extensions to filter out
    STATIC_EXTENSIONS = (
        '.css', '.png', '.jpg', '.jpeg', '.gif', '.svg',
        '.woff', '.woff2', '.ttf', '.eot', '.mp4', '.mp3',
        '.pdf', '.doc', '.docx', '.htm', '.webp', '.ico'
    )
    
    @classmethod
    def filter_static_urls(cls, url: str) -> bool:
        """
        Check if URL should be filtered out as static content.
        
        Args:
            url: URL to check
            
        Returns:
            True if URL should be kept, False if should be filtered
        """
        url_lower = url.lower()
        return not any(url_lower.endswith(ext) for ext in cls.STATIC_EXTENSIONS)

    @staticmethod
    def is_js_url(url: str) -> bool:
        """Check if URL points to JavaScript file"""
        url_lower = url.lower()
        return url_lower.endswith('.js') or '.js?' in url_lower

    @staticmethod
    def extract_host_from_url(url: str) -> Optional[str]:
        """
        Extract hostname from URL.

        Args:
            url: Full URL

        Returns:
            Hostname or None if parsing fails
        """
        try:
            return urlparse(url).netloc
        except Exception:
            return None


class ScopeCheckMixin:
    """Mixin for scope validation"""

    @staticmethod
    def is_in_scope(target: str, scope_rules: List[ScopeRuleModel]) -> bool:
        """
        Check if target matches program scope rules.

        Args:
            target: Domain or URL to check
            scope_rules: List of program scope rules

        Returns:
            True if target is in scope
        """
        if not scope_rules:
            return True

        parsed = urlparse(target if target.startswith(('http://', 'https://')) else f'http://{target}')
        domain = parsed.hostname

        if not domain:
            return False

        for rule in scope_rules:
            if rule.rule_type == RuleType.DOMAIN:
                if domain == rule.pattern or domain.endswith(f".{rule.pattern}"):
                    return True

            elif rule.rule_type == RuleType.REGEX:
                if re.match(rule.pattern, target):
                    return True

        return False

    @staticmethod
    def filter_in_scope(targets: List[str], scope_rules: List[ScopeRuleModel]) -> Tuple[List[str], List[str]]:
        """
        Filter targets by scope rules.

        Args:
            targets: List of domains or URLs
            scope_rules: List of program scope rules

        Returns:
            Tuple of (in_scope_targets, out_of_scope_targets)
        """
        in_scope = []
        out_of_scope = []

        for target in targets:
            if ScopeCheckMixin.is_in_scope(target, scope_rules):
                in_scope.append(target)
            else:
                out_of_scope.append(target)

        return in_scope, out_of_scope


class BaseScanService(ABC):
    """Base class for all scan services"""
    
    def __init__(self):
        self.name = self.__class__.__name__
        self.logger = logging.getLogger(f"service.{self.name}")

    @abstractmethod
    async def execute(self, *args, **kwargs):
        """Execute scan service - must be implemented by subclasses"""
        pass

    async def save_results(self, data: Dict[str, Any]) -> None:
        """Optional method to save scan results"""
        pass
