"""Line-oriented raw ProcessEvent parsers for CLI tools."""
from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator
from urllib.parse import urlparse

from api.infrastructure.schemas.models.process_event import ProcessEvent


class StdoutLineResultParser:
    """Emit non-empty stdout lines as result payloads."""

    async def parse_stream(self, stream: AsyncIterator[ProcessEvent]) -> AsyncIterator[ProcessEvent]:
        async for event in stream:
            if event.type == "stdout" and event.payload:
                value = event.payload.strip()
                if value:
                    yield ProcessEvent(type="result", payload=value)


class URLStdoutLineResultParser:
    """Emit stdout lines that look like HTTP URLs."""

    async def parse_stream(self, stream: AsyncIterator[ProcessEvent]) -> AsyncIterator[ProcessEvent]:
        async for event in stream:
            if event.type == "stdout" and event.payload:
                value = event.payload.strip()
                if value.startswith(("http://", "https://")):
                    yield ProcessEvent(type="result", payload=value)


class GAUStdoutParser:
    """Parse GAU stdout into URL result events."""

    _static_patterns = (
        ".css", ".js", ".svg", ".png", ".jpg", ".jpeg", ".gif", ".ico",
        ".woff", ".woff2", ".ttf", ".eot", ".otf",
        ".mp4", ".mp3", ".avi", ".webm", ".flv", ".wav",
        ".pdf", ".zip", ".tar", ".gz", ".rar", ".7z",
        ".exe", ".dll", ".bin", ".dmg", ".iso",
    )
    _noise_keywords = ("error", "failed", "no such file", "usage:", "flag")

    async def parse_stream(self, stream: AsyncIterator[ProcessEvent]) -> AsyncIterator[ProcessEvent]:
        async for event in stream:
            if event.type != "stdout" or not event.payload:
                continue
            value = event.payload.strip()
            if self._is_valid_url(value):
                yield ProcessEvent(type="result", payload=value)

    def _is_valid_url(self, value: str) -> bool:
        if not value or len(value) > 2048:
            return False
        lower_value = value.lower()
        if any(keyword in lower_value for keyword in self._noise_keywords):
            return False
        if not value.startswith(("http://", "https://")):
            return False
        return not any(pattern in lower_value for pattern in self._static_patterns)


class SubfinderStdoutParser:
    """Parse Subfinder JSON/text stdout into subdomain events."""

    async def parse_stream(self, stream: AsyncIterator[ProcessEvent]) -> AsyncIterator[ProcessEvent]:
        async for event in stream:
            if event.type != "stdout" or not event.payload:
                continue
            line = event.payload.strip()
            if not line:
                continue
            subdomain = self._extract_host(line)
            if subdomain:
                yield ProcessEvent(type="subdomain", payload=subdomain)

    @staticmethod
    def _extract_host(line: str) -> str | None:
        if line.startswith("{"):
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError:
                return None
            if isinstance(parsed, dict):
                value = parsed.get("host") or parsed.get("input") or parsed.get("domain")
                return str(value).strip() if value else None
            return None
        return line


class MantraStdoutParser:
    """Parse Mantra secret findings from stdout."""

    _ansi_escape = re.compile(r"\x1b\[[0-9;]*m")
    _finding = re.compile(r"^\[\+\]\s+(https?://[^\s]+)\s+\[(.+)\]$")

    async def parse_stream(self, stream: AsyncIterator[ProcessEvent]) -> AsyncIterator[ProcessEvent]:
        async for event in stream:
            if event.type != "stdout" or not event.payload:
                continue
            clean_line = self._ansi_escape.sub("", event.payload).strip()
            match = self._finding.match(clean_line)
            if match:
                yield ProcessEvent(
                    type="result",
                    payload={"url": match.group(1), "secret": match.group(2)},
                )


class Hakip2HostStdoutParser:
    """Parse hakip2host lines: [METHOD] IP hostname."""

    async def parse_stream(self, stream: AsyncIterator[ProcessEvent]) -> AsyncIterator[ProcessEvent]:
        async for event in stream:
            if event.type != "stdout" or not event.payload:
                continue
            parts = event.payload.strip().split(maxsplit=2)
            if len(parts) != 3 or not parts[0].startswith("["):
                continue
            yield ProcessEvent(
                type="result",
                payload={
                    "method": parts[0].strip("[]"),
                    "ip": parts[1],
                    "hostname": parts[2],
                },
            )


class FFUFStdoutParser:
    """Parse FFUF JSON stdout result lines."""

    async def parse_stream(self, stream: AsyncIterator[ProcessEvent]) -> AsyncIterator[ProcessEvent]:
        async for event in stream:
            if event.type != "stdout" or not event.payload:
                continue
            line = event.payload.strip()
            if not line.startswith("{"):
                continue
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict) and "url" in parsed:
                yield ProcessEvent(type="result", payload=parsed)


class SubjackStdoutParser:
    """Parse Subjack stdout into takeover result events."""

    async def parse_stream(self, stream: AsyncIterator[ProcessEvent]) -> AsyncIterator[ProcessEvent]:
        async for event in stream:
            if event.type != "stdout" or not event.payload:
                continue
            parsed = self._parse_line(event.payload.strip())
            if parsed is not None:
                yield ProcessEvent(type="result", payload=parsed)

    @staticmethod
    def _parse_line(line: str) -> dict[str, object] | None:
        if not line or "Not Vulnerable" in line:
            return None

        parts = line.split()
        if len(parts) < 2:
            return None

        service_start = line.find("[")
        service_end = line.find("]")
        service = line[service_start + 1:service_end] if service_start != -1 and service_end != -1 else "unknown"
        vulnerable = "Takeover Possible" in line or "possible takeover" in line.lower()
        if not vulnerable:
            return None

        subdomain = None
        cname = None
        for part in parts:
            if "." in part and not part.startswith("["):
                if subdomain is None:
                    subdomain = part
                elif cname is None:
                    cname = part
                    break

        if subdomain is None:
            return None

        return {
            "subdomain": subdomain,
            "service": service,
            "vulnerable": True,
            "cname": cname,
        }


class LinkFinderStdoutParser:
    """Parse LinkFinder stdout using target marker events for host context."""

    _static_extensions = (
        ".css", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".woff", ".ttf",
        ".eot", ".mp4", ".mp3", ".pdf", ".doc", ".htm", ".webp",
    )

    async def parse_stream(self, stream: AsyncIterator[ProcessEvent]) -> AsyncIterator[ProcessEvent]:
        current_target: str | None = None
        current_host: str | None = None
        urls_found: list[str] = []

        async for event in stream:
            if event.type == "target" and isinstance(event.payload, dict):
                if current_target and urls_found:
                    yield self._result(current_target, current_host, urls_found)
                current_target = event.payload.get("target")
                current_host = event.payload.get("host")
                urls_found = []
                continue

            if event.type != "stdout" or not event.payload or not current_host:
                continue
            normalized = self._normalize_url(event.payload.strip(), current_host)
            if normalized and self._is_valid_url(normalized):
                urls_found.append(normalized)

        if current_target and urls_found:
            yield self._result(current_target, current_host, urls_found)

    @staticmethod
    def _result(source_js: str, host: str | None, urls: list[str]) -> ProcessEvent:
        return ProcessEvent(
            type="result",
            payload={"source_js": source_js, "urls": urls, "host": host},
        )

    @staticmethod
    def _normalize_url(url: str, host: str) -> str | None:
        if url.startswith("//"):
            return f"https:{url}"
        if url.startswith("/"):
            return f"https://{host}{url}"
        if url.startswith(("http://", "https://")):
            return url
        return None

    def _is_valid_url(self, url: str) -> bool:
        if not url.startswith(("http://", "https://")):
            return False
        parsed = urlparse(url)
        if not parsed.netloc:
            return False
        lower = url.lower()
        return not any(ext in lower for ext in self._static_extensions)
