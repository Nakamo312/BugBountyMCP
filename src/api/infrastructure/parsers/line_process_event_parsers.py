"""Line-oriented raw ProcessEvent parsers for CLI tools."""
from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator
from urllib.parse import urlparse

from api.infrastructure.schemas.models.process_event import ProcessEvent


def _json_or_text(line: str) -> object:
    value = line.strip()
    if not value:
        return ""
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def _string_value(line: str, keys: tuple[str, ...] = ()) -> str | None:
    parsed = _json_or_text(line)
    if isinstance(parsed, str):
        value = parsed.strip()
        return value or None
    if isinstance(parsed, dict):
        for key in keys:
            value = parsed.get(key)
            if value:
                return str(value).strip()
    return None


def _dict_value(line: str) -> dict | None:
    parsed = _json_or_text(line)
    return parsed if isinstance(parsed, dict) else None


class StdoutLineResultParser:
    """Emit non-empty stdout lines as result payloads."""

    async def parse_stream(self, stream: AsyncIterator[ProcessEvent]) -> AsyncIterator[ProcessEvent]:
        async for event in stream:
            if event.type == "stdout" and event.payload:
                value = _string_value(
                    event.payload,
                    ("value", "line", "host", "hostname", "ip", "cidr", "url", "input"),
                )
                if value:
                    yield ProcessEvent(type="result", payload=value)


class URLStdoutLineResultParser:
    """Emit stdout lines that look like HTTP URLs."""

    async def parse_stream(self, stream: AsyncIterator[ProcessEvent]) -> AsyncIterator[ProcessEvent]:
        async for event in stream:
            if event.type == "stdout" and event.payload:
                value = _string_value(event.payload, ("url", "href", "endpoint", "input"))
                if value and value.startswith(("http://", "https://")):
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
            value = _string_value(event.payload, ("url", "href", "endpoint", "input"))
            if self._is_valid_url(value):
                yield ProcessEvent(type="result", payload=value)

    def _is_valid_url(self, value: str | None) -> bool:
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
        return _string_value(line, ("host", "hostname", "input", "domain", "value"))


class MantraStdoutParser:
    """Parse Mantra secret findings from stdout."""

    _ansi_escape = re.compile(r"\x1b\[[0-9;]*m")
    _finding = re.compile(r"^\[\+\]\s+(https?://[^\s]+)\s+\[(.+)\]$")

    async def parse_stream(self, stream: AsyncIterator[ProcessEvent]) -> AsyncIterator[ProcessEvent]:
        async for event in stream:
            if event.type != "stdout" or not event.payload:
                continue
            parsed = _dict_value(event.payload)
            if parsed is not None:
                url = parsed.get("url")
                secret = parsed.get("secret") or parsed.get("finding") or parsed.get("match")
                if url and secret:
                    yield ProcessEvent(
                        type="result",
                        payload={"url": str(url), "secret": str(secret)},
                    )
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
            parsed = _dict_value(event.payload)
            if parsed is not None:
                ip = parsed.get("ip")
                hostname = parsed.get("hostname") or parsed.get("host")
                if ip and hostname:
                    yield ProcessEvent(
                        type="result",
                        payload={
                            "method": str(parsed.get("method", "unknown")),
                            "ip": str(ip),
                            "hostname": str(hostname),
                        },
                    )
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
            parsed = _dict_value(event.payload)
            if isinstance(parsed, dict) and "url" in parsed:
                yield ProcessEvent(type="result", payload=parsed)


class SubjackStdoutParser:
    """Parse Subjack stdout into takeover result events."""

    async def parse_stream(self, stream: AsyncIterator[ProcessEvent]) -> AsyncIterator[ProcessEvent]:
        async for event in stream:
            if event.type != "stdout" or not event.payload:
                continue
            parsed = self._parse_stdout(event.payload)
            if parsed is not None:
                yield ProcessEvent(type="result", payload=parsed)

    def _parse_stdout(self, line: str) -> dict[str, object] | None:
        parsed = _dict_value(line)
        if parsed is not None:
            return self._parse_dict(parsed)
        return self._parse_line(line.strip())

    @staticmethod
    def _parse_dict(data: dict) -> dict[str, object] | None:
        subdomain = data.get("subdomain") or data.get("host") or data.get("hostname")
        if not subdomain:
            return None
        vulnerable = bool(data.get("vulnerable") or data.get("takeover") or data.get("takeover_possible"))
        if not vulnerable:
            return None
        return {
            "subdomain": str(subdomain),
            "service": str(data.get("service") or data.get("provider") or "unknown"),
            "vulnerable": True,
            "cname": data.get("cname"),
        }

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
            value = _string_value(event.payload, ("url", "href", "endpoint", "path"))
            if not value:
                continue
            normalized = self._normalize_url(value, current_host)
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
