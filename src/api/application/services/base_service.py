import asyncio
import logging
from abc import ABC, abstractmethod
from typing import AsyncGenerator, AsyncIterator, Optional, List, Dict, Any, Tuple
from urllib.parse import parse_qs, urlparse

from api.application.exceptions import ScanExecutionError, ToolNotFoundError

logger = logging.getLogger(__name__)


class CommandExecutionMixin:
    async def exec_stream(
        self, 
        command: List[str], 
        stdin: Optional[str] = None,  
        timeout: int = 600, 
        cwd: Optional[str] = None
    ) -> AsyncIterator[str]:
        self.logger.info(f"Executing: {' '.join(command)}")
        
        program = command[0]
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                stdin=asyncio.subprocess.PIPE if stdin else None,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd
            )

            if stdin:
                process.stdin.write(stdin.encode())
                await process.stdin.drain()
                process.stdin.close() 

        except FileNotFoundError:
            raise ToolNotFoundError(tool_name=program, path=program)
        except Exception as e:
            raise ScanExecutionError(f"Failed to start process: {str(e)}")

        try:
            async for line in process.stdout:
                decoded = line.decode(errors='ignore').strip()
                if decoded:
                    yield decoded

            exit_code = await asyncio.wait_for(process.wait(), timeout=timeout)
            
            if exit_code != 0:
                stderr = await process.stderr.read()
                raise ScanExecutionError(f"Tool exited with code {exit_code}: {stderr.decode()}")

        except asyncio.TimeoutError:
            self.logger.warning(f"Process timeout after {timeout}s")
            process.kill()
            await process.wait()
            raise ScanExecutionError(f"Process timed out after {timeout}s")

        except FileNotFoundError:
            raise ToolNotFoundError(tool_name=command[0], path=command[0])
        except Exception as e:
            raise ScanExecutionError(f"Failed to start process: {str(e)}")
        try:
            async for line in process.stdout:
                decoded = line.decode(errors='ignore').strip()
                if decoded:
                    yield decoded

            await asyncio.wait_for(process.wait(), timeout=timeout)
            
            if process.returncode != 0 and process.returncode is not None:
                stderr_data = await process.stderr.read()
                self.logger.error(f"Tool exited with code {process.returncode}: {stderr_data.decode()}")

        except asyncio.TimeoutError:
            self.logger.warning(f"Process timeout after {timeout}s")
            process.kill()
            await process.wait()
            raise ScanExecutionError(f"Process timed out after {timeout}s")

        async def reader(stream):
            while True:
                line = await stream.readline()
                if not line:
                    break
                decoded = line.decode(errors='ignore').strip()
                if decoded:
                    yield decoded

        async for line in reader(process.stdout):
            yield line

        try:
            await asyncio.wait_for(process.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            self.logger.warning(f"Process timeout after {timeout}s")
            process.kill()
            await process.wait()

    async def exec_command(
        self,
        command: List[str],
        timeout: int = 600,
        cwd: Optional[str] = None
    ) -> tuple[str, str, int]:
        self.logger.info(f"Executing: {' '.join(command)}")
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd
        )
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
            raise
        
class URLParseMixin:
    @staticmethod
    def split_path_and_params(full_path: str) -> Tuple[str, Dict[str, str]]:
        """
        Разделяет path и query-параметры из URL.
        Например: "/api/data?x=y&z=1" -> ("/api/data", {"x": "y", "z": "1"})
        """
        parsed = urlparse(full_path)
        path = parsed.path or "/"
        query_params = {k: v[0] for k, v in parse_qs(parsed.query).items()}
        return path, query_params
    

class URLUtilsMixin:
    @staticmethod
    def filter_static_urls(url: str) -> bool:
        static_ext = [
            '.css', '.png', '.jpg', '.jpeg', '.gif', '.svg',
            '.woff', '.woff2', '.ttf', '.eot', '.mp4', '.mp3',
            '.pdf', '.doc', '.docx', '.htm', '.webp', '.ico'
        ]
        url_lower = url.lower()
        return not any(url_lower.endswith(ext) for ext in static_ext)

    @staticmethod
    def is_js_url(url: str) -> bool:
        return url.lower().endswith('.js') or '.js?' in url.lower()

    @staticmethod
    def extract_host_from_url(url: str) -> Optional[str]:
        try:
            from urllib.parse import urlparse
            return urlparse(url).netloc
        except Exception:
            return None


class BaseScanService(ABC):
    def __init__(self):
        self.name = self.__class__.__name__
        self.logger = logging.getLogger(f"service.{self.name}")

    @abstractmethod
    async def execute(self, *args, **kwargs):
        pass

    async def save_results(self, data: Dict[str, Any]) -> None:
        pass
