"""Playwright gRPC client runner for interactive web crawling"""
import logging
from typing import AsyncIterator
import grpc

from api.infrastructure.schemas.models.process_event import ProcessEvent

logger = logging.getLogger(__name__)


class PlaywrightCliRunner:
    """
    Runner for Playwright scanner.
    Connects to gRPC service and streams discovered requests.
    """

    def __init__(self, timeout: int = 600, grpc_host: str = "playwright:50051"):
        self.timeout = timeout
        self.grpc_host = grpc_host

    async def run(
        self,
        targets: list[str] | str,
        depth: int = 2,
    ) -> AsyncIterator[ProcessEvent]:
        """
        Execute playwright scanner for given targets via gRPC.

        Args:
            targets: Single target URL or list of target URLs to crawl
            depth: Maximum crawl depth (default: 2)

        Yields:
            ProcessEvent with type="result" and payload=json_data
        """
        if isinstance(targets, str):
            targets = [targets]

        try:
            from api.infrastructure.runners import scanner_pb2, scanner_pb2_grpc
        except ImportError as e:
            logger.error(f"gRPC import error: {e}")
            return

        async with grpc.aio.insecure_channel(self.grpc_host) as channel:
            stub = scanner_pb2_grpc.PlaywrightScannerStub(channel)

            for target in targets:
                request = scanner_pb2.ScanRequest(url=target, max_depth=depth)

                logger.info(f"Starting Playwright scanner for {target} via gRPC")

                result_count = 0

                try:
                    async for response in stub.Scan(request, timeout=self.timeout):
                        if response.HasField("error"):
                            logger.error(f"Playwright error: {response.error.message}")
                            continue

                        if response.HasField("data"):
                            katana_data = response.data

                            json_data = {
                                "request": {
                                    "method": katana_data.request.method,
                                    "endpoint": katana_data.request.endpoint,
                                    "headers": dict(katana_data.request.headers),
                                    "raw": katana_data.request.raw,
                                },
                                "response": {
                                    "status_code": katana_data.response.status_code,
                                    "headers": dict(katana_data.response.headers),
                                },
                                "timestamp": katana_data.timestamp,
                            }

                            if katana_data.request.body:
                                json_data["request"]["body"] = katana_data.request.body

                            result_count += 1
                            yield ProcessEvent(type="result", payload=json_data)

                except grpc.aio.AioRpcError as e:
                    logger.error(f"gRPC error for {target}: {e.code()} - {e.details()}")

                logger.info(f"Playwright scanner completed for {target}: {result_count} requests")
