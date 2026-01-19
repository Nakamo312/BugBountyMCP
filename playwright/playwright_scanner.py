"""
Playwright-based state-aware web crawler with BFS exploration
Optimized for bug bounty: faster, SPA-aware, maximal surface
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

# -------------------- Logging --------------------
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
        level_color = {
            'INFO': Colors.GREEN,
            'WARNING': Colors.YELLOW,
            'ERROR': Colors.RED
        }.get(level, Colors.RESET)
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

# -------------------- Config --------------------
STATIC_EXTENSIONS = {
    ".css", ".svg", ".png", ".jpg", ".jpeg", ".gif", ".ico", ".webp",
    ".woff", ".woff2", ".ttf", ".eot", ".otf",
    ".mp4", ".mp3", ".avi", ".webm", ".flv", ".wav", ".ogg",
    ".pdf", ".zip", ".tar", ".gz", ".rar", ".7z",
    ".exe", ".dll", ".bin", ".dmg", ".iso",
    ".map", ".min.js", ".min.css"
}

UNCLUSTERED = {"pagination", "data_loader"}  # Execute all

# -------------------- Data Classes --------------------
@dataclass
class Action:
    selector: str
    text: str
    tag: str
    event_type: str = "click"
    semantic: str = "unknown"

    def __hash__(self):
        return hash((self.selector, self.text, self.tag, self.event_type))

    def __eq__(self, other):
        return isinstance(other, Action) and hash(self) == hash(other)

    def get_cluster_key(self) -> str:
        text_words = ''.join(c for c in self.text.lower() if c.isalnum() or c.isspace()).split()
        text_sig = '_'.join(text_words[:3])
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
        parsed = urlparse(self.url)
        normalized_url = f"{parsed.netloc}{parsed.path}"
        query_keys = frozenset(parse_qs(parsed.query).keys()) if parsed.query else frozenset()
        return hash((normalized_url, query_keys, self.cookies_hash))

    def get_fingerprint(self):
        parsed = urlparse(self.url)
        normalized_url = f"{parsed.netloc}{parsed.path}"
        query_keys = frozenset(parse_qs(parsed.query).keys()) if parsed.query else frozenset()
        return (normalized_url, query_keys, self.cookies_hash)

    def is_exhausted(self, no_new_endpoints: bool, no_new_clusters: bool) -> bool:
        all_executed = len(self.executed_actions) >= len(self.actions)
        return all_executed or (no_new_endpoints and no_new_clusters)

# -------------------- Scanner --------------------
class PlaywrightScanner:
    def __init__(self, url: str, max_depth: int = 2, max_actions_per_state: int = 50):
        self.start_url = url
        self.max_depth = max_depth
        self.max_actions_per_state = max_actions_per_state

        self.visited_states: Set[tuple] = set()
        self.state_queue: deque[State] = deque()
        self.results: list[Dict[str, Any]] = []

        self.seen_requests: Set[str] = set()
        self.request_count = 0

        self.unique_endpoints: Set[str] = set()
        self.unique_json_keys: Set[str] = set()
        self.stale_iterations = 0
        self.last_endpoint_count = 0

    # -------------------- Helpers --------------------
    def _is_static_resource(self, url: str) -> bool:
        lower_url = url.lower().split('?')[0]
        return any(lower_url.endswith(ext) for ext in STATIC_EXTENSIONS)

    def _classify_action_semantic(self, text: str, selector: str, tag: str) -> str:
        text_lower = text.lower()
        selector_lower = selector.lower()
        if any(k in text_lower for k in ['next', 'prev', 'page', '»', '«', '>', '<']):
            return 'pagination'
        if any(k in text_lower for k in ['filter', 'sort', 'search', 'apply', 'category', 'tag']):
            return 'filter'
        if any(k in text_lower for k in ['submit', 'send', 'save', 'post', 'create', 'delete', 'update']):
            return 'submit'
        if any(k in text_lower for k in ['login', 'signup', 'logout', 'register']):
            return 'auth'
        if tag == 'a' or 'nav' in selector_lower or 'menu' in selector_lower:
            return 'navigation'
        if any(k in text_lower for k in ['load', 'more', 'show', 'expand', 'view']):
            return 'data_loader'
        return 'interaction'

    async def _get_dom_hash(self, page: Page) -> str:
        fingerprint = await page.evaluate("""
            () => {
                const forms = [...document.querySelectorAll('form')].length;
                const buttons = [...document.querySelectorAll('button,a,[role="button"]')].length;
                const inputs = [...document.querySelectorAll('input')].map(i => i.name || i.type).sort().join(',');
                const onclick = [...document.querySelectorAll('[onclick]')].length;
                return location.pathname + '|' + forms + '|' + buttons + '|' + onclick + '|' + inputs;
            }
        """)
        return hashlib.sha256(fingerprint.encode()).hexdigest()[:16]

    async def _get_state_fingerprint(self, page: Page):
        cookies = await page.context.cookies()
        cookies_hash = hashlib.sha256(json.dumps(cookies, sort_keys=True, default=str).encode()).hexdigest()[:16]
        storage = await page.evaluate("() => JSON.stringify({localStorage:{...localStorage},sessionStorage:{...sessionStorage}})")
        storage_hash = hashlib.sha256(storage.encode()).hexdigest()[:16]
        dom_hash = await self._get_dom_hash(page)
        return dom_hash, cookies_hash, storage_hash

    async def _extract_actions(self, page: Page, max_actions=None) -> Set[Action]:
        if max_actions is None:
            max_actions = self.max_actions_per_state
        actions = set()
        elements = await page.query_selector_all("button, a, input[type=submit], [role=button]")
        for el in elements[:max_actions]:
            try:
                if not await el.is_visible() or not await el.is_enabled():
                    continue
                text = (await el.text_content() or "").strip()[:50]
                tag = await el.evaluate("el => el.tagName.toLowerCase()")
                selector = await self._generate_selector(el)
                semantic = self._classify_action_semantic(text, selector, tag)
                if selector:
                    actions.add(Action(selector=selector, text=text, tag=tag, semantic=semantic))
            except:
                continue
        return actions

    async def _generate_selector(self, el: ElementHandle) -> str:
        try:
            selector = await el.evaluate("""
                el => {
                    if(el.dataset.testid) return `[data-testid="${el.dataset.testid}"]`;
                    if(el.id) return '#' + el.id;
                    let path = [];
                    let current = el;
                    while(current.parentElement && path.length < 3){
                        let tag = current.tagName.toLowerCase();
                        let siblings = Array.from(current.parentElement.children).filter(e=>e.tagName===current.tagName);
                        if(siblings.length>1) tag += `:nth-of-type(${siblings.indexOf(current)+1})`;
                        path.unshift(tag);
                        current = current.parentElement;
                    }
                    return path.join(' > ');
                }
            """)
            return selector
        except:
            return None

    async def _fill_forms(self, page: Page):
        await page.evaluate("""
            () => {
                document.querySelectorAll('input, textarea, select').forEach(el=>{
                    if(el.type==='hidden')return;
                    if(el.type==='checkbox'||el.type==='radio'){el.checked=true;}
                    else if(el.tagName==='SELECT'){if(el.options.length>0) el.selectedIndex=0;}
                    else if(el.type==='email'){el.value='test@test.com';}
                    else if(el.type==='password'){el.value='Password123!';}
                    else if(el.type==='number'){el.value='1';}
                    else if(el.type==='tel'){el.value='+1234567890';}
                    else if(el.type==='url'){el.value='https://test.com';}
                    else{el.value='test';}
                    el.dispatchEvent(new Event('change',{bubbles:true}));
                    el.dispatchEvent(new Event('input',{bubbles:true}));
                });
            }
        """)

    async def _execute_action(self, page: Page, action: Action, state: State) -> tuple[bool,bool]:
        try:
            el = await page.query_selector(action.selector)
            if el and await el.is_visible() and await el.is_enabled():
                initial_request_count = self.request_count
                current_url = page.url
                await el.scroll_into_view_if_needed()
                await el.click(timeout=1000)
                await page.wait_for_timeout(50)
                had_effect = self.request_count > initial_request_count or page.url != current_url
                return True, had_effect
        except:
            return False, False
        return False, False

    # -------------------- Request / Response --------------------
    async def handle_request(self, request):
        try:
            if self._is_static_resource(request.url) or request.resource_type in ["beacon", "ping"]:
                return
            parsed = urlparse(request.url)
            if parsed.netloc != urlparse(self.start_url).netloc:
                return
            key = f"{request.method}:{parsed.path}"
            if key not in self.seen_requests:
                self.seen_requests.add(key)
                self.request_count += 1
        except Exception as e:
            logger.warning(f"Request handling failed: {e}")

    async def handle_response(self, response: Response):
        try:
            body = await response.text()
            self.unique_json_keys.update(self._extract_json_keys(body))
        except:
            pass

    def _extract_json_keys(self, data: str) -> Set[str]:
        keys = set()
        try:
            obj = json.loads(data)
            if isinstance(obj, dict):
                keys.update(obj.keys())
        except:
            pass
        return keys

    # -------------------- Exploration --------------------
    async def _explore_state(self, page: Page, state: State):
        await self._fill_forms(page)
        max_actions = 100 if state.depth==0 else 40
        actions = await self._extract_actions(page, max_actions=max_actions)
        state.actions.update(actions)

        action_clusters = {}
        for action in state.actions:
            if action.semantic in UNCLUSTERED:
                action_clusters[action.get_cluster_key()] = action
            else:
                cluster_key = action.get_cluster_key()
                if cluster_key not in action_clusters:
                    action_clusters[cluster_key] = action

        for cluster_key, action in action_clusters.items():
            if cluster_key in state.executed_clusters:
                continue
            success, had_effect = await self._execute_action(page, action, state)
            if not success:
                continue
            state.executed_actions.add(action)
            state.executed_clusters.add(cluster_key)
            if had_effect:
                self.unique_endpoints.add(page.url)
                state.discovered_endpoints.add(page.url)
                if state.depth < self.max_depth:
                    dom_hash, cookies_hash, storage_hash = await self._get_state_fingerprint(page)
                    new_state = State(
                        url=page.url,
                        dom_hash=dom_hash,
                        cookies_hash=cookies_hash,
                        storage_hash=storage_hash,
                        depth=state.depth+1,
                        path=state.path + [action],
                        actions=set()
                    )
                    fp = new_state.get_fingerprint()
                    if fp not in self.visited_states:
                        self.visited_states.add(fp)
                        self.state_queue.append(new_state)

    async def _check_convergence(self) -> bool:
        endpoints_delta = len(self.unique_endpoints) - self.last_endpoint_count
        if endpoints_delta == 0:
            self.stale_iterations += 1
        else:
            self.stale_iterations = 0
        self.last_endpoint_count = len(self.unique_endpoints)
        if self.stale_iterations >= 10 and len(self.state_queue) < 2:
            logger.info("Crawler converged.")
            return True
        return False

    # -------------------- Main --------------------
    async def scan(self):
        logger.info(f"Starting scan: {self.start_url}")
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, args=['--no-sandbox','--disable-gpu'])
            context = await browser.new_context(ignore_https_errors=True, user_agent='Mozilla/5.0')
            page = await context.new_page()
            # Safe async callbacks
            page.on("request", lambda req: asyncio.create_task(self.handle_request(req)))
            page.on("response", lambda res: asyncio.create_task(self.handle_response(res)))

            await page.goto(self.start_url)
            await page.wait_for_timeout(50)

            dom_hash, cookies_hash, storage_hash = await self._get_state_fingerprint(page)
            initial_actions = await self._extract_actions(page)

            initial_state = State(
                url=self.start_url,
                dom_hash=dom_hash,
                cookies_hash=cookies_hash,
                storage_hash=storage_hash,
                depth=0,
                path=[],
                actions=initial_actions
            )
            self.visited_states.add(initial_state.get_fingerprint())
            self.state_queue.append(initial_state)

            while self.state_queue:
                if await self._check_convergence():
                    break
                state = self.state_queue.popleft()
                await self._explore_state(page, state)

            await browser.close()
        logger.info(f"Scan completed: {len(self.unique_endpoints)} endpoints, {len(self.visited_states)} states explored.")

# -------------------- Entry --------------------
async def main():
    if len(sys.argv)<2:
        print(json.dumps({"error":"No URL provided"}),file=sys.stderr)
        sys.exit(1)
    url = sys.argv[1]
    max_depth = int(sys.argv[2]) if len(sys.argv)>2 else 2
    scanner = PlaywrightScanner(url,max_depth=max_depth)
    await scanner.scan()

if __name__=="__main__":
    asyncio.run(main())
