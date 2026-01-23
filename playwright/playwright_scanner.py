"""
Playwright-based state-aware web crawler with recursive exploration
Tracks DOM states to avoid infinite loops and maximize coverage
"""
import asyncio
import json
import logging
import sys
import hashlib
from typing import Set, Dict, Any, List, Tuple
from urllib.parse import urlparse, parse_qs
from dataclasses import dataclass, field


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
        norm_url = f"{parsed.netloc}{parsed.path.rstrip('/')}"
        query_keys = frozenset(parse_qs(parsed.query).keys())
        action_sig = hash(frozenset(a.get_cluster_key() for a in self.actions))
        dom_str = json.dumps(sorted(self.dom_vector.items()), sort_keys=True)
        dom_h = hashlib.sha256(dom_str.encode()).hexdigest()[:16]
        return (norm_url, query_keys, self.cookies_hash, self.storage_hash, dom_h, action_sig)

    def get_semantic_key(self):
        parsed = urlparse(self.url)
        norm_url = f"{parsed.netloc}{parsed.path.rstrip('/')}"
        feats = {
            'forms': self.dom_vector.get('forms', 0),
            'buttons': self.dom_vector.get('buttons', 0),
            'links': self.dom_vector.get('links', 0),
        }
        return f"{norm_url}:{feats['forms']}:{feats['buttons']}:{feats['links']}"

    def is_exhausted(self, no_new_endpoints: bool, no_new_clusters: bool) -> bool:
        all_done = len(self.executed_actions) >= len(self.actions)
        too_many_visits = self.visited_count >= 4
        return all_done or (no_new_endpoints and no_new_clusters) or too_many_visits


class PlaywrightScanner:
    def __init__(self, url: str, max_depth: int = 3, max_actions_per_state: int = 35, max_path_length: int = 12):
        self.start_url = url
        self.max_depth = max_depth
        self.max_actions_per_state = max_actions_per_state
        self.max_path_length = max_path_length

        self.results: list[Dict[str, Any]] = []
        self.pending_requests: Dict[str, Dict] = {}
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

    def _is_static_resource(self, url: str) -> bool:
        lower = url.lower().split('?')[0]
        return any(lower.endswith(ext) for ext in STATIC_EXTENSIONS)

    def _classify_action_semantic(self, text: str, selector: str, tag: str) -> str:
        t = text.lower()
        s = selector.lower()
        if any(k in t for k in ['next', 'prev', 'page', '»', '«', '>', '<']): return 'pagination'
        if any(k in t for k in ['filter', 'sort', 'search', 'apply']): return 'filter'
        if any(k in t for k in ['submit', 'send', 'save', 'post', 'create']): return 'submit'
        if any(k in t for k in ['login', 'signup', 'logout', 'register']): return 'auth'
        if tag == 'a' or 'nav' in s or 'menu' in s: return 'navigation'
        if any(k in t for k in ['load', 'more', 'show', 'expand']): return 'data_loader'
        return 'interaction'

    def _make_request_key(self, method: str, url: str, body: str = None) -> str:
        p = urlparse(url)
        path = p.path or '/'
        qkeys = ','.join(sorted(parse_qs(p.query).keys()))
        body_schema = ''
        if body:
            try:
                obj = json.loads(body)
                if isinstance(obj, dict):
                    body_schema = ','.join(sorted(obj.keys()))
            except:
                body_schema = str(hash(body))[:8]
        return f"{method}:{path}:{qkeys}:{body_schema}"

    async def _get_dom_vector(self, page: Page) -> Dict[str, int]:
        return await page.evaluate("""
            () => {
                const v = {};
                const inc = (k) => { v[k] = (v[k] || 0) + 1; };
                ['form','input','button','a','select','textarea','nav'].forEach(t => {
                    inc('tag_'+t + ':' + document.querySelectorAll(t).length);
                });
                inc('forms:' + document.forms.length);
                inc('buttons:' + document.querySelectorAll('button,[role="button"]').length);
                inc('links:' + document.querySelectorAll('a[href]').length);
                inc('inputs:' + document.querySelectorAll('input:not([type="hidden"])').length);
                return v;
            }
        """)

    async def _get_state_fingerprint(self, page: Page):
        cookies = await page.context.cookies()
        ck_hash = hashlib.sha256(json.dumps(cookies, sort_keys=True, default=str).encode()).hexdigest()[:16]

        storage = await page.evaluate("() => JSON.stringify({local: localStorage, session: sessionStorage})")
        st_hash = hashlib.sha256(storage.encode()).hexdigest()[:16]

        vec = await self._get_dom_vector(page)
        dom_h = hashlib.sha256(json.dumps(sorted(vec.items()), sort_keys=True).encode()).hexdigest()[:16]

        return dom_h, vec, ck_hash, st_hash

    async def _extract_actions(self, page: Page) -> Set[Action]:
        actions = set()
        els = await page.query_selector_all("a, button, [role=button], input[type=submit]")
        for el in els[:self.max_actions_per_state]:
            try:
                if not await el.is_visible() or not await el.is_enabled():
                    continue
                text = (await el.text_content() or "").strip()[:50]
                tag = await el.evaluate("el => el.tagName.toLowerCase()")
                selector = await self._generate_selector(el)
                if selector:
                    sem = self._classify_action_semantic(text, selector, tag)
                    actions.add(Action(selector, text, tag, semantic=sem))
            except:
                pass
        return actions

    async def _generate_selector(self, el: ElementHandle) -> str:
        try:
            return await el.evaluate("""
                el => {
                    if (el.dataset.testid) return `[data-testid="${el.dataset.testid}"]`;
                    if (el.id) return '#' + el.id;
                    if (el.getAttribute('aria-label')) return `[aria-label="${el.getAttribute('aria-label')}"]`;
                    let p = [], cur = el;
                    while (cur && p.length < 4) {
                        let tag = cur.tagName.toLowerCase();
                        let sibs = [...cur.parentElement.children].filter(c => c.tagName === cur.tagName);
                        if (sibs.length > 1) tag += `:nth-of-type(${sibs.indexOf(cur)+1})`;
                        p.unshift(tag);
                        cur = cur.parentElement;
                    }
                    return p.join(' > ');
                }
            """)
        except:
            return ""

    async def _fill_forms(self, page: Page):
        await page.evaluate("""
            () => {
                document.querySelectorAll('input:not([type=hidden]), textarea, select').forEach(el => {
                    if (el.type === 'checkbox' || el.type === 'radio') el.checked = true;
                    else if (el.tagName === 'SELECT' && el.options.length) el.selectedIndex = Math.floor(Math.random()*el.options.length);
                    else if (el.type === 'email') el.value = 'test'+Date.now()+'@example.com';
                    else if (el.type === 'password') el.value = 'TestPass123!';
                    else if (el.type === 'number') el.value = '42';
                    else el.value = 'test';
                    ['input','change'].forEach(ev => el.dispatchEvent(new Event(ev, {bubbles:true})));
                });
            }
        """)

    async def _execute_action(self, page: Page, action: Action) -> tuple[bool, bool]:
        try:
            el = await page.query_selector(action.selector)
            if not el or not await el.is_visible() or not await el.is_enabled():
                return False, False

            init_req = self.request_count
            await el.scroll_into_view_if_needed()
            await el.click(timeout=1200)
            try:
                await page.wait_for_load_state("domcontentloaded", timeout=4000)
            except:
                pass
            await page.wait_for_timeout(300)
            return True, self.request_count > init_req
        except:
            return False, False

    async def intercept_request(self, route: Route):
        req = route.request
        if self._is_static_resource(req.url) or req.resource_type in ["beacon", "ping", "image", "stylesheet", "font"]:
            return await route.continue_()

        parsed = urlparse(req.url)
        if parsed.netloc != urlparse(self.start_url).netloc:
            return await route.continue_()

        key = self._make_request_key(req.method, req.url, req.post_data)
        if key not in self.seen_requests:
            self.seen_requests.add(key)
            self.pending_requests[key] = {
                "request": {
                    "method": req.method,
                    "url": req.url,
                    "path": parsed.path or "/",
                    "post_data": req.post_data
                }
            }
            logger.info(f"Captured {req.method} {parsed.path}")

        await route.continue_()

    async def handle_response(self, response: Response):
        req = response.request
        key = self._make_request_key(req.method, req.url, req.post_data)
        if key not in self.pending_requests:
            return

        data = self.pending_requests.pop(key)
        data["response"] = {"status": response.status, "url": response.url}
        self.results.append(data)
        self.request_count += 1

        parsed = urlparse(req.url)
        self.unique_endpoints.add(req.url)
        self.unique_methods_paths.add(f"{req.method} {parsed.path}")

        if req.post_data:
            try:
                obj = json.loads(req.post_data)
                if isinstance(obj, dict):
                    self.unique_json_keys.update(obj.keys())
            except:
                pass

        try:
            body = await response.text()
            try:
                obj = json.loads(body)
                if isinstance(obj, dict):
                    self.unique_json_keys.update(obj.keys())
            except:
                pass
        except:
            pass

        logger.info(f"Found: {req.method} {req.url} → {response.status}")

    async def _replay_state(self, page: Page, start_url: str, target: State) -> bool:
        try:
            current_url = page.url
            target_url = target.url

            # Мягкое сравнение URL
            c = urlparse(current_url)
            t = urlparse(target_url)
            if c.netloc + c.path.rstrip('/') != t.netloc + t.path.rstrip('/'):
                logger.info(f"URL path differs, replaying sequence anyway: {current_url} → {target_url}")
                # продолжаем, не выходим

            await page.goto(start_url, wait_until="domcontentloaded", timeout=35000)
            await page.wait_for_timeout(800)

            for act in target.path:
                el = await self._find_element_by_action(page, act)
                if not el:
                    logger.warning(f"Replay: element not found → {act.text[:40]}")
                    continue
                await el.click(timeout=1500)
                try:
                    await page.wait_for_load_state("domcontentloaded", timeout=6000)
                except:
                    pass
                await page.wait_for_timeout(400)

            # Проверяем похожесть DOM — но мягко
            vec = await self._get_dom_vector(page)
            sim = self._dom_similarity(target.dom_vector, vec)
            if sim < 0.65:
                logger.warning(f"DOM similarity low after replay: {sim:.2f} (but continuing)")
                # НЕ return False

            logger.info(f"Replay completed → current URL: {page.url}")
            return True

        except Exception as e:
            logger.error(f"Replay failed: {e}")
            # Пробуем fallback — просто идём на target.url
            try:
                await page.goto(target.url, wait_until="domcontentloaded", timeout=30000)
                logger.info("Fallback goto target URL succeeded")
                return True
            except:
                return False

    async def _find_element_by_action(self, page: Page, action: Action) -> ElementHandle | None:
        el = await page.query_selector(action.selector)
        if el and await el.is_visible():
            return el
        if action.text:
            candidates = await page.query_selector_all(action.tag)
            for c in candidates:
                txt = (await c.text_content() or "").strip()
                if txt == action.text and await c.is_visible():
                    return c
        return None

    async def _should_skip_state(self, state: State) -> bool:
        fp = state.get_fingerprint()
        if fp in self.visited_states:
            self.states_skipped += 1
            logger.info(f"Exact duplicate skipped: {state.url}")
            return True

        sem = state.get_semantic_key()
        if sem in self.semantic_states:
            # считаем похожие
            prefix = sem.split(':', 1)[0]
            count = sum(1 for s in self.semantic_states if s.startswith(prefix))
            if count >= 4:
                self.states_skipped += 1
                logger.info(f"Too many similar states: {state.url}")
                return True

        seq = ':'.join(a.get_cluster_key() for a in state.path)
        if seq in self.visited_sequences:
            self.states_skipped += 1
            logger.info(f"Duplicate sequence: {seq[:80]}...")
            return True

        if state.depth > self.max_depth or len(state.path) >= self.max_path_length:
            self.states_skipped += 1
            return True

        if len(state.actions) < 2 and len(state.path) > 2:
            self.states_skipped += 1
            return True

        self.visited_states.add(fp)
        self.semantic_states.add(sem)
        self.visited_sequences.add(seq)
        return False

    async def _explore_state(self, page: Page, state: State):
        logger.info(f"→ Exploring {state.url} (depth={state.depth}, actions={len(state.actions)}, exec={len(state.executed_clusters)})")

        state.visited_count += 1
        await self._fill_forms(page)
        await page.wait_for_timeout(400)

        clusters = {}
        for a in state.actions:
            if a not in state.executed_actions and a not in state.dead_actions:
                ck = a.get_cluster_key()
                if ck not in clusters:
                    clusters[ck] = a

        if not clusters:
            logger.info("No new clusters to explore")
            return

        # Приоритет: submit/auth → filter → data → interaction → nav/pag
        prio = ['submit', 'auth', 'filter', 'data_loader', 'interaction', 'navigation', 'pagination']
        sorted_clusters = sorted(
            clusters.items(),
            key=lambda x: prio.index(x[1].semantic) if x[1].semantic in prio else 999
        )

        initial_endpoints = len(state.discovered_endpoints)
        initial_clusters = len(state.executed_clusters)

        for ck, action in sorted_clusters:
            if ck in state.executed_clusters:
                continue

            logger.info(f"  Trying action [{action.semantic}] '{action.text[:35]}'")

            before_req = self.request_count
            before_url = page.url

            if action.semantic in ['submit', 'auth', 'filter']:
                await self._fill_forms(page)

            success, _ = await self._execute_action(page, action)

            if not success:
                logger.info(f"  → action failed to execute")
                continue

            state.executed_actions.add(action)
            state.executed_clusters.add(ck)

            after_url = page.url
            delta_req = self.request_count - before_req

            new_dom_h, new_vec, new_ck, new_st = await self._get_state_fingerprint(page)
            changed = (
                new_dom_h != state.dom_hash or
                new_ck != state.cookies_hash or
                new_st != state.storage_hash or
                delta_req > 0
            )

            if not changed:
                state.dead_actions.add(action)
                logger.info(f"  → dead action (no change)")
                continue

            logger.info(f"  → had effect (req Δ{delta_req}, url: {before_url[:60]} → {after_url[:60]})")

            state.discovered_endpoints.add(after_url)

            if state.depth < self.max_depth and len(state.path) < self.max_path_length:
                new_state = State(
                    url=after_url,
                    dom_hash=new_dom_h,
                    dom_vector=new_vec,
                    cookies_hash=new_ck,
                    storage_hash=new_st,
                    depth=state.depth + 1,
                    path=state.path + [action],
                    actions=await self._extract_actions(page)
                )

                if await self._should_skip_state(new_state):
                    continue

                self.states_created += 1
                logger.info(f"  New child state #{self.states_created} → {new_state.url} (depth={new_state.depth})")

                # Рекурсия
                await self._explore_state(page, new_state)

                # Пытаемся вернуться
                replay_ok = await self._replay_state(page, self.start_url, state)
                if not replay_ok:
                    logger.warning("Replay after child failed → falling back to continue from current page")

            # Проверяем, исчерпано ли текущее состояние
            new_ep = len(state.discovered_endpoints) - initial_endpoints
            new_cl = len(state.executed_clusters) - initial_clusters
            if state.is_exhausted(new_ep == 0, new_cl == 0):
                logger.info(f"State exhausted (visits={state.visited_count})")
                break

    async def scan(self):
        logger.info(f"Starting recursive scan: {self.start_url} (max_depth={self.max_depth})")

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-dev-shm-usage'])
            context = await browser.new_context(ignore_https_errors=True, user_agent="Mozilla/5.0 ...")
            page = await context.new_page()

            await page.route("**/*", self.intercept_request)
            page.on("response", self.handle_response)

            await page.goto(self.start_url, wait_until="networkidle", timeout=40000)
            await page.wait_for_timeout(1500)

            dom_h, vec, ck_h, st_h = await self._get_state_fingerprint(page)
            init_actions = await self._extract_actions(page)

            root = State(
                url=self.start_url,
                dom_hash=dom_h,
                dom_vector=vec,
                cookies_hash=ck_h,
                storage_hash=st_h,
                depth=0,
                actions=init_actions
            )

            self.visited_states.add(root.get_fingerprint())
            self.semantic_states.add(root.get_semantic_key())

            logger.info(f"Initial state: {len(init_actions)} actions")

            await self._explore_state(page, root)

            await browser.close()

        logger.info(f"""
Scan finished:
  Requests captured : {self.request_count}
  Unique endpoints  : {len(self.unique_endpoints)}
  Unique paths      : {len(self.unique_methods_paths)}
  JSON keys         : {len(self.unique_json_keys)}
  States created    : {self.states_created}
  States skipped    : {self.states_skipped}
""")


async def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Usage: python script.py <url> [max_depth]"}), file=sys.stderr)
        sys.exit(1)

    url = sys.argv[1]
    depth = int(sys.argv[2]) if len(sys.argv) > 2 else 3

    scanner = PlaywrightScanner(url, max_depth=depth)
    await scanner.scan()


if __name__ == "__main__":
    asyncio.run(main())