"""
Playwright-based interactive web crawler
Finds POST endpoints by interacting with all page elements
"""
import asyncio
import json
import sys
from playwright.async_api import async_playwright, Page, Route
from typing import Set, Dict, Any
from urllib.parse import urlparse


class PlaywrightScanner:
    def __init__(self, url: str, max_depth: int = 2, timeout: int = 300):
        self.start_url = url
        self.max_depth = max_depth
        self.timeout = timeout
        self.visited_urls: Set[str] = set()
        self.results: list[Dict[str, Any]] = []
        self.request_count = 0

    async def intercept_request(self, route: Route):
        """Intercept and log all HTTP requests in Katana format"""
        request = route.request

        # Build Katana-compatible format
        from urllib.parse import urlparse, parse_qs
        parsed = urlparse(request.url)

        result = {
            "request": {
                "method": request.method,
                "endpoint": request.url,
                "headers": dict(request.headers),
            }
        }

        if request.method in ["POST", "PUT", "PATCH"] and request.post_data:
            result["request"]["body"] = request.post_data
        result["request"]["raw"] = f"{request.method} {parsed.path or '/'}"
        if parsed.query:
            result["request"]["raw"] += f"?{parsed.query}"
        result["request"]["raw"] += " HTTP/1.1\r\n"
        for key, value in request.headers.items():
            result["request"]["raw"] += f"{key}: {value}\r\n"
        result["request"]["raw"] += "\r\n"

        if request.post_data:
            result["request"]["raw"] += request.post_data

        self.results.append(result)
        self.request_count += 1

        print(json.dumps(result), flush=True)

        await route.continue_()

    async def interact_with_page(self, page: Page):
        """Interact with all elements on the page automatically"""
        try:
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

        try:
            await page.goto(url, wait_until="networkidle", timeout=30000)
            await page.wait_for_timeout(2000)

            await self.interact_with_page(page)

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
            await self.crawl_page(page, self.start_url)
            await browser.close()


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
