"""
Playwright-based state-aware web crawler with BFS exploration
Tracks DOM states to avoid infinite loops and maximize coverage
"""
import asyncio
import json
import logging
import sys
import hashlib
import time
from typing import Set, Dict, Any, List, Tuple, Optional
from urllib.parse import urlparse, parse_qs, urljoin
from dataclasses import dataclass, field
from collections import deque, defaultdict


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
    href: Optional[str] = None
    event_type: str = "click"
    semantic: str = "unknown"
    wait_for_requests: bool = False

    def __hash__(self):
        return hash((self.semantic, self.tag, self.text[:30].lower(), self.href))

    def __eq__(self, other):
        return isinstance(other, Action) and hash(self) == hash(other)

    def get_cluster_key(self) -> str:
        text_words = ''.join(c for c in self.text.lower() if c.isalnum() or c.isspace()).split()
        text_sig = '_'.join(text_words[:3])
        href_sig = self.href[:20] if self.href else ''
        return f"{self.semantic}:{self.tag}:{text_sig}:{href_sig}"


@dataclass
class State:
    url: str
    normalized_url: str
    dom_hash: str
    dom_vector: Dict[str, int]
    cookies_hash: str
    storage_hash: str
    depth: int
    path: List[Action] = field(default_factory=list)
    actions: Set[Action] = field(default_factory=set)
    executed_actions: Set[str] = field(default_factory=set)
    discovered_endpoints: Set[str] = field(default_factory=set)
    child_urls: Set[str] = field(default_factory=set)
    visited_count: int = 0

    def get_state_key(self) -> str:
        return self.normalized_url

    def is_exhausted(self) -> bool:
        if len(self.actions) == 0:
            return True
        
        executed_ratio = len(self.executed_actions) / len(self.actions)
        return executed_ratio >= 0.95 or self.visited_count >= 2


class PlaywrightScanner:
    def __init__(self, url: str, max_depth: int = 3, timeout: int = 300, max_actions_per_state: int = 30, max_path_length: int = 10):
        self.start_url = url
        self.start_domain = urlparse(url).netloc
        self.max_depth = max_depth
        self.timeout = timeout
        self.max_actions_per_state = max_actions_per_state
        self.max_path_length = max_path_length
        
        self.state_queue: deque[State] = deque()
        self.results: list[Dict[str, Any]] = []
        self.pending_requests: Dict[str, Dict[str, Any]] = {}
        self.seen_requests: Set[str] = set()
        
        self.visited_urls: Set[str] = set()
        self.url_to_state: Dict[str, State] = {}
        self.state_graph: Dict[str, Set[str]] = defaultdict(set)
        
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
        
        self.states_created = 0
        self.states_skipped = 0
        
        self.active_xhr_requests: Set[str] = set()
        self.xhr_timeout = 3.0

    def _normalize_url(self, url: str) -> str:
        parsed = urlparse(url)
        normalized = f"{parsed.netloc}{parsed.path}"
        if parsed.query:
            query_params = parse_qs(parsed.query, keep_blank_values=True)
            sorted_params = sorted(query_params.items())
            query_string = "&".join(f"{k}={','.join(sorted(v))}" for k, v in sorted_params)
            normalized += "?" + query_string
        return normalized

    def _is_same_domain(self, url: str) -> bool:
        return urlparse(url).netloc == self.start_domain

    def _is_static_resource(self, url: str) -> bool:
        lower_url = url.lower().split('?')[0]
        return any(lower_url.endswith(ext) for ext in STATIC_EXTENSIONS)

    def _classify_action_semantic(self, text: str, selector: str, tag: str, href: Optional[str] = None) -> str:
        text_lower = text.lower()
        selector_lower = selector.lower()
        
        if href and href.startswith('javascript:'):
            return 'javascript'
        
        if href and 'logout' in href.lower():
            return 'logout'
        
        if any(k in text_lower for k in ['login', 'signin', 'sign up', 'register']):
            return 'auth'
        
        if any(k in text_lower for k in ['logout', 'sign out', 'exit']):
            return 'logout'
        
        if any(k in text_lower for k in ['submit', 'save', 'post', 'create', 'delete', 'update']):
            return 'submit'
        
        if any(k in text_lower for k in ['search', 'find', 'filter', 'sort']):
            return 'search'
        
        if any(k in text_lower for k in ['next', 'prev', 'page', '»', '«', '>', '<', 'more']):
            return 'pagination'
        
        if any(k in text_lower for k in ['cart', 'buy', 'purchase', 'order', 'checkout']):
            return 'commerce'
        
        if tag == 'a' and href:
            return 'navigation'
        
        if tag == 'form':
            return 'form_submit'
        
        return 'interaction'

    def _make_request_key(self, method: str, url: str, body: str = None) -> str:
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

    async def _get_dom_vector(self, page: Page) -> Dict[str, int]:
        return await page.evaluate("""
            () => {
                const v = {};
                const inc = k => v[k] = (v[k] || 0) + 1;

                const importantTags = ['form', 'input', 'button', 'a', 'select', 'textarea', 'nav', 'header', 'section', 'article', 'main'];
                importantTags.forEach(tag => {
                    inc(`tag_${tag}` + document.querySelectorAll(tag).length);
                });
                
                inc('forms:' + document.forms.length);
                inc('buttons:' + document.querySelectorAll('button,[role="button"]').length);
                inc('links:' + document.querySelectorAll('a').length);
                inc('inputs:' + document.querySelectorAll('input:not([type="hidden"])').length);
                
                return v;
            }
        """)

    async def _get_dom_hash(self, page: Page) -> str:
        vector = await self._get_dom_vector(page)
        vector_str = json.dumps(sorted(vector.items()), sort_keys=True)
        return hashlib.sha256(vector_str.encode()).hexdigest()[:16]

    async def _get_state_fingerprint(self, page: Page):
        cookies = await page.context.cookies()
        cookies_hash = hashlib.sha256(json.dumps(cookies, sort_keys=True, default=str).encode()).hexdigest()[:16]

        storage = await page.evaluate("""
            () => JSON.stringify({
                localStorage: {...localStorage},
                sessionStorage: {...sessionStorage}
            })
        """)
        storage_hash = hashlib.sha256(storage.encode()).hexdigest()[:16]

        dom_vector = await self._get_dom_vector(page)
        dom_hash = hashlib.sha256(json.dumps(sorted(dom_vector.items()), sort_keys=True).encode()).hexdigest()[:16]
        
        return dom_hash, dom_vector, cookies_hash, storage_hash

    async def _extract_actions(self, page: Page, current_url: str) -> Set[Action]:
        actions = set()

        selectors = """
            button, 
            a:not([href^="javascript:"]):not([href^="#"]), 
            input[type=submit], 
            input[type=button],
            [role=button],
            form,
            [onclick],
            [data-action],
            [data-submit]
        """
        
        elements = await page.query_selector_all(selectors)

        for el in elements[:self.max_actions_per_state]:
            try:
                if not await el.is_visible():
                    continue
                    
                is_enabled = await el.is_enabled()
                if not is_enabled:
                    continue

                text = (await el.text_content() or "").strip()[:100]
                tag = await el.evaluate("el => el.tagName.toLowerCase()")
                
                href = None
                if tag == 'a':
                    href = await el.get_attribute("href")
                    if href:
                        href = urljoin(current_url, href)
                        if not self._is_same_domain(href):
                            continue
                
                selector = await self._generate_selector(el)
                if not selector:
                    continue
                    
                semantic = self._classify_action_semantic(text, selector, tag, href)
                
                wait_for_requests = semantic in ['submit', 'search', 'form_submit', 'auth']
                
                action = Action(
                    selector=selector,
                    text=text,
                    tag=tag,
                    href=href,
                    semantic=semantic,
                    wait_for_requests=wait_for_requests
                )
                actions.add(action)
                    
            except Exception as e:
                continue

        return actions

    async def _generate_selector(self, el: ElementHandle) -> str:
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
                });
            }
        """)

    async def _wait_for_xhr_requests(self, page: Page, timeout: float = 3.0):
        """Wait for XHR/Fetch requests to complete"""
        start_time = time.time()
        while time.time() - start_time < timeout:
            xhr_count = await page.evaluate("""
                () => {
                    const xhrs = window.performance.getEntriesByType('resource')
                        .filter(r => r.initiatorType === 'xmlhttprequest' || r.initiatorType === 'fetch');
                    const activeXhrs = performance.getEntries()
                        .filter(e => e.entryType === 'resource' && 
                            (e.initiatorType === 'xmlhttprequest' || e.initiatorType === 'fetch') &&
                            e.responseEnd === 0);
                    return activeXhrs.length;
                }
            """)
            if xhr_count == 0:
                return True
            await asyncio.sleep(0.1)
        return False

    async def _execute_action(self, page: Page, action: Action) -> tuple[bool, str, bool]:
        try:
            element = await self._find_element_by_action(page, action)
            if not element:
                return False, None, False
                
            is_visible = await element.is_visible()
            is_enabled = await element.is_enabled()
            
            if not is_visible or not is_enabled:
                return False, None, False

            initial_url = page.url
            initial_request_count = self.request_count

            await element.scroll_into_view_if_needed()
            
            if action.semantic in ['submit', 'auth', 'form_submit']:
                await self._fill_forms(page)
                await page.wait_for_timeout(200)
            
            await element.click(timeout=2000)

            if action.wait_for_requests:
                await self._wait_for_xhr_requests(page, self.xhr_timeout)
                try:
                    await page.wait_for_load_state("networkidle", timeout=5000)
                except:
                    pass
            else:
                try:
                    await page.wait_for_load_state("domcontentloaded", timeout=3000)
                except:
                    pass
            
            await page.wait_for_timeout(800)

            new_url = page.url
            had_effect = (self.request_count > initial_request_count) or (new_url != initial_url)
            
            return True, new_url, had_effect
            
        except Exception as e:
            logger.debug(f"Action execution failed for {action.text}: {e}")
            return False, None, False

    async def intercept_request(self, route: Route):
        request = route.request

        if self._is_static_resource(request.url):
            await route.continue_()
            return

        if request.resource_type in ["beacon", "ping"]:
            await route.continue_()
            return

        parsed = urlparse(request.url)
        start_domain = urlparse(self.start_url).netloc
        request_domain = parsed.netloc

        result = {
            "request": {
                "method": request.method,
                "endpoint": request.url,
                "headers": dict(request.headers),
                "resource_type": request.resource_type,
            }
        }

        if request.method in ["POST", "PUT", "PATCH"] and request.post_data:
            result["request"]["body"] = request.post_data

        result["request"]["raw"] = f"{request.method} {parsed.path or '/'}"
        if parsed.query:
            result["request"]["raw"] += f"?{parsed.query}"
        result["request"]["raw"] += " HTTP/1.1\r\n"

        for k, v in request.headers.items():
            result["request"]["raw"] += f"{k}: {v}\r\n"
        result["request"]["raw"] += "\r\n"

        if request.post_data:
            result["request"]["raw"] += request.post_data

        key = self._make_request_key(request.method, request.url, request.post_data)

        if key not in self.seen_requests:
            self.seen_requests.add(key)
            self.pending_requests[key] = result

            if request.method == "POST":
                logger.info(f"Captured POST: {parsed.path} [body: {len(request.post_data) if request.post_data else 0} bytes]")
            else:
                logger.info(f"Captured: {request.method} {parsed.path}")

        await route.continue_()

    def _extract_json_keys(self, data: str) -> Set[str]:
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

    def _extract_graphql_operation(self, data: str, content_type: str, url: str) -> str:
        if "graphql" in url.lower() or "application/graphql" in content_type.lower():
            return "graphql_raw"

        if "application/json" not in content_type.lower():
            return None

        try:
            obj = json.loads(data)
            if isinstance(obj, list):
                if any("query" in item or "mutation" in item for item in obj if isinstance(item, dict)):
                    return "graphql_batch"
            elif isinstance(obj, dict):
                if "query" in obj or "mutation" in obj:
                    return obj.get("operationName", "anonymous")
                if "id" in obj and "variables" in obj:
                    return "graphql_persisted"
        except:
            pass
        return None

    async def handle_response(self, response: Response):
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
                graphql_op = self._extract_graphql_operation(request.post_data, content_type, request.url)
                if graphql_op:
                    self.unique_graphql_ops.add(graphql_op)

                try:
                    body_obj = json.loads(request.post_data)
                    if isinstance(body_obj, dict):
                        body_schema = ','.join(sorted(body_obj.keys()))
                        logger.info(f"POST body schema: {body_schema}")
                except:
                    pass

            try:
                body = await response.text()
                if body:
                    self.unique_json_keys.update(self._extract_json_keys(body))
                    if request.method == "POST":
                        logger.info(f"Response: {request.method} {parsed.path} -> {response.status} [body: {len(body)} chars]")
                    else:
                        logger.info(f"Response: {request.method} {parsed.path} -> {response.status}")
            except:
                logger.info(f"Response: {request.method} {parsed.path} -> {response.status}")

            print(json.dumps(result), flush=True)

    async def _find_element_by_action(self, page: Page, action: Action) -> ElementHandle:
        try:
            element = await page.query_selector(action.selector)
            if element and await element.is_visible():
                return element

            if action.text:
                elements = await page.query_selector_all(action.tag)
                for el in elements:
                    text = (await el.text_content() or "").strip()
                    if text and text.lower() == action.text.lower() and await el.is_visible():
                        return el
        except:
            pass
        return None

    async def _should_skip_state(self, url: str, depth: int, path_length: int) -> bool:
        normalized_url = self._normalize_url(url)
        
        if not self._is_same_domain(url):
            self.states_skipped += 1
            logger.info(f"Different domain: {url}")
            return True
        
        if normalized_url in self.visited_urls:
            self.states_skipped += 1
            logger.debug(f"Already visited: {url}")
            return True
        
        if depth > self.max_depth:
            self.states_skipped += 1
            logger.info(f"Max depth exceeded: {depth}")
            return True
        
        if path_length >= self.max_path_length:
            self.states_skipped += 1
            logger.info(f"Max path length exceeded: {path_length}")
            return True
        
        return False

    async def _explore_state(self, page: Page, state: State):
        logger.info(f"Exploring state: {state.url} (depth={state.depth}, actions={len(state.actions)})")

        state.visited_count += 1
        
        await self._fill_forms(page)

        try:
            await page.mouse.wheel(0, 1000)
            await page.wait_for_timeout(300)
        except:
            pass

        priority_order = {
            'form_submit': 1,
            'submit': 2,
            'auth': 3,
            'search': 4,
            'commerce': 5,
            'pagination': 6,
            'navigation': 7,
            'interaction': 8,
            'logout': 9,
            'javascript': 10
        }
        
        sorted_actions = sorted(
            [a for a in state.actions if a.get_cluster_key() not in state.executed_actions],
            key=lambda x: priority_order.get(x.semantic, 99)
        )
        
        logger.info(f"Actions to explore: {len(sorted_actions)}")

        initial_endpoints = len(self.unique_endpoints)
        
        for action in sorted_actions:
            if state.is_exhausted():
                break
                
            action_key = action.get_cluster_key()
            if action_key in state.executed_actions:
                continue
                
            logger.info(f"Executing: [{action.semantic}] {action.text[:30]}")
            
            success, new_url, had_effect = await self._execute_action(page, action)
            
            if not success:
                state.executed_actions.add(action_key)
                continue
            
            state.executed_actions.add(action_key)
            
            if had_effect and new_url:
                normalized_new_url = self._normalize_url(new_url)
                
                if not self._should_skip_state(new_url, state.depth + 1, len(state.path) + 1):
                    
                    if normalized_new_url not in self.visited_urls:
                        try:
                            await page.wait_for_timeout(1000)
                            
                            dom_hash, dom_vector, cookies_hash, storage_hash = await self._get_state_fingerprint(page)
                            
                            new_actions = await self._extract_actions(page, new_url)
                            
                            new_state = State(
                                url=new_url,
                                normalized_url=normalized_new_url,
                                dom_hash=dom_hash,
                                dom_vector=dom_vector,
                                cookies_hash=cookies_hash,
                                storage_hash=storage_hash,
                                depth=state.depth + 1,
                                path=state.path + [action],
                                actions=new_actions
                            )
                            
                            self.visited_urls.add(normalized_new_url)
                            self.state_queue.append(new_state)
                            self.states_created += 1
                            state.child_urls.add(normalized_new_url)
                            
                            logger.info(f"New state [{self.states_created}]: {new_url} (depth={new_state.depth}, actions={len(new_actions)})")
                            
                            await page.goto(state.url, wait_until="domcontentloaded", timeout=10000)
                            await page.wait_for_timeout(500)
                            
                        except Exception as e:
                            logger.debug(f"Failed to create new state: {e}")
                            await page.goto(state.url, wait_until="domcontentloaded", timeout=10000)
                    else:
                        logger.debug(f"Already visited: {new_url}")
                        await page.goto(state.url, wait_until="domcontentloaded", timeout=10000)
                else:
                    await page.goto(state.url, wait_until="domcontentloaded", timeout=10000)
            else:
                logger.info(f"Dead action [{action.semantic}]: {action.text[:30]}")
        
        endpoints_discovered = len(self.unique_endpoints) - initial_endpoints
        logger.info(f"State exhausted: {len(state.executed_actions)}/{len(state.actions)} actions, {endpoints_discovered} new endpoints")

    async def _check_convergence(self) -> bool:
        endpoints_delta = len(self.unique_endpoints) - self.last_endpoint_count
        requests_delta = self.request_count - self.last_request_count
        
        if endpoints_delta == 0 and requests_delta == 0:
            self.stale_iterations += 1
        else:
            self.stale_iterations = 0

        self.last_request_count = self.request_count
        self.last_endpoint_count = len(self.unique_endpoints)
        
        if self.stale_iterations >= 3 and len(self.state_queue) == 0:
            logger.info(f"Converged: Δendpoints=0 Δrequests=0 for {self.stale_iterations} iterations, queue empty")
            return True

        return False

    async def scan(self):
        logger.info(f"Starting scan: {self.start_url} (max_depth={self.max_depth})")

        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=['--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu']
            )

            context = await browser.new_context(
                ignore_https_errors=True,
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                service_workers='block'
            )

            page = await context.new_page()

            def log_request(request):
                if not self._is_static_resource(request.url) and request.resource_type not in ["beacon", "ping"]:
                    parsed = urlparse(request.url)
                    start_domain = urlparse(self.start_url).netloc
                    if parsed.netloc == start_domain:
                        logger.info(f"Request: {request.method} {request.url}")

            page.on("request", log_request)

            await page.add_init_script("""
                (() => {
                    window._capturedRequests = [];
                    
                    const origFetch = window.fetch;
                    window.fetch = async (...args) => {
                        const startTime = Date.now();
                        try {
                            const response = await origFetch(...args);
                            const endTime = Date.now();
                            window._capturedRequests.push({
                                type: 'fetch',
                                url: args[0],
                                method: args[1]?.method || 'GET',
                                status: response.status,
                                duration: endTime - startTime
                            });
                            return response;
                        } catch (error) {
                            return Promise.reject(error);
                        }
                    };

                    const origOpen = XMLHttpRequest.prototype.open;
                    XMLHttpRequest.prototype.open = function(method, url, async, user, password) {
                        this._requestStart = Date.now();
                        this._method = method;
                        this._url = url;
                        
                        this.addEventListener('load', function() {
                            const duration = Date.now() - this._requestStart;
                            window._capturedRequests.push({
                                type: 'xhr',
                                url: this._url,
                                method: this._method,
                                status: this.status,
                                duration: duration
                            });
                        });
                        
                        origOpen.apply(this, arguments);
                    };
                    
                    const origFormSubmit = HTMLFormElement.prototype.submit;
                    HTMLFormElement.prototype.submit = function() {
                        const formData = new FormData(this);
                        const data = {};
                        for (let [key, value] of formData.entries()) {
                            data[key] = value;
                        }
                        window._capturedRequests.push({
                            type: 'form_submit',
                            url: this.action || window.location.href,
                            method: this.method || 'POST',
                            data: data
                        });
                        return origFormSubmit.apply(this, arguments);
                    };
                })();
            """)

            page.on("console", lambda msg: logger.info(f"Console[{msg.type}]: {msg.text}"))

            await page.route("**/*", self.intercept_request)
            page.on("response", self.handle_response)

            await page.goto(self.start_url, wait_until="networkidle", timeout=30000)
            await page.wait_for_timeout(2000)

            dom_hash, dom_vector, cookies_hash, storage_hash = await self._get_state_fingerprint(page)
            initial_url = page.url
            normalized_initial_url = self._normalize_url(initial_url)
            initial_actions = await self._extract_actions(page, initial_url)

            initial_state = State(
                url=initial_url,
                normalized_url=normalized_initial_url,
                dom_hash=dom_hash,
                dom_vector=dom_vector,
                cookies_hash=cookies_hash,
                storage_hash=storage_hash,
                depth=0,
                path=[],
                actions=initial_actions
            )

            self.visited_urls.add(normalized_initial_url)
            self.state_queue.append(initial_state)

            logger.info(f"Initial state has {len(initial_actions)} actions")

            while self.state_queue:
                if await self._check_convergence():
                    logger.info("Convergence detected, finishing...")
                    break

                state = self.state_queue.popleft()
                
                logger.info(f"Processing state {state.url} (queue: {len(self.state_queue)}, created: {self.states_created}, skipped: {self.states_skipped})")

                try:
                    if page.url != state.url:
                        await page.goto(state.url, wait_until="domcontentloaded", timeout=10000)
                        await page.wait_for_timeout(1000)
                    
                    await self._explore_state(page, state)
                    
                except Exception as e:
                    logger.error(f"Error exploring {state.url}: {e}")

            await browser.close()

        logger.info(f"""
Scan completed:
  Requests: {self.request_count}
  Endpoints: {len(self.unique_endpoints)}
  Methods/Paths: {len(self.unique_methods_paths)}
  JSON Keys: {len(self.unique_json_keys)}
  GraphQL Ops: {len(self.unique_graphql_ops)}
  States Created: {self.states_created}
  States Skipped: {self.states_skipped}
  Unique URLs visited: {len(self.visited_urls)}
""")


async def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "No URL provided"}), file=sys.stderr)
        sys.exit(1)

    url = sys.argv[1]
    max_depth = int(sys.argv[2]) if len(sys.argv) > 2 else 3

    scanner = PlaywrightScanner(url, max_depth=max_depth)

    try:
        await scanner.scan()
    except Exception as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())