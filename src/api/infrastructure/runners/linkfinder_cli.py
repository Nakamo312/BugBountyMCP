import logging
from typing import AsyncIterator, List
from urllib.parse import urlparse
from api.infrastructure.commands.command_executor import CommandExecutor
from api.infrastructure.schemas.models.process_event import ProcessEvent

logger = logging.getLogger(__name__)

class LinkFinderCliRunner:
    def __init__(self, linkfinder_path: str = "linkfinder", timeout: int = 15):
        self.linkfinder_path = linkfinder_path
        self.timeout = timeout

    async def run(self, js_urls: List[str]) -> AsyncIterator[ProcessEvent]:
        for target in js_urls:
            logger.info("Running LinkFinder on: %s", target)

            parsed = urlparse(target)
            host = parsed.hostname or parsed.netloc

            if not host:
                logger.warning("Could not extract host from %s, skipping", target)
                continue

            is_domain_scan = not parsed.path or parsed.path == "/" or "*" in target

            command = [
                self.linkfinder_path,
                "-i", target,
            ]

            if is_domain_scan:
                command.append("-d")

            command.extend(["-o", "cli"])

            executor = CommandExecutor(command, timeout=self.timeout)

            try:
                urls_found = []
                async for event in executor.run():
                    if event.type != "stdout":
                        continue

                    if not event.payload:
                        continue

                    line = event.payload.strip()
                    if not line:
                        continue

                    normalized_url = self._normalize_url(line, host)
                    if normalized_url and self._is_valid_url(normalized_url):
                        urls_found.append(normalized_url)

                if urls_found:
                    yield ProcessEvent(
                        type="result",
                        payload={
                            "source_js": target,
                            "urls": urls_found,
                            "host": host
                        }
                    )

            except Exception as e:
                logger.warning("LinkFinder timeout/error for %s: %s", target, str(e))
                continue

    def _normalize_url(self, url: str, host: str) -> str:
        if url.startswith("//"):
            return f"https:{url}"

        if url.startswith("/"):
            return f"https://{host}{url}"

        if url.startswith("http://") or url.startswith("https://"):
            return url

        return None

    def _is_valid_url(self, url: str) -> bool:
        if not url or not url.startswith("http"):
            return False

        static_extensions = [
            '.css', '.png', '.jpg', '.jpeg', '.gif', '.svg',
            '.woff', '.ttf', '.eot', '.mp4', '.mp3', '.pdf',
            '.doc', '.htm', '.webp'
        ]

        url_lower = url.lower()
        for ext in static_extensions:
            if ext in url_lower:
                return False

        return True
