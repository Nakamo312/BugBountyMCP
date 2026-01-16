"""Base batch processor for streaming results from CLI runners"""
import asyncio
from typing import AsyncIterator, List, TypeVar, Generic, Dict, Any, Set
from abc import ABC, abstractmethod

from api.config import Settings

T = TypeVar('T')


class BaseBatchProcessor(ABC, Generic[T]):
    """
    Base class for batching streaming results from CLI runners.
    Yields batches based on size and time constraints.
    """

    def __init__(self, settings: Settings):
        """
        Initialize batch processor from Settings.

        Args:
            settings: Application settings with batch parameters
        """
        config = self._get_batch_config(settings)
        self.batch_size_min = config['min']
        self.batch_size_max = config['max']
        self.batch_timeout = config['timeout']

    @abstractmethod
    def _get_batch_config(self, settings: Settings) -> Dict[str, Any]:
        """
        Get batch configuration from settings.

        Returns:
            Dict with 'min', 'max', 'timeout' keys
        """
        pass

    async def batch_stream(self, stream: AsyncIterator) -> AsyncIterator[List[T]]:
        """
        Collect items from stream and yield them in batches.

        Args:
            stream: Async iterator of events from CLI runner

        Yields:
            Batches of processed items
        """
        batch: List[T] = []
        last_batch_time = asyncio.get_event_loop().time()

        async for event in stream:
            item = self._extract_item(event)
            if item is None:
                continue

            batch.append(item)
            current_time = asyncio.get_event_loop().time()
            time_elapsed = current_time - last_batch_time

            if len(batch) >= self.batch_size_max:
                yield batch
                batch = []
                last_batch_time = current_time
            elif len(batch) >= self.batch_size_min and time_elapsed >= self.batch_timeout:
                yield batch
                batch = []
                last_batch_time = current_time

        if batch:
            yield batch

    @abstractmethod
    def _extract_item(self, event) -> T | None:
        """
        Extract item from event. Return None to skip event.

        Args:
            event: Event object from CLI runner

        Returns:
            Extracted item or None to skip
        """
        pass


class MapCIDRBatchProcessor(BaseBatchProcessor[str]):
    """Batch processor for MapCIDR results"""

    def _get_batch_config(self, settings: Settings) -> Dict[str, Any]:
        return {
            'min': settings.MAPCIDR_BATCH_MIN,
            'max': settings.MAPCIDR_BATCH_MAX,
            'timeout': settings.MAPCIDR_BATCH_TIMEOUT
        }

    def _extract_item(self, event) -> str | None:
        """Extract IP/CIDR string from event"""
        if event.type == "result" and event.payload:
            return event.payload
        return None


class HTTPXBatchProcessor(BaseBatchProcessor[Dict[str, Any]]):
    """Batch processor for HTTPX results"""

    def _get_batch_config(self, settings: Settings) -> Dict[str, Any]:
        return {
            'min': settings.HTTPX_BATCH_MIN,
            'max': settings.HTTPX_BATCH_MAX,
            'timeout': settings.HTTPX_BATCH_TIMEOUT
        }

    def _extract_item(self, event) -> Dict[str, Any] | None:
        """Extract HTTPX result from event"""
        if event.type == "result" and event.payload:
            return event.payload
        return None


class SubfinderBatchProcessor(BaseBatchProcessor[str]):
    """Batch processor for Subfinder subdomains"""

    def _get_batch_config(self, settings: Settings) -> Dict[str, Any]:
        return {
            'min': settings.SUBFINDER_BATCH_MIN,
            'max': settings.SUBFINDER_BATCH_MAX,
            'timeout': settings.SUBFINDER_BATCH_TIMEOUT
        }

    def _extract_item(self, event) -> str | None:
        """Extract subdomain from event"""
        if event.type == "subdomain" and event.payload:
            return event.payload
        return None


class GAUBatchProcessor(BaseBatchProcessor[str]):
    """Batch processor for GAU URLs with deduplication"""

    def _get_batch_config(self, settings: Settings) -> Dict[str, Any]:
        return {
            'min': settings.GAU_BATCH_MIN,
            'max': settings.GAU_BATCH_MAX,
            'timeout': settings.GAU_BATCH_TIMEOUT
        }

    async def batch_stream(self, stream: AsyncIterator) -> AsyncIterator[List[str]]:
        """Collect URLs with per-scan deduplication"""
        batch: List[str] = []
        last_batch_time = asyncio.get_event_loop().time()
        seen_urls: Set[str] = set()

        async for event in stream:
            item = self._extract_item(event, seen_urls)
            if item is None:
                continue

            batch.append(item)
            current_time = asyncio.get_event_loop().time()
            time_elapsed = current_time - last_batch_time

            if len(batch) >= self.batch_size_max:
                yield batch
                batch = []
                last_batch_time = current_time
            elif len(batch) >= self.batch_size_min and time_elapsed >= self.batch_timeout:
                yield batch
                batch = []
                last_batch_time = current_time

        if batch:
            yield batch

    def _extract_item(self, event, seen_urls: Set[str]) -> str | None:
        """Extract URL from event with deduplication"""
        if event.type != "url":
            return None

        url = event.payload
        if url in seen_urls:
            return None

        seen_urls.add(url)
        return url


class KatanaBatchProcessor(BaseBatchProcessor[Dict[str, Any]]):
    """Batch processor for Katana crawl results"""

    def _get_batch_config(self, settings: Settings) -> Dict[str, Any]:
        return {
            'min': settings.KATANA_BATCH_MIN,
            'max': settings.KATANA_BATCH_MAX,
            'timeout': settings.KATANA_BATCH_TIMEOUT
        }

    def _extract_item(self, event) -> Dict[str, Any] | None:
        """Extract Katana result from event"""
        if event.type == "result" and event.payload:
            return event.payload
        return None


class DNSxBatchProcessor(BaseBatchProcessor[Dict[str, Any]]):
    """Batch processor for DNSx results"""

    def _get_batch_config(self, settings: Settings) -> Dict[str, Any]:
        return {
            'min': settings.DNSX_BATCH_MIN,
            'max': settings.DNSX_BATCH_MAX,
            'timeout': settings.DNSX_BATCH_TIMEOUT
        }

    def _extract_item(self, event) -> Dict[str, Any] | None:
        """Extract DNSx result from event"""
        if event.type == "result" and event.payload:
            return event.payload
        return None


class SubjackBatchProcessor(BaseBatchProcessor[Dict[str, Any]]):
    """Batch processor for Subjack subdomain takeover results"""

    def _get_batch_config(self, settings: Settings) -> Dict[str, Any]:
        return {
            'min': settings.HTTPX_BATCH_MIN,
            'max': settings.HTTPX_BATCH_MAX,
            'timeout': settings.HTTPX_BATCH_TIMEOUT
        }

    def _extract_item(self, event) -> Dict[str, Any] | None:
        """Extract Subjack result from event"""
        if event.type == "result" and event.payload:
            return event.payload
        return None


class ASNMapBatchProcessor(BaseBatchProcessor[Dict[str, Any]]):
    """Batch processor for ASNMap results"""

    def _get_batch_config(self, settings: Settings) -> Dict[str, Any]:
        return {
            'min': settings.ASNMAP_BATCH_MIN,
            'max': settings.ASNMAP_BATCH_MAX,
            'timeout': settings.ASNMAP_BATCH_TIMEOUT
        }

    def _extract_item(self, event) -> Dict[str, Any] | None:
        """Extract ASNMap result from event"""
        if event.type == "result" and event.payload:
            return event.payload
        return None


class NaabuBatchProcessor(BaseBatchProcessor[Dict[str, Any]]):
    """Batch processor for Naabu port scan results"""

    def _get_batch_config(self, settings: Settings) -> Dict[str, Any]:
        return {
            'min': settings.NAABU_BATCH_MIN,
            'max': settings.NAABU_BATCH_MAX,
            'timeout': settings.NAABU_BATCH_TIMEOUT
        }

    def _extract_item(self, event) -> Dict[str, Any] | None:
        """Extract Naabu result from event"""
        if event.type == "result" and event.payload:
            return event.payload
        return None


class TLSxBatchProcessor(BaseBatchProcessor[Dict[str, Any]]):
    """Batch processor for TLSx certificate scan results"""

    def _get_batch_config(self, settings: Settings) -> Dict[str, Any]:
        return {
            'min': settings.TLSX_BATCH_MIN,
            'max': settings.TLSX_BATCH_MAX,
            'timeout': settings.TLSX_BATCH_TIMEOUT
        }

    def _extract_item(self, event) -> Dict[str, Any] | None:
        """Extract TLSx result from event"""
        if event.type == "result" and event.payload:
            return event.payload
        return None


class SmapBatchProcessor(BaseBatchProcessor[Dict[str, Any]]):
    """Batch processor for Smap port scan results"""

    def __init__(self, settings: Settings):
        super().__init__(settings)

    def _get_batch_config(self, settings: Settings) -> Dict[str, Any]:
        return {
            'min': 10,
            'max': 100,
            'timeout': 20.0
        }

    def _extract_item(self, event) -> Dict[str, Any] | None:
        """Extract Smap result from event"""
        if event.type == "result" and event.payload:
            return event.payload
        return None


class Hakip2HostBatchProcessor(BaseBatchProcessor[Dict[str, Any]]):
    """Batch processor for hakip2host reverse DNS/SSL results"""

    def __init__(self, settings: Settings):
        super().__init__(settings)

    def _get_batch_config(self, settings: Settings) -> Dict[str, Any]:
        return {
            'min': 50,
            'max': 200,
            'timeout': 15.0
        }

    def _extract_item(self, event) -> Dict[str, Any] | None:
        """Extract hakip2host result from event"""
        if event.type == "result" and event.payload:
            return event.payload
        return None
