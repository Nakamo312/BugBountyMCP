"""
gRPC service for Playwright scanning
Streams Katana-format results via gRPC
Each Scan() call opens independent stream for parallel execution
"""
import asyncio
import json
import sys
from concurrent import futures
import grpc
from playwright_scanner import PlaywrightScanner
import scanner_pb2
import scanner_pb2_grpc


class PlaywrightScannerService(scanner_pb2_grpc.PlaywrightScannerServicer):
    """gRPC service implementation for Playwright scanning"""

    async def Scan(self, request, context):
        """Stream scan results as they arrive"""
        scanner = PlaywrightScanner(request.url, max_depth=request.max_depth)

        results_queue = asyncio.Queue()

        original_print = print

        def capture_print(*args, **kwargs):
            if args and isinstance(args[0], str):
                try:
                    data = json.loads(args[0])
                    asyncio.create_task(results_queue.put(data))
                except json.JSONDecodeError:
                    pass

        async def run_scan():
            import builtins
            builtins.print = capture_print
            try:
                await scanner.scan()
            except Exception as e:
                await results_queue.put({"error": str(e)})
            finally:
                builtins.print = original_print
                await results_queue.put(None)

        scan_task = asyncio.create_task(run_scan())

        try:
            while True:
                result = await results_queue.get()

                if result is None:
                    break

                if "error" in result:
                    yield scanner_pb2.ScanResult(
                        error=scanner_pb2.ScanError(message=result["error"])
                    )
                else:
                    req = result.get("request", {})
                    resp = result.get("response", {})

                    katana_output = scanner_pb2.KatanaOutput(
                        request=scanner_pb2.Request(
                            method=req.get("method", ""),
                            endpoint=req.get("endpoint", ""),
                            headers=req.get("headers", {}),
                            body=req.get("body"),
                            raw=req.get("raw", "")
                        ),
                        response=scanner_pb2.Response(
                            status_code=resp.get("status_code", 0),
                            headers=resp.get("headers", {})
                        ),
                        timestamp=result.get("timestamp", 0.0)
                    )

                    yield scanner_pb2.ScanResult(data=katana_output)

            await scan_task

        except Exception as e:
            yield scanner_pb2.ScanResult(
                error=scanner_pb2.ScanError(message=str(e))
            )

    async def HealthCheck(self, request, context):
        """Health check endpoint"""
        return scanner_pb2.HealthResponse(
            status="healthy",
            service="playwright-scanner"
        )


async def serve():
    """Start gRPC server with support for multiple concurrent streams"""
    server = grpc.aio.server(
        futures.ThreadPoolExecutor(max_workers=10),
        options=[
            ('grpc.max_concurrent_streams', 100),
            ('grpc.so_reuseport', 1),
        ]
    )
    scanner_pb2_grpc.add_PlaywrightScannerServicer_to_server(
        PlaywrightScannerService(), server
    )
    server.add_insecure_port('[::]:50051')
    await server.start()
    print("Playwright gRPC server listening on port 50051", file=sys.stderr)
    await server.wait_for_termination()


if __name__ == '__main__':
    asyncio.run(serve())
