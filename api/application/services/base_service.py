"""Base service for all scanners"""
import asyncio
import logging
from abc import ABC, abstractmethod
from typing import AsyncIterator, Optional, List, Dict, Any
from uuid import UUID

logger = logging.getLogger(__name__)


class BaseService(ABC):
    """Abstract base service for all scanning operations"""
    
    def __init__(self):
        self.name = self.__class__.__name__
        self.logger = logging.getLogger(f"service.{self.name}")
    
    @abstractmethod
    async def execute(self, *args, **kwargs) -> Any:
        """Main execution method - must be implemented by subclass"""
        pass
    
    async def _exec_stream(
        self, 
        command: List[str], 
        timeout: int = 600,
        cwd: Optional[str] = None
    ) -> AsyncIterator[str]:
        """Execute command and stream output line by line"""
        self.logger.info(f"Executing: {' '.join(command)}")
        
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd
            )
            
            async def read_stream(stream):
                while True:
                    line = await stream.readline()
                    if not line:
                        break
                    decoded = line.decode('utf-8', errors='ignore').strip()
                    if decoded:
                        yield decoded
            
            async for line in read_stream(process.stdout):
                yield line
            
            try:
                await asyncio.wait_for(process.wait(), timeout=timeout)
            except asyncio.TimeoutError:
                self.logger.warning(f"Process timeout after {timeout}s")
                process.kill()
                await process.wait()
                
        except Exception as e:
            self.logger.error(f"Execution error: {e}")
            raise
    
    async def _exec_command(
        self,
        command: List[str],
        timeout: int = 600,
        cwd: Optional[str] = None
    ) -> tuple[str, str, int]:
        """Execute command and return (stdout, stderr, returncode)"""
        self.logger.info(f"Executing: {' '.join(command)}")
        
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd
            )
            
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), 
                timeout=timeout
            )
            
            return (
                stdout.decode('utf-8', errors='ignore'),
                stderr.decode('utf-8', errors='ignore'),
                process.returncode
            )
            
        except asyncio.TimeoutError:
            self.logger.warning(f"Process timeout after {timeout}s")
            process.kill()
            await process.wait()
            raise
        except Exception as e:
            self.logger.error(f"Execution error: {e}")
            raise
    
    def _filter_static_urls(self, url: str) -> bool:
        """Filter out static files"""
        static_extensions = [
            '.css', '.png', '.jpg', '.jpeg', '.gif', '.svg',
            '.woff', '.woff2', '.ttf', '.eot', '.mp4', '.mp3',
            '.pdf', '.doc', '.docx', '.htm', '.webp', '.ico'
        ]
        url_lower = url.lower()
        return not any(url_lower.endswith(ext) for ext in static_extensions)
    
    def _is_js_url(self, url: str) -> bool:
        """Check if URL is JavaScript file"""
        return url.lower().endswith('.js') or '.js?' in url.lower()
    
    def _extract_host_from_url(self, url: str) -> Optional[str]:
        """Extract host from URL"""
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            return parsed.netloc
        except Exception:
            return None
    
    async def _save_results(self, data: Dict[str, Any]) -> None:
        """Template method for saving results - override if needed"""
        pass
