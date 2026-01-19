"""
FIXED: True BFS crawler with proper state exploration
"""
import asyncio
import json
import logging
import sys
import hashlib
import re
import time
from typing import Set, Dict, Any, List, Optional, Tuple, Deque
from urllib.parse import urlparse, parse_qs, urljoin
from dataclasses import dataclass, field
from collections import deque


class Colors:
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    CYAN = '\033[96m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
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
        elif level == 'DEBUG':
            level_color = Colors.BLUE
        else:
            level_color = Colors.CYAN
        return f"[{timestamp}] [{level_color}{level}{Colors.RESET}] {record.getMessage()}"


logger = logging.getLogger("playwright_scanner")
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(ColorFormatter())
logger.addHandler(handler)

try:
    from playwright.async_api import async_playwright, Page, Route, Response, ElementHandle
except ImportError:
    print(json.dumps({"error": "playwright not installed. Run: pip install playwright && playwright install"}), file=sys.stderr)
    sys.exit(1)


STATIC_EXTENSIONS = {
    ".css", ".svg", ".png", ".jpg", ".jpeg", ".gif", ".ico", ".webp",
    ".woff", ".woff2", ".ttf", ".eot", ".otf",
    ".mp4", ".mp3", ".avi", ".webm", ".flv", ".wav", ".ogg",
    ".pdf", ".zip", ".tar", ".gz", ".rar", ".7z",
    ".exe", ".dll", ".bin", ".dmg", ".iso",
    ".map", ".min.js", ".min.css"
}


@dataclass
class Action:
    selector: str
    text: str
    tag: str
    event_type: str = "click"
    semantic: str = "unknown"
    importance: int = 1
    href: str = ""

    def __hash__(self):
        return hash((self.selector, self.text, self.tag, self.event_type, self.href))


@dataclass
class State:
    url: str
    dom_hash: str
    cookies_hash: str
    storage_hash: str
    depth: int
    actions: List[Action] = field(default_factory=list)
    path: List[Action] = field(default_factory=list)
    
    def __hash__(self):
        parsed = urlparse(self.url)
        query_items = tuple(sorted(parse_qs(parsed.query).items())) if parsed.query else ()
        return hash((parsed.netloc, parsed.path, query_items, self.dom_hash[:8], self.cookies_hash[:8]))
    
    def __eq__(self, other):
        return hash(self) == hash(other)


class PlaywrightScanner:
    def __init__(self, url: str, max_depth: int = 3, timeout: int = 300):
        self.start_url = url
        self.max_depth = max_depth
        self.timeout = timeout
        
        self.visited_states: Set[State] = set()
        self.state_queue: Deque[State] = deque()
        self.captured_requests: List[Dict[str, Any]] = []
        
        self.unique_endpoints: Set[str] = set()
        self.unique_methods_paths: Set[str] = set()
        
        self.request_count = 0
        self.start_time = time.time()
        self.domain = urlparse(url).netloc
        
        self.states_explored = 0
        self.actions_executed = 0
        self.last_new_request_time = time.time()

    def _is_static_resource(self, url: str) -> bool:
        lower_url = url.lower()
        return any(lower_url.endswith(ext) for ext in STATIC_EXTENSIONS)

    async def _get_dom_hash(self, page: Page) -> str:
        try:
            fingerprint = await page.evaluate("""
                () => {
                    const elements = {
                        forms: document.querySelectorAll('form').length,
                        buttons: document.querySelectorAll('button, [role="button"]').length,
                        links: document.querySelectorAll('a[href]').length,
                        inputs: document.querySelectorAll('input, textarea, select').length,
                        clickables: document.querySelectorAll('[onclick]').length,
                    };
                    const url = window.location.pathname + window.location.search;
                    return `${url}|${elements.forms}|${elements.buttons}|${elements.clickables}`;
                }
            """)
            return hashlib.sha256(fingerprint.encode()).hexdigest()[:16]
        except:
            return "error"

    async def _get_state_fingerprint(self, page: Page):
        cookies = await page.context.cookies()
        cookies_hash = hashlib.sha256(json.dumps(cookies, sort_keys=True, default=str).encode()).hexdigest()[:16]
        
        storage = await page.evaluate("""
            () => JSON.stringify({
                localStorage: Object.keys(localStorage).length,
                sessionStorage: Object.keys(sessionStorage).length
            })
        """)
        storage_hash = hashlib.sha256(storage.encode()).hexdigest()[:16]
        
        dom_hash = await self._get_dom_hash(page)
        return dom_hash, cookies_hash, storage_hash

    def _classify_action_semantic(self, text: str, selector: str, tag: str) -> Tuple[str, int]:
        text_lower = text.lower()
        importance = 1
        
        if any(k in text_lower for k in ['login', 'sign in', 'signin']):
            return 'auth_login', 10
        if any(k in text_lower for k in ['signup', 'register']):
            return 'auth_register', 10
        if any(k in text_lower for k in ['submit', 'save', 'create']):
            return 'submit', 9
        if any(k in text_lower for k in ['search', 'filter']):
            return 'search', 8
        if tag == 'form':
            return 'form', 9
        if tag == 'a':
            return 'link', 6
        if tag == 'button':
            return 'button', 7
            
        return 'interaction', 5

    async def _extract_actions(self, page: Page) -> List[Action]:
        actions = []
        seen = set()
        
        selectors = [
            "a[href]:not([href^='javascript:']):not([href^='#'])",
            "button:not([disabled])",
            "input[type='submit']:not([disabled])",
            "input[type='button']:not([disabled])",
            "form",
            "[onclick]",
            "[role='button']",
            "summary",
            "label[for]",
        ]
        
        for selector in selectors:
            try:
                elements = await page.query_selector_all(selector)
                for el in elements[:50]:
                    try:
                        if not await el.is_visible():
                            continue
                            
                        tag = await el.evaluate("e => e.tagName.toLowerCase()")
                        text = (await el.text_content() or "").strip()[:100]
                        
                        selector_str = await self._generate_selector(el)
                        if not selector_str or selector_str in seen:
                            continue
                            
                        href = ""
                        if tag == 'a':
                            href = await el.get_attribute('href') or ""
                        
                        semantic, importance = self._classify_action_semantic(text, selector_str, tag)
                        
                        event_type = "click"
                        if tag in ["input", "textarea", "select"]:
                            event_type = "change"
                        elif tag == "form":
                            event_type = "submit"
                        
                        action = Action(
                            selector=selector_str,
                            text=text,
                            tag=tag,
                            event_type=event_type,
                            semantic=semantic,
                            importance=importance,
                            href=href
                        )
                        
                        actions.append(action)
                        seen.add(selector_str)
                        
                    except:
                        continue
            except:
                continue
        
        actions.sort(key=lambda x: x.importance, reverse=True)
        logger.info(f"Found {len(actions)} actions")
        return actions

    async def _generate_selector(self, element: ElementHandle) -> Optional[str]:
        try:
            element_id = await element.get_attribute('id')
            if element_id:
                return f"#{element_id}"
            
            name = await element.get_attribute('name')
            tag = await element.evaluate("el => el.tagName.toLowerCase()")
            
            if name and tag in ['input', 'textarea', 'select', 'button']:
                return f"{tag}[name='{name}']"
            
            classes = await element.get_attribute('class')
            if classes:
                first_class = classes.split()[0]
                if first_class:
                    return f"{tag}.{first_class}"
            
            return f"{tag}:has-text('{await element.text_content() or ''[:30]}')"
            
        except:
            return None

    async def _fill_form(self, page: Page, form: ElementHandle):
        try:
            inputs = await form.query_selector_all('input, textarea, select')
            
            for inp in inputs:
                try:
                    inp_type = await inp.get_attribute('type') or 'text'
                    inp_name = await inp.get_attribute('name')
                    
                    if not inp_name or inp_type == 'hidden':
                        continue
                    
                    if inp_type in ['text', 'search', 'url']:
                        await inp.fill('test')
                    elif inp_type == 'email':
                        await inp.fill('test@example.com')
                    elif inp_type == 'password':
                        await inp.fill('password123')
                    elif inp_type == 'number':
                        await inp.fill('1')
                    elif inp_type == 'checkbox':
                        await inp.click()
                    elif inp_type == 'radio':
                        await inp.click()
                    
                    await inp.dispatch_event('input')
                    await inp.dispatch_event('change')
                    
                except:
                    continue
                    
            await page.wait_for_timeout(100)
            
        except:
            pass

    async def _execute_action(self, page: Page, action: Action) -> bool:
        try:
            logger.info(f"Executing: {action.semantic} - {action.text[:30]}")
            
            if action.tag == 'a' and action.href:
                target_url = action.href
                if not target_url.startswith('http'):
                    target_url = urljoin(page.url, target_url)
                
                await page.goto(target_url, wait_until="networkidle", timeout=10000)
                
            elif action.tag == 'form':
                element = await page.query_selector(action.selector)
                if element:
                    await self._fill_form(page, element)
                    await element.evaluate("form => form.submit()")
                    
            else:
                element = await page.query_selector(action.selector)
                if element:
                    await element.click()
            
            await page.wait_for_timeout(300)
            return True
            
        except Exception as e:
            logger.debug(f"Action failed: {e}")
            return False

    async def intercept_request(self, route: Route):
        request = route.request
        
        if self._is_static_resource(request.url):
            await route.continue_()
            return
        
        parsed = urlparse(request.url)
        
        if parsed.netloc != self.domain:
            await route.continue_()
            return
        
        req_data = {
            'timestamp': time.time(),
            'method': request.method,
            'url': request.url,
            'path': parsed.path,
            'headers': dict(request.headers),
            'post_data': request.post_data,
            'resource_type': request.resource_type,
        }
        
        self.captured_requests.append(req_data)
        self.unique_endpoints.add(request.url)
        self.unique_methods_paths.add(f"{request.method} {parsed.path}")
        self.request_count += 1
        self.last_new_request_time = time.time()
        
        print(json.dumps(req_data, ensure_ascii=False), flush=True)
        logger.info(f"Request: {request.method} {parsed.path}")
        
        await route.continue_()

    async def handle_response(self, response: Response):
        request = response.request
        parsed = urlparse(request.url)
        
        if parsed.netloc != self.domain:
            return
        
        resp_data = {
            'timestamp': time.time(),
            'request_url': request.url,
            'status': response.status,
            'headers': dict(response.headers),
        }
        
        print(json.dumps(resp_data, ensure_ascii=False), flush=True)

    async def _explore_state(self, page: Page, state: State) -> List[State]:
        new_states = []
        
        logger.info(f"Exploring state: {state.url} (depth={state.depth}, actions={len(state.actions)})")
        
        for action in state.actions[:20]:
            if time.time() - self.start_time > self.timeout:
                break
            
            self.actions_executed += 1
            
            current_url = page.url
            current_hash = await self._get_dom_hash(page)
            
            success = await self._execute_action(page, action)
            
            if not success:
                continue
            
            await asyncio.sleep(0.5)
            
            new_url = page.url
            new_dom_hash = await self._get_dom_hash(page)
            new_cookies_hash, new_storage_hash = "", ""
            
            try:
                new_dom_hash, new_cookies_hash, new_storage_hash = await self._get_state_fingerprint(page)
            except:
                pass
            
            if state.depth < self.max_depth and urlparse(new_url).netloc == self.domain:
                new_actions = await self._extract_actions(page)
                new_state = State(
                    url=new_url,
                    dom_hash=new_dom_hash,
                    cookies_hash=new_cookies_hash,
                    storage_hash=new_storage_hash,
                    depth=state.depth + 1,
                    actions=new_actions,
                    path=state.path + [action]
                )
                
                if new_state not in self.visited_states:
                    new_states.append(new_state)
            
            if page.url != current_url:
                await page.goto(current_url, wait_until="networkidle", timeout=10000)
                await asyncio.sleep(0.5)
        
        return new_states

    async def scan(self):
        logger.info(f"Starting BFS crawl: {self.start_url}")
        logger.info(f"Max depth: {self.max_depth}, Timeout: {self.timeout}s")
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=['--no-sandbox', '--disable-dev-shm-usage']
            )
            
            context = await browser.new_context(
                ignore_https_errors=True,
                viewport={'width': 1920, 'height': 1080}
            )
            
            page = await context.new_page()
            
            await page.route("**/*", lambda route: self.intercept_request(route))
            page.on("response", lambda response: self.handle_response(response))
            
            await page.goto(self.start_url, wait_until="networkidle", timeout=30000)
            await asyncio.sleep(2)
            
            initial_dom_hash, initial_cookies_hash, initial_storage_hash = await self._get_state_fingerprint(page)
            initial_actions = await self._extract_actions(page)
            
            initial_state = State(
                url=self.start_url,
                dom_hash=initial_dom_hash,
                cookies_hash=initial_cookies_hash,
                storage_hash=initial_storage_hash,
                depth=0,
                actions=initial_actions
            )
            
            self.visited_states.add(initial_state)
            self.state_queue.append(initial_state)
            
            logger.info(f"Initial state queued with {len(initial_actions)} actions")
            
            while self.state_queue and (time.time() - self.start_time) < self.timeout:
                current_state = self.state_queue.popleft()
                self.states_explored += 1
                
                if page.url != current_state.url:
                    await page.goto(current_state.url, wait_until="networkidle", timeout=10000)
                    await asyncio.sleep(1)
                
                new_states = await self._explore_state(page, current_state)
                
                for new_state in new_states:
                    if new_state not in self.visited_states:
                        self.visited_states.add(new_state)
                        self.state_queue.append(new_state)
                        logger.info(f"New state discovered: {new_state.url} (queue: {len(self.state_queue)})")
                
                elapsed = time.time() - self.start_time
                logger.info(f"Progress: {self.states_explored} states, {self.actions_executed} actions, {self.request_count} requests")
                
                if time.time() - self.last_new_request_time > 30 and len(self.state_queue) == 0:
                    logger.info("No new requests for 30 seconds, stopping")
                    break
            
            await browser.close()
        
        self._print_results()

    def _print_results(self):
        elapsed = time.time() - self.start_time
        
        print("\n" + "="*80, file=sys.stderr)
        print("CRAWL COMPLETE", file=sys.stderr)
        print("="*80, file=sys.stderr)
        print(f"Time: {elapsed:.2f}s", file=sys.stderr)
        print(f"States explored: {self.states_explored}", file=sys.stderr)
        print(f"Actions executed: {self.actions_executed}", file=sys.stderr)
        print(f"Requests captured: {self.request_count}", file=sys.stderr)
        print(f"Unique endpoints: {len(self.unique_endpoints)}", file=sys.stderr)
        print(f"Unique methods/paths: {len(self.unique_methods_paths)}", file=sys.stderr)
        print("="*80, file=sys.stderr)
        
        if self.unique_methods_paths:
            print("\nUNIQUE ENDPOINTS:", file=sys.stderr)
            for endpoint in sorted(self.unique_methods_paths):
                print(f"  {endpoint}", file=sys.stderr)


async def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "No URL provided"}))
        sys.exit(1)

    url = sys.argv[1]
    max_depth = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    
    scanner = PlaywrightScanner(url, max_depth=max_depth, timeout=300)
    
    try:
        await scanner.scan()
    except KeyboardInterrupt:
        print("\nCrawl interrupted", file=sys.stderr)
        scanner._print_results()
    except Exception as e:
        print(f"\nError: {e}", file=sys.stderr)
        scanner._print_results()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())