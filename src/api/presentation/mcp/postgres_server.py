"""Standalone stdio MCP server for curated Postgres artifact reads."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from typing import Any

import uvicorn
from fastapi import FastAPI, Request

from api.config import Settings
from api.infrastructure.artifacts.postgres_reader import PostgresArtifactReader
from api.infrastructure.database.connection import DatabaseConnection
from api.presentation.mcp.tools import TOOL_DEFINITIONS, call_tool

PROTOCOL_VERSION = "2024-11-05"


class StdioMCPServer:
    def __init__(self, reader: PostgresArtifactReader):
        self.reader = reader

    async def handle(self, message: dict[str, Any]) -> dict[str, Any] | None:
        if "id" not in message:
            return None

        method = message.get("method")
        try:
            if method == "initialize":
                result = {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "bugbounty-postgres-mcp", "version": "0.1.0"},
                }
            elif method == "tools/list":
                result = {"tools": TOOL_DEFINITIONS}
            elif method == "tools/call":
                params = message.get("params") or {}
                tool_result = await call_tool(
                    self.reader,
                    str(params.get("name")),
                    params.get("arguments") or {},
                )
                result = {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(tool_result, ensure_ascii=False, separators=(",", ":")),
                        }
                    ]
                }
            else:
                return self._error(message["id"], -32601, f"Method not found: {method}")
            return {"jsonrpc": "2.0", "id": message["id"], "result": result}
        except Exception as exc:
            logging.exception("MCP request failed")
            return self._error(message["id"], -32603, str(exc))

    @staticmethod
    def _error(request_id: Any, code: int, message: str) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    db = DatabaseConnection(settings.postgres_mcp_dsn)
    server = StdioMCPServer(PostgresArtifactReader(db.session_factory))
    app = FastAPI(title="BugBounty Postgres MCP", version="0.1.0")

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/mcp")
    async def mcp(request: Request) -> Any:
        payload = await request.json()
        if isinstance(payload, list):
            responses = [await server.handle(message) for message in payload]
            return [response for response in responses if response is not None]
        return await server.handle(payload)

    @app.on_event("shutdown")
    async def shutdown() -> None:
        await db.close()

    return app


async def read_message() -> dict[str, Any] | None:
    headers: dict[str, str] = {}
    while True:
        line = await asyncio.to_thread(sys.stdin.buffer.readline)
        if line == b"":
            return None
        line_text = line.decode("ascii").strip()
        if not line_text:
            break
        name, value = line_text.split(":", 1)
        headers[name.lower()] = value.strip()

    content_length = int(headers.get("content-length", "0"))
    if content_length <= 0:
        return None
    payload = await asyncio.to_thread(sys.stdin.buffer.read, content_length)
    return json.loads(payload.decode("utf-8"))


async def write_message(message: dict[str, Any]) -> None:
    payload = json.dumps(message, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    header = f"Content-Length: {len(payload)}\r\n\r\n".encode("ascii")
    await asyncio.to_thread(sys.stdout.buffer.write, header + payload)
    await asyncio.to_thread(sys.stdout.buffer.flush)


async def serve() -> None:
    settings = Settings()
    logging.basicConfig(level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO), stream=sys.stderr)
    db = DatabaseConnection(settings.postgres_mcp_dsn)
    server = StdioMCPServer(PostgresArtifactReader(db.session_factory))
    try:
        while True:
            message = await read_message()
            if message is None:
                break
            response = await server.handle(message)
            if response is not None:
                await write_message(response)
    finally:
        await db.close()


def main() -> None:
    settings = Settings()
    if settings.POSTGRES_MCP_TRANSPORT == "stdio" or os.environ.get("MCP_TRANSPORT") == "stdio":
        asyncio.run(serve())
        return
    uvicorn.run(
        create_app(settings),
        host=settings.POSTGRES_MCP_HOST,
        port=settings.POSTGRES_MCP_PORT,
        log_level=settings.LOG_LEVEL.lower(),
    )


if __name__ == "__main__":
    main()
