"""
Playwright-based state-aware web crawler with BFS exploration
Tracks DOM states to avoid infinite loops and maximize coverage
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

    def __hash__(self):
        return hash((self.selector, self.text, self.tag, self.event_type))

    def __eq__(self, other):
        return isinstance(other, Action) and hash(self) == hash(other)

    def get_cluster_key(self) -> str:
        """Get key for clustering similar actions"""
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
        action_sig = frozenset(a.get_cluster_key() for a in self.actions)
        return hash((self.url, action_sig))

    def get_fingerprint(self):
        action_sig = frozenset(a.get_cluster_key() for a in self.actions)
        return (self.url, action_sig)

    def is_exhausted(self, no_new_endpoints: bool, no_new_clusters: bool) -> bool:
        """Check if state exploration is exhausted"""
        all_executed = len(self.executed_actions) >= len(self.actions)
        return all_executed or (no_new_endpoints and no_new_clusters)


class PlaywrightScanner:
    def __init__(self, url: str, max_depth: int = 2, timeout: int = 300, max_actions_per_state: int = 20, max_path_length: int = 10):
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

    def _is_static_resource(self, url: str) -> bool:
        """Check if URL is a static resource that should be skipped"""
        lower_url = url.lower().split('?')[0]
        return any(lower_url.endswith(ext) for ext in STATIC_EXTENSIONS)

    def _classify_action_semantic(self, text: str, selector: str, tag: str) -> str:
        """Classify action by semantic type"""
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

    def _make_request_key(self, method: str, url: str, body: str = None) -> str:
        """Create normalized unique key for request deduplication"""
        parsed = urlparse(url)
        normalized_path = parsed.path or '/'

        query_keys = sorted(parse_qs(parsed.query).keys()) if parsed.query else []
        query_sig = ','.join(query_keys)

        body_schema = ''
        if body:
            try:
                body_obj = json.loads(body)
                if isinstance(body_obj, dict):
                    body_schema = ','.join(sorted(body_obj.keys()))
            except:
                body_schema = str(hash(body))[:8]

        return f"{method}:{normalized_path}:{query_sig}:{body_schema}"

    async def _get_dom_hash(self, page: Page) -> str:
        """Get semantic DOM fingerprint ignoring dynamic content"""
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
        """Get full state fingerprint including cookies and storage"""
        cookies = await page.context.cookies()
        cookies_hash = hashlib.sha256(json.dumps(cookies, sort_keys=True, default=str).encode()).hexdigest()[:16]

        storage = await page.evaluate("""
            () => JSON.stringify({
                localStorage: {...localStorage},
                sessionStorage: {...sessionStorage}
            })
        """)
        storage_hash = hashlib.sha256(storage.encode()).hexdigest()[:16]

        dom_hash = await self._get_dom_hash(page)
        return dom_hash, cookies_hash, storage_hash

    async def _extract_actions(self, page: Page) -> Set[Action]:
        """Extract all clickable actions from current page"""
        actions = set()

        selectors = "button, a, input[type=submit], [role=button]"
        elements = await page.query_selector_all(selectors)

        for el in elements[:self.max_actions_per_state]:
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
                pass

        return actions

    async def _generate_selector(self, el: ElementHandle) -> str:
        """Generate semantic stable CSS selector for element"""
        try:
            selector = await el.evaluate("""
                el => {
                    if (el.dataset.testid) return `[data-testid="${el.dataset.testid}"]`;
                    if (el.getAttribute("aria-label")) return `[aria-label="${el.getAttribute("aria-label")}"]`;
                    if (el.id) return '#' + el.id;
                    if (el.name) return `[name="${el.name}"]`;
                    if (el.getAttribute("role")) {
                        const text = el.textContent?.trim().slice(0, 30);
                        if (text) return `[role="${el.getAttribute("role")}"][text*="${text}"]`;
                    }

                    let path = [];
                    let current = el;
                    while (current.parentElement && path.length < 3) {
                        let tag = current.tagName.toLowerCase();
                        let siblings = Array.from(current.parentElement.children).filter(e => e.tagName === current.tagName);
                        if (siblings.length > 1) {
                            let index = siblings.indexOf(current) + 1;
                            tag += `:nth-of-type(${index})`;
                        }
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
        """Smart fill all forms on page"""
        await page.evaluate("""
            () => {
                document.querySelectorAll('input, textarea, select').forEach(el => {
                    if (el.type === 'hidden') return;
                    if (el.type === 'checkbox' || el.type === 'radio') {
                        el.checked = true;
                    } else if (el.tagName === 'SELECT') {
                        if (el.options.length > 0) el.selectedIndex = 0;
                    } else if (el.type === 'email') {
                        el.value = 'test@test.com';
                    } else if (el.type === 'password') {
                        el.value = 'Password123!';
                    } else if (el.type === 'number') {
                        el.value = '1';
                    } else if (el.type === 'tel') {
                        el.value = '+1234567890';
                    } else if (el.type === 'url') {
                        el.value = 'https://test.com';
                    } else {
                        el.value = 'test';
                    }
                    el.dispatchEvent(new Event('change', { bubbles: true }));
                    el.dispatchEvent(new Event('input', { bubbles: true }));
                });
            }
        """)

    async def _execute_action(self, page: Page, action: Action) -> tuple[bool, bool]:
        """Execute single action and return (success, had_effect)"""
        try:
            element = await page.query_selector(action.selector)
            if element and await element.is_visible() and await element.is_enabled():
                initial_request_count = self.request_count

                await element.scroll_into_view_if_needed()
                await element.click(timeout=1000)

                try:
                    await page.wait_for_load_state("domcontentloaded", timeout=500)
                except:
                    pass

                await page.wait_for_timeout(200)

                had_effect = self.request_count > initial_request_count
                return True, had_effect
        except:
            pass
        return False, False

    async def intercept_request(self, route: Route):
        """Intercept and log all HTTP requests"""
        request = route.request

        if self._is_static_resource(request.url):
            await route.continue_()
            return

        parsed = urlparse(request.url)
        start_domain = urlparse(self.start_url).netloc
        request_domain = parsed.netloc

        if start_domain != request_domain:
            await route.continue_()
            return

        request_key = self._make_request_key(request.method, request.url, request.post_data)

        if request_key in self.seen_requests:
            await route.continue_()
            return

        self.seen_requests.add(request_key)

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

        key = self._make_request_key(request.method, request.url, request.post_data)
        self.pending_requests[key] = result

        await route.continue_()

    def _extract_json_keys(self, data: str) -> Set[str]:
        """Extract JSON keys from request/response body"""
        keys = set()
        try:
            obj = json.loads(data)
            if isinstance(obj, dict):
                keys.update(obj.keys())
                for v in obj.values():
                    if isinstance(v, dict):
                        keys.update(v.keys())
        except:
            pass
        return keys

    def _extract_graphql_operation(self, data: str, content_type: str) -> str:
        """Extract GraphQL operation name"""
        if "application/json" not in content_type.lower():
            return None

        try:
            obj = json.loads(data)
            if isinstance(obj, dict) and ("query" in obj or "mutation" in obj):
                return obj.get("operationName", "anonymous")
        except:
            pass
        return None

    async def handle_response(self, response: Response):
        """Handle response and combine with request data"""
        request = response.request
        key = self._make_request_key(request.method, request.url, request.post_data)

        if key in self.pending_requests:
            result = self.pending_requests.pop(key)

            result["response"] = {
                "status_code": response.status,
                "headers": dict(response.headers),
            }

            result["timestamp"] = asyncio.get_event_loop().time()

            self.results.append(result)
            self.request_count += 1

            parsed = urlparse(request.url)
            endpoint = f"{request.method} {parsed.path}"
            self.unique_endpoints.add(request.url)
            self.unique_methods_paths.add(endpoint)

            if request.post_data:
                self.unique_json_keys.update(self._extract_json_keys(request.post_data))

                content_type = request.headers.get("content-type", "")
                graphql_op = self._extract_graphql_operation(request.post_data, content_type)
                if graphql_op:
                    self.unique_graphql_ops.add(graphql_op)

            try:
                body = await response.text()
                self.unique_json_keys.update(self._extract_json_keys(body))
            except:
                pass

            logger.info(f"Found: {request.method} {request.url} -> {response.status}")
            print(json.dumps(result), flush=True)

    async def _find_element_by_action(self, page: Page, action: Action) -> ElementHandle:
        """Find element using multiple fallback strategies"""
        element = await page.query_selector(action.selector)
        if element and await element.is_visible():
            return element

        if action.text:
            elements = await page.query_selector_all(action.tag)
            for el in elements:
                text = (await el.text_content() or "").strip()
                if text == action.text and await el.is_visible():
                    return el

        return None

    async def _replay_state(self, page: Page, start_url: str, action_path: List[Action], expected_fingerprint: tuple = None):
        """Replay action sequence to reach specific state with validation"""
        try:
            await page.goto(start_url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(1000)

            for action in action_path:
                element = await self._find_element_by_action(page, action)
                if element and await element.is_enabled():
                    await element.click(timeout=1000)
                    try:
                        await page.wait_for_load_state("domcontentloaded", timeout=5000)
                    except:
                        pass
                    await page.wait_for_timeout(500)
                else:
                    logger.warning(f"Replay failed: element not found for {action.text[:30]}")
                    return False

            if expected_fingerprint:
                url_match = page.url == expected_fingerprint[0]
                if not url_match:
                    logger.warning(f"Replay mismatch: URL changed {page.url} != {expected_fingerprint[0]}")
                    return False

                current_actions = await self._extract_actions(page)
                action_signatures = {a.get_cluster_key() for a in current_actions}
                has_similar_actions = len(action_signatures) > 0

                if not has_similar_actions:
                    logger.warning(f"Replay mismatch: no similar actions found")
                    return False

            return True
        except Exception as e:
            logger.error(f"State replay failed: {e}")
            return False

    async def _explore_state(self, page: Page, state: State):
        """Explore single state by executing representative actions from each cluster"""
        logger.info(f"Exploring state: {state.url} (depth={state.depth}, actions={len(state.actions)})")

        await self._fill_forms(page)

        action_clusters = {}
        for action in state.actions:
            if action not in state.executed_actions and action not in state.dead_actions:
                cluster_key = action.get_cluster_key()
                if cluster_key not in action_clusters:
                    action_clusters[cluster_key] = action

        logger.info(f"Action clusters: {len(action_clusters)} ({', '.join(k.split(':')[0] for k in action_clusters.keys())})")

        initial_state_endpoints = len(state.discovered_endpoints)
        initial_state_clusters = len(state.executed_clusters)

        for cluster_key, action in action_clusters.items():
            if cluster_key in state.executed_clusters:
                continue

            try:
                dom_hash, cookies_hash, storage_hash = await self._get_state_fingerprint(page)
            except Exception as e:
                logger.warning(f"Failed to get state fingerprint before action: {e}")
                break

            initial_request_count = self.request_count
            initial_endpoints = self.unique_endpoints.copy()

            if action.semantic in ['submit', 'interaction', 'auth']:
                await self._fill_forms(page)
                await page.wait_for_timeout(100)

            success, _ = await self._execute_action(page, action)

            if not success:
                continue

            state.executed_actions.add(action)
            state.executed_clusters.add(cluster_key)

            try:
                new_dom, new_cookies, new_storage = await self._get_state_fingerprint(page)
                new_url = page.url
            except Exception as e:
                logger.warning(f"Failed to get state fingerprint after action (navigation?): {e}")
                break

            request_delta = self.request_count - initial_request_count
            new_endpoints = self.unique_endpoints - initial_endpoints
            dom_changed = new_dom != dom_hash
            cookies_changed = new_cookies != cookies_hash
            storage_changed = new_storage != storage_hash

            had_effect = request_delta > 0 or dom_changed or cookies_changed or storage_changed

            if not had_effect:
                state.dead_actions.add(action)
                logger.info(f"Dead action [{action.semantic}]: {action.text[:30]} (no requests, no state change)")
                continue

            state.discovered_endpoints.update(new_endpoints)
            if new_endpoints:
                logger.info(f"Action [{action.semantic}] discovered {len(new_endpoints)} new endpoints")

            new_fingerprint = (new_url, new_dom, new_cookies, new_storage)

            start_domain = urlparse(self.start_url).netloc
            new_domain = urlparse(new_url).netloc

            if new_fingerprint not in self.visited_states and state.depth < self.max_depth and len(state.path) < self.max_path_length and start_domain == new_domain and not state.is_volatile:
                try:
                    actions = await self._extract_actions(page)
                    new_state = State(
                        url=new_url,
                        dom_hash=new_dom,
                        cookies_hash=new_cookies,
                        storage_hash=new_storage,
                        depth=state.depth + 1,
                        path=state.path + [action],
                        actions=actions
                    )
                    self.visited_states.add(new_fingerprint)
                    self.state_queue.append(new_state)
                    logger.info(f"New state: {new_url} (dom={new_dom[:8]}, path_len={len(new_state.path)})")
                except Exception as e:
                    logger.warning(f"Failed to extract actions for new state: {e}")

            if new_fingerprint != state.get_fingerprint() and not state.is_volatile:
                replay_success = await self._replay_state(page, self.start_url, state.path, state.get_fingerprint())
                if not replay_success:
                    state.is_volatile = True
                    logger.info(f"State marked as volatile (non-deterministic), explore once only")
                    break

            new_endpoints_delta = len(state.discovered_endpoints) - initial_state_endpoints
            new_clusters_delta = len(state.executed_clusters) - initial_state_clusters
            if state.is_exhausted(new_endpoints_delta == 0, new_clusters_delta == 0):
                logger.info(f"State exhausted: {len(state.executed_clusters)} clusters executed, {len(state.discovered_endpoints)} endpoints discovered")
                break

    async def _check_convergence(self) -> bool:
        """Check if crawler has converged (no new discoveries)"""
        endpoints_delta = len(self.unique_endpoints) - self.last_endpoint_count
        requests_delta = self.request_count - self.last_request_count
        keys_delta = len(self.unique_json_keys) - self.last_keys_count
        graphql_delta = len(self.unique_graphql_ops) - self.last_graphql_count

        if endpoints_delta == 0 and requests_delta == 0 and keys_delta == 0 and graphql_delta == 0:
            self.stale_iterations += 1
        else:
            self.stale_iterations = 0

        self.last_request_count = self.request_count
        self.last_endpoint_count = len(self.unique_endpoints)
        self.last_keys_count = len(self.unique_json_keys)
        self.last_graphql_count = len(self.unique_graphql_ops)

        if self.stale_iterations >= 3:
            logger.info(f"Converged: Δendpoints=0 Δrequests=0 Δkeys=0 ΔgraphQL=0 for {self.stale_iterations} iterations")
            return True

        return False

    async def scan(self):
        """Main BFS scanning loop"""
        logger.info(f"Starting scan: {self.start_url} (max_depth={self.max_depth})")

        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=['--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu']
            )

            context = await browser.new_context(
                ignore_https_errors=True,
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            )

            page = await context.new_page()

            await page.add_init_script("""
                (() => {
                  const origFetch = window.fetch;
                  window.fetch = async (...args) => {
                    const res = await origFetch(...args);
                    res.clone().text().then(body => {
                      console.debug("FETCH", args[0], body);
                    });
                    return res;
                  };

                  const origOpen = XMLHttpRequest.prototype.open;
                  XMLHttpRequest.prototype.open = function(method, url) {
                    this.addEventListener('load', function() {
                      console.debug("XHR", method, url, this.responseText);
                    });
                    origOpen.apply(this, arguments);
                  };
                })();
            """)

            page.on("console", lambda msg: logger.info(f"Console: {msg.text}") if msg.type == "debug" else None)

            await page.route("**/*", self.intercept_request)
            page.on("response", self.handle_response)

            await page.goto(self.start_url, wait_until="networkidle", timeout=30000)
            await page.wait_for_timeout(2000)

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
                if await self._check_convergence() and len(self.state_queue) < 2:
                    break

                state = self.state_queue.popleft()

                try:
                    if not state.is_volatile and state.path:
                        await self._replay_state(page, self.start_url, state.path)
                    await self._explore_state(page, state)
                except Exception as e:
                    logger.error(f"Error exploring {state.url}: {e}")

            await browser.close()

        logger.info(f"Scan completed: {self.request_count} requests, {len(self.unique_endpoints)} endpoints, {len(self.unique_methods_paths)} methods, {len(self.unique_json_keys)} JSON keys, {len(self.unique_graphql_ops)} GraphQL ops, {len(self.visited_states)} states")


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
