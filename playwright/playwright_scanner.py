"""
Playwright-based state-aware web crawler with recursive DFS using threads
Improved: form submission, replay reliability, parameter fuzzing, deduplication tuning
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
        level_color = Colors.GREEN if level == 'INFO' else \
                      Colors.YELLOW if level == 'WARNING' else \
                      Colors.RED if level == 'ERROR' else Colors.RESET
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
        action_sig = hash(frozenset(a.get_cluster_key() for a in self.actions))
        dom_str = json.dumps(sorted(self.dom_vector.items()), sort_keys=True)
        dom_hash = hashlib.sha256(dom_str.encode()).hexdigest()[:16]
        return (normalized_url, query_params, self.cookies_hash, self.storage_hash, dom_hash, action_sig)

    def get_semantic_key(self):
        parsed = urlparse(self.url)
        normalized_url = f"{parsed.netloc}{parsed.path}"
        feats = {
            'forms': self.dom_vector.get('forms', 0),
            'buttons': self.dom_vector.get('buttons', 0),
            'links': self.dom_vector.get('links', 0),
        }
        return f"{normalized_url}:{feats['forms']}:{feats['buttons']}:{feats['links']}"

    def is_exhausted(self, no_new_endpoints: bool, no_new_clusters: bool) -> bool:
        return (len(self.executed_actions) >= len(self.actions) or
                self.visited_count >= 3 or
                (no_new_endpoints and no_new_clusters))

class PlaywrightScanner:
    def __init__(self, url: str, max_depth: int = 3, timeout: int = 300,
                 max_actions_per_state: int = 25, max_path_length: int = 15):
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
        self.semaphore = threading.Semaphore(5)  # Ограничение параллелизма

    def _is_static_resource(self, url: str) -> bool:
        lower = url.lower().split('?')[0]
        return any(lower.endswith(ext) for ext in STATIC_EXTENSIONS)

    def _classify_action_semantic(self, text: str, selector: str, tag: str) -> str:
        tl = text.lower()
        sl = selector.lower()
        if any(w in tl for w in ['next', 'prev', 'page', '»', '«', '>', '<']):
            return 'pagination'
        if any(w in tl for w in ['filter', 'sort', 'search', 'apply', 'category', 'tag']):
            return 'filter'
        if any(w in tl for w in ['submit', 'send', 'save', 'post', 'create', 'delete', 'update', 'login', 'sign', 'register']):
            return 'submit'
        if any(w in tl for w in ['login', 'signup', 'logout', 'register']):
            return 'auth'
        if tag == 'a' or 'nav' in sl or 'menu' in sl:
            return 'navigation'
        if any(w in tl for w in ['load', 'more', 'show', 'expand', 'view']):
            return 'data_loader'
        return 'interaction'

    def _make_request_key(self, method: str, url: str, body: str = None) -> str:
        p = urlparse(url)
        path = p.path or '/'
        qkeys = sorted(parse_qs(p.query).keys()) if p.query else []
        qsig = ','.join(qkeys)
        body_schema = ''
        if body:
            try:
                obj = json.loads(body)
                if isinstance(obj, dict):
                    body_schema = ','.join(sorted(obj.keys()))
            except:
                body_schema = str(hash(body))[:8]
        return f"{method}:{path}:{qsig}:{body_schema}"

    async def _get_dom_vector(self, page: Page) -> Dict[str, int]:
        return await page.evaluate("""
            () => {
                const v = {};
                const inc = (k) => { v[k] = (v[k] || 0) + 1; };
                const tags = ['form','input','button','a','select','textarea','nav','header','section','article','main'];
                tags.forEach(t => inc(`tag_${t}` + document.querySelectorAll(t).length));
                inc('forms:' + document.forms.length);
                inc('buttons:' + document.querySelectorAll('button,[role="button"]').length);
                inc('links:' + document.querySelectorAll('a').length);
                inc('inputs:' + document.querySelectorAll('input:not([type="hidden"])').length);
                document.querySelectorAll('button, a').forEach(el => {
                    const t = (el.textContent || '').toLowerCase();
                    if (t.includes('next') || t.includes('prev') || t.includes('page')) inc('pattern_pagination');
                    if (t.includes('search')) inc('pattern_search');
                    if (t.includes('login') || t.includes('sign')) inc('pattern_auth');
                    if (t.includes('submit') || t.includes('save')) inc('pattern_submit');
                });
                return v;
            }
        """)

    async def _get_dom_hash(self, page: Page) -> str:
        v = await self._get_dom_vector(page)
        s = json.dumps(sorted(v.items()), sort_keys=True)
        return hashlib.sha256(s.encode()).hexdigest()[:16]

    def _dom_similarity(self, a: Dict, b: Dict) -> float:
        if not a or not b: return 0.0
        imp = ['forms:', 'buttons:', 'links:', 'inputs:', 'pattern_']
        total_w = sim_sum = 0
        for k in set(a) | set(b):
            w = 2.0 if any(k.startswith(p) for p in imp) else 1.0
            va, vb = a.get(k, 0), b.get(k, 0)
            if va + vb > 0:
                sim = 1 - abs(va - vb) / max(va + vb, 1)
                sim_sum += sim * w
                total_w += w
        return sim_sum / total_w if total_w > 0 else 1.0

    async def _get_state_fingerprint(self, page: Page):
        cookies = await page.context.cookies()
        ch = hashlib.sha256(json.dumps(cookies, sort_keys=True, default=str).encode()).hexdigest()[:16]
        storage = await page.evaluate("() => JSON.stringify({localStorage: {...localStorage}, sessionStorage: {...sessionStorage}})")
        sh = hashlib.sha256(storage.encode()).hexdigest()[:16]
        dv = await self._get_dom_vector(page)
        dh = hashlib.sha256(json.dumps(sorted(dv.items()), sort_keys=True).encode()).hexdigest()[:16]
        return dh, dv, ch, sh

    async def _extract_actions(self, page: Page) -> Set[Action]:
        actions = set()
        sel = "a, button, input[type=submit], input[type=button], [role=button], [onclick], [role=link]"
        els = await page.query_selector_all(sel)
        for el in els[:self.max_actions_per_state]:
            try:
                if not await el.is_visible() or not await el.is_enabled():
                    continue
                text = (await el.text_content() or "").strip()[:50]
                tag = await el.evaluate("el => el.tagName.toLowerCase()")
                selector = await self._generate_selector(el)
                sem = self._classify_action_semantic(text, selector, tag)
                if selector:
                    actions.add(Action(selector=selector, text=text, tag=tag, semantic=sem))
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
                        const txt = (el.textContent || '').trim().slice(0,30);
                        if (txt) return `[role="${el.getAttribute("role")}"][text*="${txt}"]`;
                    }
                    let path = [];
                    let cur = el;
                    while (cur.parentElement && path.length < 5) {
                        let tag = cur.tagName.toLowerCase();
                        let sibs = [...cur.parentElement.children].filter(e => e.tagName === cur.tagName);
                        if (sibs.length > 1) {
                            let idx = sibs.indexOf(cur) + 1;
                            tag += `:nth-of-type(${idx})`;
                        }
                        path.unshift(tag);
                        cur = cur.parentElement;
                    }
                    return path.join(' > ');
                }
            """)
        except:
            return ""

    async def _fill_and_submit_forms(self, page: Page):
        try:
            await page.evaluate("""
                () => {
                    document.querySelectorAll('form').forEach(form => {
                        form.querySelectorAll('input, textarea, select').forEach(el => {
                            if (el.type === 'hidden') return;
                            if (['checkbox','radio'].includes(el.type)) el.checked = true;
                            else if (el.tagName === 'SELECT' && el.options.length) el.selectedIndex = Math.floor(Math.random() * el.options.length);
                            else if (el.type === 'email' || el.type === 'text') el.value = 'test' + Math.random().toString(36).substring(2,10) + '@example.com';
                            else if (el.type === 'password') el.value = 'TestPass123!';
                            else if (el.type === 'number') el.value = '42';
                            else el.value = 'test value';
                            el.dispatchEvent(new Event('input', {bubbles:true}));
                            el.dispatchEvent(new Event('change', {bubbles:true}));
                        });
                        const btn = form.querySelector('input[type=submit], button[type=submit], button');
                        if (btn) btn.click();
                        else form.submit();
                    });
                }
            """)
            await page.wait_for_timeout(1000)
        except Exception as e:
            logger.warning(f"Form fill/submit error: {e}")

    async def _execute_action(self, page: Page, action: Action) -> tuple[bool, bool]:
        try:
            el = await page.query_selector(action.selector)
            if not el or not await el.is_visible() or not await el.is_enabled():
                return False, False
            init_req = self.request_count
            init_url = page.url
            await el.scroll_into_view_if_needed()
            await el.click(timeout=3000)
            try: await page.wait_for_load_state("domcontentloaded", timeout=6000)
            except: pass
            await page.wait_for_timeout(700)
            effect = (
                self.request_count > init_req or
                page.url != init_url or
                True  # conservative: assume JS could have changed something
            )
            return True, effect
        except Exception as e:
            logger.debug(f"Execute failed: {e}")
            return False, False

    async def intercept_request(self, route: Route):
        req = route.request
        if self._is_static_resource(req.url) or req.resource_type in ["beacon", "ping"]:
            await route.continue_()
            return
        p = urlparse(req.url)
        if p.netloc != urlparse(self.start_url).netloc:
            await route.continue_()
            return
        data = {
            "request": {
                "method": req.method,
                "endpoint": req.url,
                "headers": dict(req.headers),
                "resource_type": req.resource_type,
            }
        }
        if req.post_data:
            data["request"]["body"] = req.post_data
        key = self._make_request_key(req.method, req.url, req.post_data)
        with self.lock:
            if key not in self.seen_requests:
                self.seen_requests.add(key)
                self.pending_requests[key] = data
                logger.info(f"Captured: {req.method} {p.path} {'[body]' if req.post_data else ''}")
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

    def _extract_graphql_operation(self, data: str, ct: str, url: str) -> str | None:
        if "graphql" in url.lower() or "application/graphql" in ct.lower():
            return "graphql_raw"
        if "application/json" not in ct.lower():
            return None
        try:
            obj = json.loads(data)
            if isinstance(obj, list) and any("query" in i or "mutation" in i for i in obj if isinstance(i, dict)):
                return "graphql_batch"
            if isinstance(obj, dict):
                if "query" in obj or "mutation" in obj:
                    return obj.get("operationName", "anonymous")
                if "id" in obj and "variables" in obj:
                    return "graphql_persisted"
        except:
            pass
        return None

    async def handle_response(self, response: Response):
        req = response.request
        key = self._make_request_key(req.method, req.url, req.post_data)
        result = None
        with self.lock:
            if key in self.pending_requests:
                result = self.pending_requests.pop(key)
        if result:
            result["response"] = {"status_code": response.status, "headers": dict(response.headers)}
            result["timestamp"] = asyncio.get_event_loop().time()
            parsed = urlparse(req.url)
            endpoint = f"{req.method} {parsed.path}"
            new_keys_req = self._extract_json_keys(req.post_data or "")
            graphql_op = self._extract_graphql_operation(req.post_data or "", req.headers.get("content-type", ""), req.url)
            new_keys_resp = set()
            try:
                body = await response.text()
                new_keys_resp = self._extract_json_keys(body)
            except:
                pass
            with self.lock:
                self.results.append(result)
                self.request_count += 1
                self.unique_endpoints.add(req.url)
                self.unique_methods_paths.add(endpoint)
                self.unique_json_keys.update(new_keys_req | new_keys_resp)
                if graphql_op:
                    self.unique_graphql_ops.add(graphql_op)
            logger.info(f"Found: {req.method} {req.url} -> {response.status}")
            print(json.dumps(result), flush=True)

    async def _find_element_by_action(self, page: Page, action: Action) -> ElementHandle | None:
        el = await page.query_selector(action.selector)
        if el and await el.is_visible():
            return el
        if action.text:
            els = await page.query_selector_all(action.tag)
            for e in els:
                txt = (await e.text_content() or "").strip()
                if txt == action.text and await e.is_visible():
                    return e
        return None

    async def _replay_state(self, page: Page, start_url: str, target: State) -> bool:
        for attempt in range(2):
            try:
                await page.goto(start_url, wait_until="networkidle", timeout=45000)
                await page.wait_for_timeout(1500)
                for act in target.path:
                    el = await self._find_element_by_action(page, act)
                    if not el or not await el.is_enabled():
                        logger.warning(f"Replay attempt {attempt+1}: no element for {act.text[:30]}")
                        break
                    await el.click(timeout=3500)
                    try: await page.wait_for_load_state("domcontentloaded", timeout=8000)
                    except: pass
                    await page.wait_for_timeout(900)
                cu = urlparse(page.url)
                eu = urlparse(target.url)
                if f"{cu.netloc}{cu.path}" != f"{eu.netloc}{eu.path}":
                    logger.warning(f"Replay attempt {attempt+1}: URL mismatch")
                    continue
                cv = await self._get_dom_vector(page)
                sim = self._dom_similarity(target.dom_vector, cv)
                if sim < 0.70:
                    logger.warning(f"Replay attempt {attempt+1}: similarity {sim:.2f} < 0.70")
                    continue
                return True
            except Exception as e:
                logger.error(f"Replay attempt {attempt+1} error: {e}")
        return False

    async def _should_skip_state(self, new_state: State) -> bool:
        with self.lock:
            fp = new_state.get_fingerprint()
            if fp in self.visited_states:
                self.states_skipped += 1
                logger.info(f"Exact duplicate: {new_state.url}")
                return True

            sk = new_state.get_semantic_key()
            similar = [s for s in self.semantic_states if s.startswith(sk.split(':')[0])]
            if len(similar) >= 5:
                self.states_skipped += 1
                logger.info(f"Too similar ({len(similar)}): {new_state.url}")
                return True

            seq = ':'.join(a.get_cluster_key() for a in new_state.path)
            if seq in self.visited_sequences:
                self.states_skipped += 1
                logger.info(f"Duplicate sequence: {seq}")
                return True

            if new_state.depth > self.max_depth or len(new_state.path) >= self.max_path_length:
                self.states_skipped += 1
                logger.info(f"Depth/path limit: {new_state.url}")
                return True

            if len(new_state.actions) < 2 and len(new_state.path) > 1:
                self.states_skipped += 1
                logger.info(f"Too few actions: {new_state.url}")
                return True
        return False

    async def _explore_state(self, page: Page, state: State):
        logger.info(f"Exploring {state.url} (depth={state.depth}, actions={len(state.actions)})")
        with self.lock:
            state.visited_count += 1

        await self._fill_and_submit_forms(page)

        try:
            await page.mouse.wheel(0, 5000)
            await page.wait_for_timeout(700)
        except:
            pass

        clusters = {}
        for a in state.actions - state.executed_actions - state.dead_actions:
            k = a.get_cluster_key()
            if k not in clusters:
                clusters[k] = a

        prio = ['submit', 'auth', 'filter', 'data_loader', 'interaction', 'navigation', 'pagination']
        sorted_c = sorted(clusters.items(), key=lambda x: prio.index(x[1].semantic) if x[1].semantic in prio else 999)

        init_eps = len(state.discovered_endpoints)
        init_cls = len(state.executed_clusters)

        for ck, action in sorted_c:
            if ck in state.executed_clusters:
                continue

            bh, bv, bc, bs = await self._get_state_fingerprint(page)
            ireq = self.request_count

            if action.semantic in ['submit', 'auth', 'filter', 'interaction']:
                await self._fill_and_submit_forms(page)

            ok, _ = await self._execute_action(page, action)
            if not ok:
                continue

            state.executed_actions.add(action)
            state.executed_clusters.add(ck)

            try:
                ah, av, ac, as_ = await self._get_state_fingerprint(page)
                nu = page.url
            except:
                logger.warning("Fingerprint after action failed")
                break

            changed = (
                self.request_count > ireq or
                ah != bh or ac != bc or as_ != bs or
                nu != state.url
            )

            if not changed:
                state.dead_actions.add(action)
                logger.info(f"Dead [{action.semantic}]: {action.text[:30]}")
                continue

            state.discovered_endpoints.add(nu)

            # Простой fuzz параметров
            pu = urlparse(nu)
            if pu.query and state.depth < self.max_depth:
                ps = parse_qs(pu.query)
                for k in list(ps):
                    if k.lower() in ['artist', 'cat', 'id', 'page', 'item']:
                        for v in range(1, 6):
                            nps = ps.copy()
                            nps[k] = [str(v)]
                            nq = urlencode(nps, doseq=True)
                            fu = pu._replace(query=nq).geturl()
                            if fu != nu:
                                fs = State(
                                    url=fu,
                                    dom_hash=ah,
                                    dom_vector=av,
                                    cookies_hash=ac,
                                    storage_hash=as_,
                                    depth=state.depth + 1,
                                    path=state.path + [action],
                                    actions=await self._extract_actions(page)
                                )
                                if not await self._should_skip_state(fs):
                                    with self.lock:
                                        self.visited_states.add(fs.get_fingerprint())
                                        self.semantic_states.add(fs.get_semantic_key())
                                        self.visited_sequences.add(':'.join(a.get_cluster_key() for a in fs.path))
                                        self.states_created += 1
                                    threading.Thread(target=self._wrapped_explore, args=(fs,)).start()
                                    logger.info(f"Fuzz param {k}={v}: {fu}")

            if state.depth < self.max_depth and len(state.path) < self.max_path_length:
                na = await self._extract_actions(page)
                ns = State(
                    url=nu,
                    dom_hash=ah,
                    dom_vector=av,
                    cookies_hash=ac,
                    storage_hash=as_,
                    depth=state.depth + 1,
                    path=state.path + [action],
                    actions=na
                )

                if await self._should_skip_state(ns):
                    continue

                with self.lock:
                    self.visited_states.add(ns.get_fingerprint())
                    self.semantic_states.add(ns.get_semantic_key())
                    self.visited_sequences.add(':'.join(a.get_cluster_key() for a in ns.path))
                    self.states_created += 1

                threading.Thread(target=self._wrapped_explore, args=(ns,)).start()
                logger.info(f"New state: {nu} (depth={ns.depth}, actions={len(na)})")

            delta_eps = len(state.discovered_endpoints) - init_eps
            delta_cls = len(state.executed_clusters) - init_cls

            if state.is_exhausted(delta_eps == 0, delta_cls == 0):
                logger.info(f"Exhausted after {state.visited_count} visits: {state.url}")
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
                br = await p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu'])
                ctx = await br.new_context(ignore_https_errors=True,
                                           user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
                pg = await ctx.new_page()
                await pg.route("**/*", self.intercept_request)
                pg.on("response", self.handle_response)
                pg.on("console", lambda m: logger.info(f"Console: {m.text}"))

                if state.path:
                    if not await self._replay_state(pg, self.start_url, state):
                        logger.warning(f"Replay failed → skip {state.url}")
                        await br.close()
                        return
                else:
                    await pg.goto(self.start_url, wait_until="networkidle", timeout=45000)
                    await pg.wait_for_timeout(2500)

                await self._explore_state(pg, state)
                await br.close()

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(inner())
        except Exception as e:
            logger.error(f"Thread crash: {e}")
        finally:
            loop.close()

    async def scan(self):
        logger.info(f"Scan start: {self.start_url} depth={self.max_depth}")

        async with async_playwright() as p:
            br = await p.chromium.launch(headless=True, args=['--no-sandbox'])
            ctx = await br.new_context(ignore_https_errors=True)
            pg = await ctx.new_page()
            await pg.goto(self.start_url, wait_until="networkidle", timeout=45000)
            await pg.wait_for_timeout(2500)

            dh, dv, ch, sh = await self._get_state_fingerprint(pg)
            acts = await self._extract_actions(pg)

            init = State(
                url=self.start_url,
                dom_hash=dh,
                dom_vector=dv,
                cookies_hash=ch,
                storage_hash=sh,
                depth=0,
                path=[],
                actions=acts
            )

            with self.lock:
                self.visited_states.add(init.get_fingerprint())
                self.semantic_states.add(init.get_semantic_key())

            logger.info(f"Initial actions: {len(acts)}")
            await br.close()

        threading.Thread(target=self._wrapped_explore, args=(init,)).start()
        self.done_event.wait()

        logger.info(f"""
Scan finished:
  Requests .......... {self.request_count}
  Unique endpoints .. {len(self.unique_endpoints)}
  Methods/Paths ..... {len(self.unique_methods_paths)}
  JSON keys ......... {len(self.unique_json_keys)}
  GraphQL ops ....... {len(self.unique_graphql_ops)}
  States created .... {self.states_created}
  States skipped .... {self.states_skipped}
""")

async def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "URL required"}), file=sys.stderr)
        sys.exit(1)
    url = sys.argv[1]
    depth = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    s = PlaywrightScanner(url, max_depth=depth)
    await s.scan()

if __name__ == "__main__":
    asyncio.run(main())