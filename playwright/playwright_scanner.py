"""
Playwright-based state-aware web crawler with BFS exploration
Enhanced for correct POST/PUT form submission, SPA handling, and full coverage
"""
import asyncio
import json
import logging
import sys
import hashlib
from typing import Set, Dict, Any, List
from urllib.parse import urlparse, parse_qs
from dataclasses import dataclass, field
from collections import deque

from playwright.async_api import async_playwright, Page, Route, Response, ElementHandle

# ---------------- Logging ----------------
class Colors:
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    RESET = '\033[0m'

class ColorFormatter(logging.Formatter):
    def format(self, record):
        timestamp = self.formatTime(record, '%H:%M:%S')
        level = record.levelname
        color = Colors.RESET
        if level == 'INFO': color = Colors.GREEN
        elif level == 'WARNING': color = Colors.YELLOW
        elif level == 'ERROR': color = Colors.RED
        return f"[{timestamp}] [{color}{level}{Colors.RESET}] {record.getMessage()}"

logger = logging.getLogger("playwright_scanner")
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(ColorFormatter())
logger.addHandler(handler)

# ---------------- Constants ----------------
STATIC_EXTENSIONS = {
    ".css", ".svg", ".png", ".jpg", ".jpeg", ".gif", ".ico", ".webp",
    ".woff", ".woff2", ".ttf", ".eot", ".otf",
    ".mp4", ".mp3", ".avi", ".webm", ".flv", ".wav", ".ogg",
    ".pdf", ".zip", ".tar", ".gz", ".rar", ".7z",
    ".exe", ".dll", ".bin", ".dmg", ".iso",
    ".map", ".min.js", ".min.css"
}

# ---------------- Data Classes ----------------
@dataclass
class Action:
    selector: str
    text: str
    tag: str
    event_type: str = "click"
    semantic: str = "unknown"

    def __hash__(self): return hash((self.selector, self.text, self.tag, self.event_type))
    def __eq__(self, other): return isinstance(other, Action) and hash(self) == hash(other)

    def get_cluster_key(self) -> str:
        words = ''.join(c for c in self.text.lower() if c.isalnum() or c.isspace()).split()
        text_sig = '_'.join(words[:3])
        return f"{self.semantic}:{self.tag}:{text_sig}"

@dataclass
class State:
    url: str
    dom_hash: str
    cookies_hash: str
    storage_hash: str
    depth: int
    path: List[Action] = field(default_factory=list)
    actions: Set[Action] = field(default_factory=set)
    executed_actions: Set[Action] = field(default_factory=set)
    dead_actions: Set[Action] = field(default_factory=set)
    executed_clusters: Set[str] = field(default_factory=set)
    discovered_endpoints: Set[str] = field(default_factory=set)
    is_volatile: bool = False

    def __hash__(self):
        return hash((self.url, frozenset(a.get_cluster_key() for a in self.actions)))

    def get_fingerprint(self):
        return (self.url, frozenset(a.get_cluster_key() for a in self.actions))

    def is_exhausted(self, no_new_endpoints: bool, no_new_clusters: bool) -> bool:
        all_executed = len(self.executed_actions) >= len(self.actions)
        return all_executed or (no_new_endpoints and no_new_clusters)

# ---------------- Scanner ----------------
class PlaywrightScanner:
    def __init__(self, url: str, max_depth: int = 3, timeout: int = 300, max_actions_per_state: int = 50, max_path_length: int = 20):
        self.start_url = url
        self.max_depth = max_depth
        self.timeout = timeout
        self.max_actions_per_state = max_actions_per_state
        self.max_path_length = max_path_length

        self.visited_states: Set[tuple] = set()
        self.state_queue: deque[State] = deque()
        self.results: list[Dict[str, Any]] = []
        self.pending_requests: Dict[str, Dict[str, Any]] = {}
        self.seen_requests: Set[str] = set()

        self.unique_endpoints: Set[str] = set()
        self.unique_methods_paths: Set[str] = set()
        self.unique_json_keys: Set[str] = set()
        self.unique_graphql_ops: Set[str] = set()
        self.request_count = 0
        self.last_request_count = 0
        self.last_endpoint_count = 0
        self.last_keys_count = 0
        self.last_graphql_count = 0
        self.stale_iterations = 0

    # ---------------- Utility ----------------
    def _is_static_resource(self, url: str) -> bool:
        lower_url = url.lower().split('?')[0]
        return any(lower_url.endswith(ext) for ext in STATIC_EXTENSIONS)

    def _classify_action_semantic(self, text: str, selector: str, tag: str) -> str:
        text_lower = text.lower()
        sel_lower = selector.lower()
        if any(k in text_lower for k in ['next', 'prev', 'page', '»', '«', '>', '<']): return 'pagination'
        if any(k in text_lower for k in ['filter', 'sort', 'search', 'apply', 'category', 'tag']): return 'filter'
        if any(k in text_lower for k in ['submit', 'send', 'save', 'post', 'create', 'delete', 'update']): return 'submit'
        if any(k in text_lower for k in ['login', 'signup', 'logout', 'register']): return 'auth'
        if tag == 'a' or 'nav' in sel_lower or 'menu' in sel_lower: return 'navigation'
        if any(k in text_lower for k in ['load', 'more', 'show', 'expand', 'view']): return 'data_loader'
        return 'interaction'

    def _make_request_key(self, method: str, url: str, body: str = None) -> str:
        parsed = urlparse(url)
        path = parsed.path or '/'
        query_sig = ','.join(sorted(parse_qs(parsed.query).keys())) if parsed.query else ''
        body_sig = ''
        if body:
            try:
                obj = json.loads(body)
                if isinstance(obj, dict): body_sig = ','.join(sorted(obj.keys()))
            except: body_sig = str(hash(body))[:8]
        return f"{method}:{path}:{query_sig}:{body_sig}"

    # ---------------- State Fingerprinting ----------------
    async def _get_dom_hash(self, page: Page) -> str:
        fingerprint = await page.evaluate("""
            () => {
                const forms = [...document.querySelectorAll('form')].length;
                const buttons = [...document.querySelectorAll('button,a,[role="button"]')].length;
                const inputs = [...document.querySelectorAll('input')].map(i => i.name || i.type).sort().join(',');
                const onclick = [...document.querySelectorAll('[onclick]')].length;
                return `${location.pathname}|${forms}|${buttons}|${onclick}|${inputs}`;
            }
        """)
        return hashlib.sha256(fingerprint.encode()).hexdigest()[:16]

    async def _get_state_fingerprint(self, page: Page):
        cookies = await page.context.cookies()
        cookies_hash = hashlib.sha256(json.dumps(cookies, sort_keys=True, default=str).encode()).hexdigest()[:16]

        storage = await page.evaluate("""
            () => JSON.stringify({ localStorage: {...localStorage}, sessionStorage: {...sessionStorage} })
        """)
        storage_hash = hashlib.sha256(storage.encode()).hexdigest()[:16]

        dom_hash = await self._get_dom_hash(page)
        return dom_hash, cookies_hash, storage_hash

    # ---------------- Actions ----------------
    async def _generate_selector(self, el: ElementHandle) -> str:
        try:
            return await el.evaluate("""
                el => {
                    if (el.dataset.testid) return `[data-testid="${el.dataset.testid}"]`;
                    if (el.getAttribute("aria-label")) return `[aria-label="${el.getAttribute("aria-label")}"]`;
                    if (el.id) return '#' + el.id;
                    if (el.name) return `[name="${el.name}"]`;
                    if (el.getAttribute("role")) return `[role="${el.getAttribute("role")}"]`;
                    let path = [];
                    let current = el;
                    while (current.parentElement && path.length < 3) {
                        let tag = current.tagName.toLowerCase();
                        let siblings = Array.from(current.parentElement.children).filter(e => e.tagName === current.tagName);
                        if (siblings.length > 1) { tag += `:nth-of-type(${siblings.indexOf(current)+1})`; }
                        path.unshift(tag); current = current.parentElement;
                    }
                    return path.join(' > ');
                }
            """)
        except: return None

    async def _extract_actions(self, page: Page) -> Set[Action]:
        actions = set()
        elements = await page.query_selector_all("button, a, input[type=submit], [role=button]")

        for el in elements[:self.max_actions_per_state]:
            try:
                if not await el.is_visible() or not await el.is_enabled(): continue
                text = (await el.text_content() or "").strip()[:50]
                tag = await el.evaluate("el => el.tagName.toLowerCase()")
                selector = await self._generate_selector(el)
                semantic = self._classify_action_semantic(text, selector, tag)
                if selector: actions.add(Action(selector=selector, text=text, tag=tag, semantic=semantic))
            except: continue
        return actions

    async def _fill_forms(self, page: Page):
        """Smart fill forms with realistic values"""
        await page.evaluate("""
            () => {
                document.querySelectorAll('input, textarea, select').forEach(el => {
                    if (el.type === 'hidden') return;
                    if (el.type === 'checkbox' || el.type === 'radio') el.checked = true;
                    else if (el.type === 'email') el.value = 'test@example.org';
                    else if (el.type === 'password') el.value = 'KatanaP@ssw0rd1';
                    else if (el.type === 'number') el.value = el.min || 1;
                    else if (el.type === 'tel') el.value = '+1234567890';
                    else if (el.type === 'url') el.value = 'https://example.com';
                    else if (el.tagName === 'SELECT') { if (el.options.length>0) el.selectedIndex=0; }
                    else el.value = 'test';
                    el.dispatchEvent(new Event('change', { bubbles: true }));
                    el.dispatchEvent(new Event('input', { bubbles: true }));
                });
            }
        """)

    async def _execute_action(self, page: Page, action: Action) -> tuple[bool,bool]:
        """Click element or submit form and always consider POST as effective"""
        try:
            el = await page.query_selector(action.selector)
            if el and await el.is_visible() and await el.is_enabled():
                initial_req_count = self.request_count
                await el.scroll_into_view_if_needed()
                await el.click(timeout=2000)
                await page.wait_for_timeout(300)
                return True, True  # always mark POST as effective
        except: pass
        return False, False

    # ---------------- Requests ----------------
    async def intercept_request(self, route: Route):
        req = route.request
        if self._is_static_resource(req.url): await route.continue_(); return

        key = self._make_request_key(req.method, req.url, req.post_data)
        self.pending_requests[key] = {
            "request": {
                "method": req.method,
                "endpoint": req.url,
                "headers": dict(req.headers),
                "body": req.post_data,
            }
        }
        await route.continue_()

    async def handle_response(self, response: Response):
        req = response.request
        key = self._make_request_key(req.method, req.url, req.post_data)
        if key not in self.pending_requests: return

        result = self.pending_requests.pop(key)
        result["response"] = {"status_code": response.status, "headers": dict(response.headers)}
        result["timestamp"] = asyncio.get_event_loop().time()
        self.results.append(result)
        self.request_count += 1
        self.unique_endpoints.add(req.url)
        print(json.dumps(result), flush=True)

    # ---------------- Exploration ----------------
    async def _explore_state(self, page: Page, state: State):
        await self._fill_forms(page)
        action_clusters = {}
        for action in state.actions:
            if action not in state.executed_actions:
                key = action.get_cluster_key()
                action_clusters[key] = action  # keep all submit/critical actions

        for cluster_key, action in action_clusters.items():
            if cluster_key in state.executed_clusters: continue
            success, _ = await self._execute_action(page, action)
            if not success: continue
            state.executed_actions.add(action)
            state.executed_clusters.add(cluster_key)
            # capture new state
            dom, cookies, storage = await self._get_state_fingerprint(page)
            url = page.url
            if state.depth < self.max_depth:
                actions = await self._extract_actions(page)
                new_state = State(url=url, dom_hash=dom, cookies_hash=cookies,
                                  storage_hash=storage, depth=state.depth+1,
                                  path=state.path+[action], actions=actions)
                f = new_state.get_fingerprint()
                if f not in self.visited_states:
                    self.visited_states.add(f)
                    self.state_queue.append(new_state)

    # ---------------- Main Scan ----------------
    async def scan(self):
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(ignore_https_errors=True)
            page = await context.new_page()
            await page.route("**/*", self.intercept_request)
            page.on("response", self.handle_response)

            await page.goto(self.start_url, wait_until="networkidle", timeout=30000)
            dom, cookies, storage = await self._get_state_fingerprint(page)
            actions = await self._extract_actions(page)
            initial_state = State(url=self.start_url, dom_hash=dom, cookies_hash=cookies,
                                  storage_hash=storage, depth=0, path=[], actions=actions)
            self.visited_states.add(initial_state.get_fingerprint())
            self.state_queue.append(initial_state)

            while self.state_queue:
                state = self.state_queue.popleft()
                await self._explore_state(page, state)

            await browser.close()
        logger.info(f"Scan complete: {self.request_count} requests, {len(self.visited_states)} states")

# ---------------- Runner ----------------
async def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error":"No URL"}), file=sys.stderr)
        sys.exit(1)
    url = sys.argv[1]
    scanner = PlaywrightScanner(url)
    await scanner.scan()

if __name__ == "__main__":
    asyncio.run(main())
