"""
Playwright-based interactive web crawler
Finds POST endpoints by interacting with all page elements
"""
import asyncio
import json
import logging
import sys
from typing import Set, Dict, Any
from urllib.parse import urlparse

class Colors:
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    CYAN = '\033[96m'
    RESET = '\033[0m'


class ColorFormatter(logging.Formatter):
    def format(self, record):
        timestamp = self.formatTime(record, '%H:%M:%S')
        level = record.levelname
        if level == 'INFO':
            level_color = Colors.GREEN
        elif level == 'WARNING':
            level_color = Colors.YELLOW
        elif level == 'ERROR':
            level_color = Colors.RED
        else:
            level_color = Colors.RESET
        return f"[{timestamp}] [{level_color}{level}{Colors.RESET}] {record.getMessage()}"


logger = logging.getLogger("playwright_scanner")
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(ColorFormatter())
logger.addHandler(handler)

try:
    from playwright.async_api import async_playwright, Page, Route, Response
except ImportError:
    print(json.dumps({"error": "playwright not installed. Run: pip install playwright && playwright install"}), file=sys.stderr)
    sys.exit(1)


STATIC_EXTENSIONS = {
    ".css", ".js", ".svg", ".png", ".jpg", ".jpeg", ".gif", ".ico", ".webp",
    ".woff", ".woff2", ".ttf", ".eot", ".otf",
    ".mp4", ".mp3", ".avi", ".webm", ".flv", ".wav", ".ogg",
    ".pdf", ".zip", ".tar", ".gz", ".rar", ".7z",
    ".exe", ".dll", ".bin", ".dmg", ".iso",
    ".map", ".min.js", ".min.css"
}


class PlaywrightScanner:
    def __init__(self, url: str, max_depth: int = 2, timeout: int = 300):
        self.start_url = url
        self.max_depth = max_depth
        self.timeout = timeout
        self.visited_urls: Set[str] = set()
        self.results: list[Dict[str, Any]] = []
        self.request_count = 0
        self.pending_requests: Dict[str, Dict[str, Any]] = {}

    def _is_static_resource(self, url: str) -> bool:
        """Check if URL is a static resource that should be skipped"""
        lower_url = url.lower().split('?')[0]
        return any(lower_url.endswith(ext) for ext in STATIC_EXTENSIONS)

    async def intercept_request(self, route: Route):
        """Intercept and log all HTTP requests in Katana format"""
        request = route.request

        if self._is_static_resource(request.url):
            await route.continue_()
            return

        parsed = urlparse(request.url)

        result = {
            "request": {
                "method": request.method,
                "endpoint": request.url,
                "headers": dict(request.headers),
            }
        }

        # Add body for POST/PUT/PATCH
        if request.method in ["POST", "PUT", "PATCH"] and request.post_data:
            result["request"]["body"] = request.post_data

        # Add raw request
        result["request"]["raw"] = f"{request.method} {parsed.path or '/'}"
        if parsed.query:
            result["request"]["raw"] += f"?{parsed.query}"
        result["request"]["raw"] += " HTTP/1.1\r\n"

        # Add headers to raw
        for key, value in request.headers.items():
            result["request"]["raw"] += f"{key}: {value}\r\n"
        result["request"]["raw"] += "\r\n"

        if request.post_data:
            result["request"]["raw"] += request.post_data

        # Store pending request to match with response
        self.pending_requests[request.url] = result

        await route.continue_()

    async def handle_response(self, response: Response):
        """Handle response and combine with request data"""
        url = response.url

        if url in self.pending_requests:
            result = self.pending_requests.pop(url)

            result["response"] = {
                "status_code": response.status,
                "headers": dict(response.headers),
            }

            result["timestamp"] = asyncio.get_event_loop().time()

            self.results.append(result)
            self.request_count += 1

            logger.info(f"Found: {result['request']['method']} {result['request']['endpoint']} -> {response.status}")
            print(json.dumps(result), flush=True)

    async def interact_with_page(self, page: Page):
        """Interact with all elements on the page automatically"""
        try:
            # Let Playwright auto-fill all forms
            await page.evaluate("""
                () => {
                    // Auto-fill all input fields
                    document.querySelectorAll('input, textarea, select').forEach(el => {
                        if (el.type === 'checkbox' || el.type === 'radio') {
                            el.checked = true;
                        } else if (el.tagName === 'SELECT') {
                            if (el.options.length > 0) {
                                el.selectedIndex = 0;
                            }
                        } else {
                            el.value = 'test';
                        }

                        // Trigger change events
                        el.dispatchEvent(new Event('change', { bubbles: true }));
                        el.dispatchEvent(new Event('input', { bubbles: true }));
                    });
                }
            """)

            await page.wait_for_timeout(500)

            # Click all clickable elements
            await page.evaluate("""
                () => {
                    document.querySelectorAll('button, a, [onclick], [role="button"]').forEach(el => {
                        try {
                            el.click();
                        } catch (e) {}
                    });
                }
            """)

            await page.wait_for_timeout(1000)

            # Submit all forms
            await page.evaluate("""
                () => {
                    document.querySelectorAll('form').forEach(form => {
                        try {
                            form.submit();
                        } catch (e) {
                            // Try clicking submit button
                            const submitBtn = form.querySelector('[type="submit"]');
                            if (submitBtn) submitBtn.click();
                        }
                    });
                }
            """)

            await page.wait_for_timeout(1000)

        except Exception:
            pass

    async def crawl_page(self, page: Page, url: str, depth: int = 0):
        """Crawl a single page and interact with elements"""
        if depth > self.max_depth or url in self.visited_urls:
            return

        self.visited_urls.add(url)
        logger.info(f"Crawling: {url} (depth={depth})")

        try:
            await page.goto(url, wait_until="networkidle", timeout=30000)
            await page.wait_for_timeout(2000)

            await self.interact_with_page(page)

            # Get all same-origin links for deeper crawling
            if depth < self.max_depth:
                links = await page.evaluate("""
                    (startUrl) => {
                        const startOrigin = new URL(startUrl).origin;
                        const links = [];

                        document.querySelectorAll('a[href]').forEach(a => {
                            try {
                                const href = a.href;
                                const url = new URL(href);
                                if (url.origin === startOrigin) {
                                    links.push(href);
                                }
                            } catch (e) {}
                        });

                        return [...new Set(links)];
                    }
                """, self.start_url)

                # Crawl child pages
                for child_url in links[:5]:
                    await self.crawl_page(page, child_url, depth + 1)

        except Exception:
            pass

    async def scan(self):
        """Main scanning loop"""
        logger.info(f"Starting scan: {self.start_url} (max_depth={self.max_depth})")

        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    '--no-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-gpu',
                ]
            )

            context = await browser.new_context(
                ignore_https_errors=True,
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            )

            page = await context.new_page()

            await page.route("**/*", self.intercept_request)
            page.on("response", self.handle_response)

            await self.crawl_page(page, self.start_url)
            await browser.close()

        logger.info(f"Scan completed: {self.request_count} requests found, {len(self.visited_urls)} pages visited")


async def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "No URL provided"}), file=sys.stderr)
        sys.exit(1)

    url = sys.argv[1]
    max_depth = int(sys.argv[2]) if len(sys.argv) > 2 else 2

    scanner = PlaywrightScanner(url, max_depth=max_depth)

    try:
        await scanner.scan()
    except Exception as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
