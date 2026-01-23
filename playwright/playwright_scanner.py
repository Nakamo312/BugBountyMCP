"""
Playwright-based state-aware web crawler with BFS exploration
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
    event_type: str = "click"
    semantic: str = "unknown"

    def __hash__(self):
        return hash((self.semantic, self.tag, self.text[:30].lower()))

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
    visited_count: int = 0  # Счётчик посещений этого состояния

    def get_fingerprint(self):
        """Strict fingerprint for exact state matching"""
        parsed = urlparse(self.url)
        normalized_url = f"{parsed.netloc}{parsed.path}"
        query_keys = frozenset(parse_qs(parsed.query).keys()) if parsed.query else frozenset()
        
        # Включаем хэш действий и DOM структуры
        action_signature = hash(frozenset(a.get_cluster_key() for a in self.actions))
        dom_vector_str = json.dumps(sorted(self.dom_vector.items()), sort_keys=True)
        dom_hash = hashlib.sha256(dom_vector_str.encode()).hexdigest()[:16]
        
        return (normalized_url, query_keys, self.cookies_hash, self.storage_hash, 
                dom_hash, action_signature)

    def get_semantic_key(self):
        """Semantic key for fuzzy matching - только по URL и основным фичам"""
        parsed = urlparse(self.url)
        normalized_url = f"{parsed.netloc}{parsed.path}"
        
        # Основные фичи DOM
        key_features = {
            'forms': self.dom_vector.get('forms', 0),
            'buttons': self.dom_vector.get('buttons', 0),
            'links': self.dom_vector.get('links', 0),
        }
        
        return f"{normalized_url}:{key_features['forms']}:{key_features['buttons']}:{key_features['links']}"

    def is_exhausted(self, no_new_endpoints: bool, no_new_clusters: bool) -> bool:
        """Check if state exploration is exhausted"""
        all_executed = len(self.executed_actions) >= len(self.actions)
        visited_too_much = self.visited_count >= 3  # Не посещаем одно состояние больше 3 раз
        return all_executed or (no_new_endpoints and no_new_clusters) or visited_too_much


class PlaywrightScanner:
    def __init__(self, url: str, max_depth: int = 2, timeout: int = 300, max_actions_per_state: int = 20, max_path_length: int = 10):
        self.start_url = url
        self.max_depth = max_depth
        self.timeout = timeout
        self.max_actions_per_state = max_actions_per_state
        self.max_path_length = max_path_length
        
        self.state_queue: deque[State] = deque()
        self.results: list[Dict[str, Any]] = []
        self.pending_requests: Dict[str, Dict[str, Any]] = {}
        self.seen_requests: Set[str] = set()
        
        # Три уровня дедупликации:
        # 1. Точные фингерпринты (visited_states)
        # 2. Семантические ключи (semantic_states)
        # 3. Посещённые последовательности действий (visited_sequences)
        self.visited_states: Set[Tuple] = set()
        self.semantic_states: Set[str] = set()
        self.visited_sequences: Set[str] = set()
        
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
        
        # Счётчики для отладки
        self.states_created = 0
        self.states_skipped = 0

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

    async def _get_dom_vector(self, page: Page) -> Dict[str, int]:
        """Get semantic DOM feature vector"""
        return await page.evaluate("""
            () => {
                const v = {};
                const inc = k => v[k] = (v[k] || 0) + 1;

                // Count only important tags
                const importantTags = ['form', 'input', 'button', 'a', 'select', 'textarea', 'nav', 'header', 'section', 'article', 'main'];
                importantTags.forEach(tag => {
                    inc(`tag_${tag}` + document.querySelectorAll(tag).length);
                });
                
                // Count interactive elements
                inc('forms:' + document.forms.length);
                inc('buttons:' + document.querySelectorAll('button,[role="button"]').length);
                inc('links:' + document.querySelectorAll('a').length);
                inc('inputs:' + document.querySelectorAll('input:not([type="hidden"])').length);
                
                // Count semantic patterns
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
        """Get semantic DOM fingerprint ignoring dynamic content"""
        vector = await self._get_dom_vector(page)
        vector_str = json.dumps(sorted(vector.items()), sort_keys=True)
        return hashlib.sha256(vector_str.encode()).hexdigest()[:16]

    def _dom_similarity(self, a: Dict[str, int], b: Dict[str, int]) -> float:
        """Calculate weighted similarity between DOM feature vectors"""
        if not a or not b:
            return 0.0
        
        # Важные фичи получают больший вес
        important_features = ['forms:', 'buttons:', 'links:', 'inputs:', 'pattern_']
        
        total_weight = 0
        similarity_sum = 0
        
        for key in set(a.keys()) | set(b.keys()):
            # Определяем вес фичи
            weight = 2.0 if any(key.startswith(p) for p in important_features) else 1.0
            
            val_a = a.get(key, 0)
            val_b = b.get(key, 0)
            
            if val_a + val_b > 0:
                similarity = 1 - abs(val_a - val_b) / max(val_a + val_b, 1)
                similarity_sum += similarity * weight
                total_weight += weight
        
        return similarity_sum / total_weight if total_weight > 0 else 1.0

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

        dom_vector = await self._get_dom_vector(page)
        dom_hash = hashlib.sha256(json.dumps(sorted(dom_vector.items()), sort_keys=True).encode()).hexdigest()[:16]
        
        return dom_hash, dom_vector, cookies_hash, storage_hash

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

        if request.resource_type in ["beacon", "ping"]:
            await route.continue_()
            return

        parsed = urlparse(request.url)
        start_domain = urlparse(self.start_url).netloc
        request_domain = parsed.netloc

        if start_domain != request_domain:
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

            logger.info(f"Captured: {request.method} {parsed.path} {f'[body: {len(request.post_data)} bytes]' if request.post_data else ''}")

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

    def _extract_graphql_operation(self, data: str, content_type: str, url: str) -> str:
        """Extract GraphQL operation name"""
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

    async def _replay_state(self, page: Page, start_url: str, target_state: State) -> bool:
        """Replay action sequence to reach target_state with fuzzy validation"""
        try:
            await page.goto(start_url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(1000)

            for action in target_state.path:
                element = await self._find_element_by_action(page, action)
                if not element or not await element.is_enabled():
                    logger.warning(f"Replay failed: element not found for {action.text[:30]}")
                    return False
                await element.click(timeout=1000)
                try:
                    await page.wait_for_load_state("domcontentloaded", timeout=5000)
                except:
                    pass
                await page.wait_for_timeout(500)

            parsed = urlparse(page.url)
            current_normalized = f"{parsed.netloc}{parsed.path}"
            expected_parsed = urlparse(target_state.url)
            expected_normalized = f"{expected_parsed.netloc}{expected_parsed.path}"

            if current_normalized != expected_normalized:
                logger.warning(f"Replay URL mismatch: {current_normalized} != {expected_normalized}")
                return False
        
            current_dom_vector = await self._get_dom_vector(page)
            similarity = self._dom_similarity(target_state.dom_vector, current_dom_vector)

            if similarity < 0.85:
                logger.warning(f"Replay DOM mismatch: similarity {similarity:.2f}")
                return False

            return True

        except Exception as e:
            logger.error(f"State replay failed: {e}")
            return False

    async def _should_skip_state(self, new_state: State) -> bool:
        """Check if state should be skipped based on multiple criteria"""
        
        # 1. Точное совпадение фингерпринта
        exact_fingerprint = new_state.get_fingerprint()
        if exact_fingerprint in self.visited_states:
            self.states_skipped += 1
            logger.info(f"Exact duplicate state: {new_state.url}")
            return True
        
        # 2. Проверка семантического ключа (предотвращает зацикливание на одной странице)
        semantic_key = new_state.get_semantic_key()
        if semantic_key in self.semantic_states:
            # Если это уже третий раз на семантически похожей странице - пропускаем
            similar_states = [s for s in self.semantic_states if s.startswith(new_state.get_semantic_key().split(':')[0])]
            if len(similar_states) >= 3:
                self.states_skipped += 1
                logger.info(f"Too many similar states on {new_state.url}, skipping")
                return True
        
        # 3. Проверка последовательности действий
        sequence_key = ':'.join(a.get_cluster_key() for a in new_state.path)
        if sequence_key in self.visited_sequences:
            self.states_skipped += 1
            logger.info(f"Duplicate action sequence: {sequence_key}")
            return True
        
        # 4. Проверка глубины
        if new_state.depth > self.max_depth:
            self.states_skipped += 1
            logger.info(f"Max depth exceeded: {new_state.depth}")
            return True
        
        # 5. Проверка длины пути
        if len(new_state.path) >= self.max_path_length:
            self.states_skipped += 1
            logger.info(f"Max path length exceeded: {len(new_state.path)}")
            return True
        
        # 6. Проверка на слишком мало действий (возможно, неинтересная страница)
        if len(new_state.actions) < 2 and len(new_state.path) > 1:
            self.states_skipped += 1
            logger.info(f"Too few actions: {len(new_state.actions)}")
            return True
        
        return False

    async def _explore_state(self, page: Page, state: State):
        """Explore single state by executing representative actions from each cluster"""
        logger.info(f"Exploring state: {state.url} (depth={state.depth}, actions={len(state.actions)})")

        # Увеличиваем счётчик посещений
        state.visited_count += 1
        
        await self._fill_forms(page)

        try:
            await page.mouse.wheel(0, 5000)
            await page.wait_for_timeout(500)
        except:
            pass

        # Группируем действия по кластерам
        action_clusters = {}
        for action in state.actions:
            if action not in state.executed_actions and action not in state.dead_actions:
                cluster_key = action.get_cluster_key()
                if cluster_key not in action_clusters:
                    action_clusters[cluster_key] = action

        logger.info(f"Action clusters: {len(action_clusters)}")

        # Сортируем кластеры по приоритету
        # Сначала исследуем формы и отправки, затем навигацию
        priority_order = ['submit', 'auth', 'filter', 'data_loader', 'interaction', 'navigation', 'pagination']
        sorted_clusters = sorted(
            action_clusters.items(),
            key=lambda x: priority_order.index(x[1].semantic) if x[1].semantic in priority_order else len(priority_order)
        )

        initial_state_endpoints = len(state.discovered_endpoints)
        initial_state_clusters = len(state.executed_clusters)

        for cluster_key, action in sorted_clusters:
            if cluster_key in state.executed_clusters:
                continue

            try:
                dom_hash, dom_vector, cookies_hash, storage_hash = await self._get_state_fingerprint(page)
            except Exception as e:
                logger.warning(f"Failed to get state fingerprint before action: {e}")
                break

            initial_request_count = self.request_count
            initial_endpoints = self.unique_endpoints.copy()

            # Для некоторых типов действий сначала заполняем формы
            if action.semantic in ['submit', 'auth', 'filter', 'interaction']:
                await self._fill_forms(page)
                await page.wait_for_timeout(100)

            success, _ = await self._execute_action(page, action)

            if not success:
                continue

            state.executed_actions.add(action)
            state.executed_clusters.add(cluster_key)

            try:
                new_dom, new_dom_vector, new_cookies, new_storage = await self._get_state_fingerprint(page)
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
                logger.info(f"Dead action [{action.semantic}]: {action.text[:30]}")
                continue

            state.discovered_endpoints.update(new_endpoints)
            if new_endpoints:
                logger.info(f"Action [{action.semantic}] discovered {len(new_endpoints)} new endpoints")

            start_domain = urlparse(self.start_url).netloc
            new_domain = urlparse(new_url).netloc

            if state.depth < self.max_depth and len(state.path) < self.max_path_length and start_domain == new_domain and not state.is_volatile:
                try:
                    actions = await self._extract_actions(page)
                    new_state = State(
                        url=new_url,
                        dom_hash=new_dom,
                        dom_vector=new_dom_vector,
                        cookies_hash=new_cookies,
                        storage_hash=new_storage,
                        depth=state.depth + 1,
                        path=state.path + [action],
                        actions=actions
                    )
                    
                    # Проверяем, нужно ли пропустить это состояние
                    if await self._should_skip_state(new_state):
                        continue
                    
                    # Добавляем в отслеживаемые
                    self.visited_states.add(new_state.get_fingerprint())
                    self.semantic_states.add(new_state.get_semantic_key())
                    sequence_key = ':'.join(a.get_cluster_key() for a in new_state.path)
                    self.visited_sequences.add(sequence_key)
                    
                    # Добавляем в очередь
                    self.state_queue.append(new_state)
                    self.states_created += 1
                    
                    logger.info(f"New state [{self.states_created}]: {new_url} (depth={new_state.depth}, actions={len(actions)})")
                        
                except Exception as e:
                    logger.warning(f"Failed to extract actions for new state: {e}")

            new_endpoints_delta = len(state.discovered_endpoints) - initial_state_endpoints
            new_clusters_delta = len(state.executed_clusters) - initial_state_clusters
            
            # Если состояние исчерпано, выходим
            if state.is_exhausted(new_endpoints_delta == 0, new_clusters_delta == 0):
                logger.info(f"State exhausted after {state.visited_count} visits")
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

        if self.stale_iterations >= 2:  # Уменьшил с 3 до 2 для более быстрого завершения
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

            page.on("console", lambda msg: logger.info(f"Console[{msg.type}]: {msg.text}"))

            await page.route("**/*", self.intercept_request)
            page.on("response", self.handle_response)

            await page.goto(self.start_url, wait_until="networkidle", timeout=30000)
            await page.wait_for_timeout(2000)

            dom_hash, dom_vector, cookies_hash, storage_hash = await self._get_state_fingerprint(page)
            initial_actions = await self._extract_actions(page)

            initial_state = State(
                url=self.start_url,
                dom_hash=dom_hash,
                dom_vector=dom_vector,
                cookies_hash=cookies_hash,
                storage_hash=storage_hash,
                depth=0,
                path=[],
                actions=initial_actions
            )

            # Инициализация трекеров
            self.visited_states.add(initial_state.get_fingerprint())
            self.semantic_states.add(initial_state.get_semantic_key())
            self.state_queue.append(initial_state)

            logger.info(f"Initial state has {len(initial_actions)} actions")

            while self.state_queue:
                if await self._check_convergence() and len(self.state_queue) < 2:
                    logger.info("Convergence detected, finishing...")
                    break

                state = self.state_queue.popleft()
                
                logger.info(f"Processing state {state.url} (queue: {len(self.state_queue)}, created: {self.states_created}, skipped: {self.states_skipped})")

                try:
                    if state.path and page.url != state.url:
                        success = await self._replay_state(page, self.start_url, state)
                        if not success:
                            logger.warning(f"Failed to replay state {state.url}, skipping")
                            continue
                    
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
""")


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