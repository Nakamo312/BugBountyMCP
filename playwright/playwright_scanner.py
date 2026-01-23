"""
Playwright-based state-aware web crawler with recursive DFS exploration using threads
Improved form submission, replay reliability, parameter fuzzing, less aggressive deduplication
"""
import asyncio
import json
import logging
import sys
import hashlib
from typing import Set, Dict, Any, List, Tuple
from urllib.parse import urlparse, parse_qs, urlencode
from dataclasses import dataclass, field
import threading
from collections import defaultdict

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
        return hash((self.semantic, self.tag, self.text[:30].lower()))

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
    dom_vector: Dict[str, int]
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
    visited_count: int = 0

    def get_fingerprint(self):
        parsed = urlparse(self.url)
        normalized_url = f"{parsed.netloc}{parsed.path}"
        query_params = frozenset(sorted(parse_qs(parsed.query).items())) if parsed.query else frozenset()
        action_signature = hash(frozenset(a.get_cluster_key() for a in self.actions))
        dom_vector_str = json.dumps(sorted(self.dom_vector.items()), sort_keys=True)
        dom_hash = hashlib.sha256(dom_vector_str.encode()).hexdigest()[:16]
        return (normalized_url, query_params, self.cookies_hash, self.storage_hash, dom_hash, action_signature)

    def get_semantic_key(self):
        parsed = urlparse(self.url)
        normalized_url = f"{parsed.netloc}{parsed.path}"
        key_features = {
            'forms': self.dom_vector.get('forms', 0),
            'buttons': self.dom_vector.get('buttons', 0),
            'links': self.dom_vector.get('links', 0),
        }
        return f"{normalized_url}:{key_features['forms']}:{key_features['buttons']}:{key_features['links']}"

    def is_exhausted(self, no_new_endpoints: bool, no_new_clusters: bool) -> bool:
        all_executed = len(self.executed_actions) >= len(self.actions)
        visited_too_much = self.visited_count >= 3
        return all_executed or (no_new_endpoints and no_new_clusters) or visited_too_much

class PlaywrightScanner:
    def __init__(self, url: str, max_depth: int = 3, timeout: int = 300, max_actions_per_state: int = 25, max_path_length: int = 15):
        self.start_url = url
        self.max_depth = max_depth
        self.timeout = timeout
        self.max_actions_per_state = max_actions_per_state
        self.max_path_length = max_path_length
        
        self.results: list[Dict[str, Any]] = []
        self.pending_requests: Dict[str, Dict[str, Any]] = {}
        self.seen_requests: Set[str] = set()
        
        self.visited_states: Set[Tuple] = set()
        self.semantic_states: Set[str] = set()
        self.visited_sequences: Set[str] = set()
        
        self.unique_endpoints: Set[str] = set()
        self.unique_methods_paths: Set[str] = set()
        self.unique_json_keys: Set[str] = set()
        self.unique_graphql_ops: Set[str] = set()
        self.request_count = 0
        
        self.states_created = 0
        self.states_skipped = 0
        
        self.lock = threading.Lock()
        self.active_count = 0
        self.done_event = threading.Event()
        self.semaphore = threading.Semaphore(5)  # max 5 parallel browsers

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
        if any(k in text_lower for k in ['submit', 'send', 'save', 'post', 'create', 'delete', 'update', 'login', 'sign', 'register']):
            return 'submit'
        if any(k in text_lower for k in ['login', 'signup', 'logout', 'register']):
            return 'auth'
        if tag == 'a' or 'nav' in selector_lower or 'menu' in selector_lower:
            return 'navigation'
        if any(k in text_lower for k in ['load', 'more', 'show', 'expand', 'view']):
            return 'data_loader'
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
                importantTags.forEach(tag => inc(`tag_${tag}` + document.querySelectorAll(tag).length));
                inc('forms:' + document.forms.length);
                inc('buttons:' + document.querySelectorAll('button,[role="button"]').length);
                inc('links:' + document.querySelectorAll('a').length);
                inc('inputs:' + document.querySelectorAll('input:not([type="hidden"])').length);
                document.querySelectorAll('button, a').forEach(el => {
                    const text = el.textContent?.toLowerCase() || '';
                    if (text.includes('next') || text.includes('prev') || text.includes('page')) inc('pattern_pagination');
                    if (text.includes('search')) inc('pattern_search');
                    if (text.includes('login') || text.includes('sign')) inc('pattern_auth');
                    if (text.includes('submit') || text.includes('save')) inc('pattern_submit');
                });
                return v;
            }
        """)

    async def _get_dom_hash(self, page: Page) -> str:
        vector = await self._get_dom_vector(page)
        vector_str = json.dumps(sorted(vector.items()), sort_keys=True)
        return hashlib.sha256(vector_str.encode()).hexdigest()[:16]

    def _dom_similarity(self, a: Dict[str, int], b: Dict[str, int]) -> float:
        if not a or not b:
            return 0.0
        important_features = ['forms:', 'buttons:', 'links:', 'inputs:', 'pattern_']
        total_weight = 0
        similarity_sum = 0
        for key in set(a.keys()) | set(b.keys()):
            weight = 2.0 if any(key.startswith(p) for p in important_features) else 1.0
            val_a = a.get(key, 0)
            val_b = b.get(key, 0)
            if val_a + val_b > 0:
                similarity = 1 - abs(val_a - val_b) / max(val_a + val_b, 1)
                similarity_sum += similarity * weight
                total_weight += weight
        return similarity_sum / total_weight if total_weight > 0 else 1.0

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

    async def _extract_actions(self, page: Page) -> Set[Action]:
        actions = set()
        selectors = "a, button, input[type=submit], input[type=button], [role=button], [onclick]"
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
        try:
            return await el.evaluate("""
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
                    while (current.parentElement && path.length < 4) {
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
        except:
            return ""

    async def _fill_and_submit_forms(self, page: Page):
        """Заполняет и пытается отправить все формы на странице"""
        try:
            forms = await page.query_selector_all('form')
            for form in forms:
                await form.evaluate("""
                    form => {
                        form.querySelectorAll('input, textarea, select').forEach(el => {
                            if (el.type === 'hidden') return;
                            if (el.type === 'checkbox' || el.type === 'radio') {
                                el.checked = true;
                            } else if (el.tagName === 'SELECT') {
                                if (el.options.length > 0) el.selectedIndex = Math.floor(Math.random() * el.options.length);
                            } else if (el.type === 'email' || el.type === 'text') {
                                el.value = 'test' + Math.random().toString(36).substring(7) + '@example.com';
                            } else if (el.type === 'password') {
                                el.value = 'TestPass123!';
                            } else if (el.type === 'number') {
                                el.value = '42';
                            } else {
                                el.value = 'test value';
                            }
                            el.dispatchEvent(new Event('input', { bubbles: true }));
                            el.dispatchEvent(new Event('change', { bubbles: true }));
                        });
                        // Принудительный submit
                        const submitBtn = form.querySelector('input[type=submit], button[type=submit], button:not([type])');
                        if (submitBtn) {
                            submitBtn.click();
                        } else {
                            form.submit();
                        }
                    }
                """)
                await page.wait_for_timeout(800)
        except Exception as e:
            logger.warning(f"Form submit failed: {e}")

    async def _execute_action(self, page: Page, action: Action) -> tuple[bool, bool]:
        try:
            element = await page.query_selector(action.selector)
            if not element or not await element.is_visible() or not await element.is_enabled():
                return False, False

            initial_request_count = self.request_count
            initial_url = page.url
            await element.scroll_into_view_if_needed()
            await element.click(timeout=3000)
            try:
                await page.wait_for_load_state("domcontentloaded", timeout=5000)
            except:
                pass
            await page.wait_for_timeout(600)
            had_effect = (
                self.request_count > initial_request_count or
                page.url != initial_url or
                (await self._get_dom_hash(page)) != (await self._get_dom_hash(page))  # Простая проверка на DOM-изменение
            )
            return True, had_effect
        except Exception as e:
            logger.debug(f"Action execution failed: {e}")
            return False, False

    async def intercept_request(self, route: Route):
        request = route.request
        if self._is_static_resource(request.url) or request.resource_type in ["beacon", "ping"]:
            await route.continue_()
            return
        parsed = urlparse(request.url)
        start_domain = urlparse(self.start_url).netloc
        if parsed.netloc != start_domain:
            await route.continue_()
            return

        result = {
            "request": {
                "method": request.method,
                "endpoint": request.url,
                "headers": dict(request.headers),
                "resource_type": request.resource_type,
            }
        }
        if request.post_data:
            result["request"]["body"] = request.post_data
        key = self._make_request_key(request.method, request.url, request.post_data)
        with self.lock:
            if key not in self.seen_requests:
                self.seen_requests.add(key)
                self.pending_requests[key] = result
                logger.info(f"Captured: {request.method} {parsed.path} {f'[body: {len(request.post_data or '')} bytes]' if request.post_data else ''}")
        await route.continue_()

    # ... (остальные методы intercept, handle_response, _extract_json_keys и т.д. остаются как были)

    async def _replay_state(self, page: Page, start_url: str, target_state: State) -> bool:
        for attempt in range(2):
            try:
                await page.goto(start_url, wait_until="networkidle", timeout=40000)
                await page.wait_for_timeout(1500)

                for action in target_state.path:
                    element = await self._find_element_by_action(page, action)
                    if not element or not await element.is_enabled():
                        logger.warning(f"Replay attempt {attempt+1}: element missing for {action.text[:30]}")
                        break
                    await element.click(timeout=3000)
                    await page.wait_for_load_state("domcontentloaded", timeout=7000)
                    await page.wait_for_timeout(800)

                current_url = urlparse(page.url)
                expected_url = urlparse(target_state.url)
                if f"{current_url.netloc}{current_url.path}" != f"{expected_url.netloc}{expected_url.path}":
                    logger.warning(f"Replay attempt {attempt+1}: URL mismatch")
                    continue

                current_vector = await self._get_dom_vector(page)
                sim = self._dom_similarity(target_state.dom_vector, current_vector)
                if sim < 0.70:
                    logger.warning(f"Replay attempt {attempt+1}: low DOM similarity {sim:.2f}")
                    continue

                return True
            except Exception as e:
                logger.error(f"Replay attempt {attempt+1} failed: {e}")
        return False

    async def _should_skip_state(self, new_state: State) -> bool:
        with self.lock:
            fingerprint = new_state.get_fingerprint()
            if fingerprint in self.visited_states:
                self.states_skipped += 1
                logger.info(f"Exact duplicate: {new_state.url}")
                return True

            semantic = new_state.get_semantic_key()
            similar = [s for s in self.semantic_states if s.startswith(semantic.split(':')[0])]
            if len(similar) >= 5:
                self.states_skipped += 1
                logger.info(f"Too many similar states: {new_state.url}")
                return True

            sequence = ':'.join(a.get_cluster_key() for a in new_state.path)
            if sequence in self.visited_sequences:
                self.states_skipped += 1
                logger.info(f"Duplicate sequence: {sequence}")
                return True

            if new_state.depth > self.max_depth or len(new_state.path) >= self.max_path_length:
                self.states_skipped += 1
                return True

            if len(new_state.actions) < 2 and len(new_state.path) > 1:
                self.states_skipped += 1
                return True

        return False

    async def _explore_state(self, page: Page, state: State):
        logger.info(f"Exploring: {state.url} (depth={state.depth}, actions={len(state.actions)})")
        with self.lock:
            state.visited_count += 1

        await self._fill_and_submit_forms(page)
        try:
            await page.mouse.wheel(0, 4000)
            await page.wait_for_timeout(600)
        except:
            pass

        action_clusters = {}
        for action in state.actions - state.executed_actions - state.dead_actions:
            key = action.get_cluster_key()
            if key not in action_clusters:
                action_clusters[key] = action

        priority = ['submit', 'auth', 'filter', 'data_loader', 'interaction', 'navigation', 'pagination']
        sorted_clusters = sorted(
            action_clusters.items(),
            key=lambda x: priority.index(x[1].semantic) if x[1].semantic in priority else len(priority)
        )

        initial_endpoints = len(state.discovered_endpoints)
        initial_clusters = len(state.executed_clusters)

        for cluster_key, action in sorted_clusters:
            if cluster_key in state.executed_clusters:
                continue

            before_hash, before_vector, before_cookies, before_storage = await self._get_state_fingerprint(page)
            initial_req = self.request_count

            if action.semantic in ['submit', 'auth', 'filter']:
                await self._fill_and_submit_forms(page)

            success, _ = await self._execute_action(page, action)
            if not success:
                continue

            state.executed_actions.add(action)
            state.executed_clusters.add(cluster_key)

            try:
                after_hash, after_vector, after_cookies, after_storage = await self._get_state_fingerprint(page)
                new_url = page.url
            except:
                logger.warning("Fingerprint failed after action")
                break

            changed = (
                self.request_count > initial_req or
                after_hash != before_hash or
                after_cookies != before_cookies or
                after_storage != before_storage or
                new_url != state.url
            )

            if not changed:
                state.dead_actions.add(action)
                logger.info(f"Dead action [{action.semantic}]: {action.text[:30]}")
                continue

            # Параметризация (fuzzing простых GET-параметров)
            parsed = urlparse(new_url)
            if parsed.query and state.depth < self.max_depth:
                params = parse_qs(parsed.query)
                for key in list(params.keys()):
                    if key in ['artist', 'cat', 'id', 'page']:
                        for val in range(1, 6):
                            new_params = params.copy()
                            new_params[key] = [str(val)]
                            new_query = urlencode(new_params, doseq=True)
                            fuzz_url = parsed._replace(query=new_query).geturl()
                            if fuzz_url != new_url:
                                # Создаём фейковое состояние для fuzz
                                fuzz_state = State(
                                    url=fuzz_url,
                                    dom_hash=after_hash,
                                    dom_vector=after_vector,
                                    cookies_hash=after_cookies,
                                    storage_hash=after_storage,
                                    depth=state.depth + 1,
                                    path=state.path + [action],
                                    actions=await self._extract_actions(page)  # приблизительно
                                )
                                if not await self._should_skip_state(fuzz_state):
                                    with self.lock:
                                        self.visited_states.add(fuzz_state.get_fingerprint())
                                        self.semantic_states.add(fuzz_state.get_semantic_key())
                                        self.visited_sequences.add(':'.join(a.get_cluster_key() for a in fuzz_state.path))
                                        self.states_created += 1
                                    t = threading.Thread(target=self._wrapped_explore, args=(fuzz_state,))
                                    t.start()
                                    logger.info(f"Fuzz spawned: {fuzz_url}")

            if state.depth < self.max_depth and len(state.path) < self.max_path_length:
                new_actions = await self._extract_actions(page)
                new_state = State(
                    url=new_url,
                    dom_hash=after_hash,
                    dom_vector=after_vector,
                    cookies_hash=after_cookies,
                    storage_hash=after_storage,
                    depth=state.depth + 1,
                    path=state.path + [action],
                    actions=new_actions
                )

                if await self._should_skip_state(new_state):
                    continue

                with self.lock:
                    self.visited_states.add(new_state.get_fingerprint())
                    self.semantic_states.add(new_state.get_semantic_key())
                    self.visited_sequences.add(':'.join(a.get_cluster_key() for a in new_state.path))
                    self.states_created += 1

                t = threading.Thread(target=self._wrapped_explore, args=(new_state,))
                t.start()
                logger.info(f"Spawned: {new_url} (depth={new_state.depth})")

            new_endpoints_delta = len(state.discovered_endpoints) - initial_endpoints
            new_clusters_delta = len(state.executed_clusters) - initial_clusters

            if state.is_exhausted(new_endpoints_delta == 0, new_clusters_delta == 0):
                logger.info(f"State exhausted: {state.url}")
                break

    def _wrapped_explore(self, state):
        with self.semaphore:
            with self.lock:
                self.active_count += 1
            try:
                self._run_explore(state)
            finally:
                with self.lock:
                    self.active_count -= 1
                    if self.active_count == 0:
                        self.done_event.set()

    def _run_explore(self, state):
        async def inner():
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-dev-shm-usage'])
                context = await browser.new_context(ignore_https_errors=True, user_agent='Mozilla/5.0 ...')
                page = await context.new_page()
                page.on("request", lambda req: logger.debug(f"Request: {req.method} {req.url}"))
                await page.route("**/*", self.intercept_request)
                page.on("response", self.handle_response)

                if state.path:
                    if not await self._replay_state(page, self.start_url, state):
                        logger.warning(f"Replay failed for {state.url}")
                        await browser.close()
                        return
                else:
                    await page.goto(self.start_url, wait_until="networkidle", timeout=40000)
                    await page.wait_for_timeout(2000)

                await self._explore_state(page, state)
                await browser.close()

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(inner())
        finally:
            loop.close()

    async def scan(self):
        logger.info(f"Starting scan: {self.start_url} (max_depth={self.max_depth})")

        # Initial state
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, args=['--no-sandbox'])
            context = await browser.new_context(ignore_https_errors=True)
            page = await context.new_page()
            await page.goto(self.start_url, wait_until="networkidle", timeout=40000)
            await page.wait_for_timeout(2000)

            dom_hash, dom_vector, cookies_hash, storage_hash = await self._get_state_fingerprint(page)
            actions = await self._extract_actions(page)

            initial_state = State(
                url=self.start_url,
                dom_hash=dom_hash,
                dom_vector=dom_vector,
                cookies_hash=cookies_hash,
                storage_hash=storage_hash,
                depth=0,
                path=[],
                actions=actions
            )

            with self.lock:
                self.visited_states.add(initial_state.get_fingerprint())
                self.semantic_states.add(initial_state.get_semantic_key())

            logger.info(f"Initial state: {len(actions)} actions")
            await browser.close()

        # Запуск начального исследования
        t = threading.Thread(target=self._wrapped_explore, args=(initial_state,))
        t.start()
        self.done_event.wait()

        logger.info(f"""
Scan completed:
  Requests: {self.request_count}
  Endpoints: {len(self.unique_endpoints)}
  Methods/Paths: {len(self.unique_methods_paths)}
  JSON Keys: {len(self.unique_json_keys)}
  GraphQL Ops: {len(self.unique_graphql_ops)}
  States Created: {self.states_created}
  States Skipped: {self.states_skipped}
""")

async def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "No URL provided"}), file=sys.stderr)
        sys.exit(1)
    url = sys.argv[1]
    max_depth = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    scanner = PlaywrightScanner(url, max_depth=max_depth)
    await scanner.scan()

if __name__ == "__main__":
    asyncio.run(main())