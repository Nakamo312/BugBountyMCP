"""Line-oriented raw ProcessEvent parsers for CLI tools."""
from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator
from urllib.parse import urlparse

from api.application.pipeline.records import (
    FuzzFinding,
    HostFinding,
    JavaScriptReferenceFinding,
    ServiceFinding,
    UrlFinding,
)
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


def _default_service_scheme(port: int) -> str:
    return "https" if port == 443 else "http"


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


class WaymoreStdoutParser:
    """Parse Waymore URL stdout into UrlFinding records."""

    async def parse_stream(self, stream: AsyncIterator[ProcessEvent]) -> AsyncIterator[ProcessEvent]:
        async for event in stream:
            if event.type != "stdout" or not event.payload:
                continue
            value = _string_value(event.payload, ("url", "href", "endpoint", "input"))
            if value and value.startswith(("http://", "https://")):
                yield ProcessEvent(
                    type="canonical_record",
                    payload=UrlFinding(
                        url=value,
                        source_tool="waymore",
                        raw=event.payload,
                    ),
                )


class KatanaStdoutParser:
    """Parse Katana JSONL stdout into URL evidence records."""

    async def parse_stream(self, stream: AsyncIterator[ProcessEvent]) -> AsyncIterator[ProcessEvent]:
        async for event in stream:
            if event.type != "stdout" or not event.payload:
                continue
            parsed = _dict_value(event.payload)
            if parsed is None:
                continue
            url = self._endpoint_url(parsed)
            if not self._is_absolute_http_url(url):
                continue
            metadata = self._metadata(parsed, url)
            yield ProcessEvent(
                type="canonical_record",
                payload=UrlFinding(
                    url=url,
                    source_tool="katana",
                    source_target=self._host(url),
                    metadata=metadata,
                    raw=parsed,
                ),
            )

    @staticmethod
    def _endpoint_url(data: dict) -> str | None:
        request = data.get("request")
        if isinstance(request, dict):
            endpoint = request.get("endpoint") or request.get("url")
            if endpoint:
                return str(endpoint).strip() or None
        endpoint = data.get("endpoint") or data.get("url")
        return str(endpoint).strip() or None if endpoint else None

    @staticmethod
    def _is_absolute_http_url(url: str | None) -> bool:
        if not url:
            return False
        parsed = urlparse(url)
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)

    @staticmethod
    def _host(url: str) -> str | None:
        parsed = urlparse(url)
        return parsed.hostname or parsed.netloc or None

    @classmethod
    def _metadata(cls, data: dict, url: str) -> dict[str, object]:
        request = data.get("request") if isinstance(data.get("request"), dict) else {}
        response = data.get("response") if isinstance(data.get("response"), dict) else {}
        headers = response.get("headers") if isinstance(response.get("headers"), dict) else {}
        metadata: dict[str, object] = {
            "method": str(request.get("method") or data.get("method") or "GET").upper(),
        }
        status_code = response.get("status_code") or data.get("status_code")
        if status_code is not None:
            metadata["status_code"] = status_code
        title = response.get("title") or data.get("title")
        if title:
            metadata["title"] = str(title)
        content_type = cls._header_value(headers, "content-type")
        if content_type:
            metadata["content_type"] = content_type
        if cls._is_javascript_url(url, content_type):
            metadata["asset_type"] = "javascript"
        return metadata

    @staticmethod
    def _header_value(headers: dict, name: str) -> str | None:
        lowered = name.lower()
        for header_name, value in headers.items():
            if str(header_name).lower() == lowered:
                return str(value)
        return None

    @staticmethod
    def _is_javascript_url(url: str, content_type: str | None) -> bool:
        lowered = url.lower().split("?", 1)[0]
        if lowered.endswith((".js", ".mjs", ".cjs")):
            return True
        return bool(content_type and "javascript" in content_type.lower())


class SubfinderStdoutParser:
    """Parse Subfinder JSON/text stdout into HostFinding records."""

    async def parse_stream(self, stream: AsyncIterator[ProcessEvent]) -> AsyncIterator[ProcessEvent]:
        async for event in stream:
            if event.type != "stdout" or not event.payload:
                continue
            line = event.payload.strip()
            if not line:
                continue
            subdomain = self._extract_host(line)
            if subdomain:
                yield ProcessEvent(
                    type="canonical_record",
                    payload=HostFinding(
                        host=subdomain,
                        source_tool="subfinder",
                        raw=line,
                    ),
                )

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
                        type="canonical_record",
                        payload=HostFinding(
                            host=str(hostname),
                            source_tool="hakip2host",
                            ip=str(ip),
                            metadata={"method": str(parsed.get("method", "unknown"))},
                            raw=parsed,
                        ),
                    )
                continue

            parts = event.payload.strip().split(maxsplit=2)
            if len(parts) != 3 or not parts[0].startswith("["):
                continue
            yield ProcessEvent(
                type="canonical_record",
                payload=HostFinding(
                    host=parts[2],
                    source_tool="hakip2host",
                    ip=parts[1],
                    metadata={"method": parts[0].strip("[]")},
                    raw=event.payload,
                ),
            )


class NaabuStdoutParser:
    """Parse Naabu JSON stdout into ServiceFinding records."""

    async def parse_stream(self, stream: AsyncIterator[ProcessEvent]) -> AsyncIterator[ProcessEvent]:
        async for event in stream:
            if event.type != "stdout" or not event.payload:
                continue
            parsed = _dict_value(event.payload)
            if parsed is None:
                continue

            ip = parsed.get("ip") or parsed.get("host")
            port = parsed.get("port")
            if not ip or port is None:
                continue

            try:
                port_number = int(port)
            except (TypeError, ValueError):
                continue

            yield ProcessEvent(
                type="canonical_record",
                payload=ServiceFinding(
                    ip=str(ip),
                    port=port_number,
                    protocol=str(parsed.get("protocol") or "tcp"),
                    source_tool="naabu",
                    host=str(parsed.get("host")) if parsed.get("host") else None,
                    scheme=_default_service_scheme(port_number),
                    raw=parsed,
                ),
            )


class FFUFStdoutParser:
    """Parse FFUF JSON stdout into URL and fuzzing evidence records."""

    async def parse_stream(self, stream: AsyncIterator[ProcessEvent]) -> AsyncIterator[ProcessEvent]:
        async for event in stream:
            if event.type != "stdout" or not event.payload:
                continue
            parsed = _dict_value(event.payload)
            if parsed is None:
                continue
            url = self._url(parsed)
            if not self._is_absolute_http_url(url):
                continue
            metadata = self._metadata(parsed)
            yield ProcessEvent(
                type="canonical_record",
                payload=UrlFinding(
                    url=url,
                    source_tool="ffuf",
                    source_target=self._host(url),
                    metadata={"evidence_type": "fuzz_candidate"},
                    raw=parsed,
                ),
            )
            yield ProcessEvent(
                type="canonical_record",
                payload=FuzzFinding(
                    url=url,
                    source_tool="ffuf",
                    source_target=self._host(url),
                    status_code=self._int_value(parsed.get("status")),
                    length=self._int_value(parsed.get("length")),
                    words=self._int_value(parsed.get("words")),
                    lines=self._int_value(parsed.get("lines")),
                    redirect_location=self._string_value(parsed.get("redirectlocation")),
                    metadata=metadata,
                    raw=parsed,
                ),
            )

    @staticmethod
    def _url(data: dict) -> str | None:
        value = data.get("url")
        return str(value).strip() or None if value else None

    @staticmethod
    def _is_absolute_http_url(url: str | None) -> bool:
        if not url:
            return False
        parsed = urlparse(url)
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)

    @staticmethod
    def _host(url: str) -> str | None:
        parsed = urlparse(url)
        return parsed.hostname or parsed.netloc or None

    @staticmethod
    def _int_value(value: object) -> int | None:
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _string_value(value: object) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @classmethod
    def _metadata(cls, data: dict) -> dict[str, object]:
        metadata: dict[str, object] = {}
        for key in ("input", "position", "content-type", "resultfile"):
            value = data.get(key)
            if value is not None:
                metadata[key.replace("-", "_")] = value
        return metadata


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
    """Parse LinkFinder stdout into URL evidence and JS reference findings."""

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
                async for record in self._records(current_target, current_host, urls_found):
                    yield record
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

        async for record in self._records(current_target, current_host, urls_found):
            yield record

    async def _records(
        self,
        source_js: str | None,
        host: str | None,
        urls: list[str],
    ) -> AsyncIterator[ProcessEvent]:
        if not source_js or not urls:
            return
        for url in urls:
            yield ProcessEvent(
                type="canonical_record",
                payload=JavaScriptReferenceFinding(
                    source_url=source_js,
                    referenced_url=url,
                    source_tool="linkfinder",
                    source_target=host,
                ),
            )
            yield ProcessEvent(
                type="canonical_record",
                payload=UrlFinding(
                    url=url,
                    source_tool="linkfinder",
                    source_target=host,
                    discovered_from=source_js,
                ),
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
