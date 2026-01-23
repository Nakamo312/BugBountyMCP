"""
Playwright-based recursive crawler with self-replication
Each crawler explores one branch and spawns child crawlers for sub-branches
"""
import asyncio
import json
import logging
import sys
import hashlib
from typing import Set, Dict, Any, List, Tuple, Optional
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
        if level == 'INFO':
            level_color = Colors.GREEN
        elif level == 'WARNING':
            level_color = Colors.YELLOW
        elif level == 'ERROR':
            level_color = Colors.RED
        else:
            level_color = Colors.RESET
        return f"[{timestamp}] [{level_color}{level}{Colors.RESET}] {record.getMessage()}"


logger = logging.getLogger("recursive_crawler")
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
    visited_count: int = 0
    local_fingerprints: Set[Tuple] = field(default_factory=set)

    def get_fingerprint(self):
        parsed = urlparse(self.url)
        normalized_url = f"{parsed.netloc}{parsed.path}"
        query_keys = frozenset(parse_qs(parsed.query).keys()) if parsed.query else frozenset()
        
        dom_vector_str = json.dumps(sorted(self.dom_vector.items()), sort_keys=True)
        dom_hash = hashlib.sha256(dom_vector_str.encode()).hexdigest()[:16]
        
        return (normalized_url, query_keys, self.cookies_hash, self.storage_hash, dom_hash)

    def is_exhausted(self) -> bool:
        if len(self.actions) == 0:
            return True
        
        total_possible = len(self.actions)
        executed_or_dead = len(self.executed_actions) + len(self.dead_actions)
        return executed_or_dead >= total_possible or self.visited_count >= 2


class PlaywrightScanner:
    """Crawler that recursively explores a branch and spawns child crawlers"""
    
    def __init__(self, 
                 start_url: str,
                 max_depth: int = 3,
                 max_path_length: int = 10,
                 crawler_id: str = "main"):
        
        self.start_url = start_url
        self.max_depth = max_depth
        self.max_path_length = max_path_length
        self.crawler_id = crawler_id
        
        # Глобальные данные для всех краулеров
        self.global_visited_states: Set[Tuple] = set()
        self.global_visited_urls: Set[str] = set()
        self.results: List[Dict[str, Any]] = []
        self.unique_endpoints: Set[str] = set()
        self.unique_methods_paths: Set[str] = set()
        self.unique_json_keys: Set[str] = set()
        self.unique_graphql_ops: Set[str] = set()
        self.request_count = 0
        
        # Локальные для этого краулера
        self.pending_requests: Dict[str, Dict[str, Any]] = {}
        self.seen_requests: Set[str] = set()
        
        # Счетчики
        self.states_explored = 0
        self.child_crawlers_spawned = 0
        
    def _is_static_resource(self, url: str) -> bool:
        lower_url = url.lower().split('?')[0]
        return any(lower_url.endswith(ext) for ext in STATIC_EXTENSIONS)
    
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
    
    async def _get_dom_vector(self, page: Page) -> Dict[str, int]:
        return await page.evaluate("""
            () => {
                const v = {};
                const inc = k => v[k] = (v[k] || 0) + 1;
                
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
    
    async def _extract_actions(self, page: Page) -> Set[Action]:
        actions = set()
        selectors = "button, a, input[type=submit], [role=button], form"
        elements = await page.query_selector_all(selectors)
        
        for el in elements[:30]:
            try:
                if not await el.is_visible() or not await el.is_enabled():
                    continue
                
                text = (await el.text_content() or "").strip()[:50]
                tag = await el.evaluate("el => el.tagName.toLowerCase()")
                selector = await self._generate_selector(el)
                
                if selector:
                    semantic = self._classify_action_semantic(text, selector, tag)
                    actions.add(Action(selector=selector, text=text, tag=tag, semantic=semantic))
            except:
                continue
        
        return actions
    
    async def _generate_selector(self, el: ElementHandle) -> str:
        try:
            return await el.evaluate("""
                el => {
                    if (el.id) return '#' + el.id;
                    if (el.name) return `[name="${el.name}"]`;
                    if (el.getAttribute("aria-label")) {
                        return `[aria-label="${el.getAttribute("aria-label")}"]`;
                    }
                    
                    let path = [];
                    let current = el;
                    while (current.parentElement && path.length < 3) {
                        let tag = current.tagName.toLowerCase();
                        path.unshift(tag);
                        current = current.parentElement;
                    }
                    return path.join(' > ');
                }
            """)
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
                });
            }
        """)
    
    async def _execute_action(self, page: Page, action: Action) -> tuple[bool, bool]:
        try:
            element = await page.query_selector(action.selector)
            if element and await element.is_visible() and await element.is_enabled():
                initial_request_count = self.request_count
                
                await element.scroll_into_view_if_needed()
                
                if action.semantic in ['submit', 'auth']:
                    await self._fill_forms(page)
                    await page.wait_for_timeout(200)
                
                await element.click(timeout=2000)
                
                try:
                    await page.wait_for_load_state("networkidle", timeout=5000)
                except:
                    pass
                
                await page.wait_for_timeout(1000)
                
                had_effect = self.request_count > initial_request_count
                return True, had_effect
        except:
            pass
        return False, False
    
    async def intercept_request(self, route: Route):
        request = route.request
        
        if self._is_static_resource(request.url):
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
        
        if request.method in ["POST", "PUT", "PATCH"] and request.post_data:
            result["request"]["body"] = request.post_data
        
        key = self._make_request_key(request.method, request.url, request.post_data)
        
        if key not in self.seen_requests:
            self.seen_requests.add(key)
            self.pending_requests[key] = result
            
            logger.info(f"[{self.crawler_id}] Captured: {request.method} {parsed.path}")
        
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
                body = await response.text()
                self.unique_json_keys.update(self._extract_json_keys(body))
            except:
                pass
            
            logger.info(f"[{self.crawler_id}] Found: {request.method} {request.url} -> {response.status}")
            print(json.dumps(result), flush=True)
    
    async def _should_skip_state(self, state: State, forbidden_urls: Set[str]) -> bool:
        """Check if state should be skipped"""
        
        # Проверка запрещенных URL (родительских URL)
        if state.url in forbidden_urls:
            logger.info(f"[{self.crawler_id}] Skipping forbidden URL: {state.url}")
            return True
        
        # Проверка глубины
        if state.depth > self.max_depth:
            logger.info(f"[{self.crawler_id}] Max depth exceeded: {state.depth}")
            return True
        
        # Проверка длины пути
        if len(state.path) >= self.max_path_length:
            logger.info(f"[{self.crawler_id}] Max path length exceeded: {len(state.path)}")
            return True
        
        # Проверка глобального посещения
        state_fingerprint = state.get_fingerprint()
        if state_fingerprint in self.global_visited_states:
            logger.debug(f"[{self.crawler_id}] State already visited globally")
            return True
        
        # Проверка локального посещения (в этой ветке)
        if state_fingerprint in state.local_fingerprints:
            logger.debug(f"[{self.crawler_id}] State already visited locally")
            return True
        
        return False
    
    async def explore_branch(self, page: Page, state: State, forbidden_urls: Set[str]):
        """Рекурсивно исследуем ветку и создаем дочерние краулеры"""
        
        logger.info(f"[{self.crawler_id}] Exploring branch: {state.url} (depth={state.depth}, actions={len(state.actions)})")
        
        state.visited_count += 1
        state.local_fingerprints.add(state.get_fingerprint())
        self.global_visited_states.add(state.get_fingerprint())
        self.global_visited_urls.add(state.url)
        self.states_explored += 1
        
        await self._fill_forms(page)
        
        try:
            await page.mouse.wheel(0, 3000)
            await page.wait_for_timeout(300)
        except:
            pass
        
        # Группируем действия по кластерам
        action_clusters = {}
        for action in state.actions:
            if action not in state.executed_actions and action not in state.dead_actions:
                cluster_key = action.get_cluster_key()
                if cluster_key not in action_clusters:
                    action_clusters[cluster_key] = action
        
        logger.info(f"[{self.crawler_id}] Action clusters: {len(action_clusters)}")
        
        # Приоритетный порядок выполнения
        priority_order = ['submit', 'auth', 'filter', 'search', 'data_loader', 'interaction', 'navigation', 'pagination']
        
        for cluster_key, action in action_clusters.items():
            if state.is_exhausted():
                break
            
            # Запоминаем текущее состояние перед действием
            initial_url = page.url
            
            success, had_effect = await self._execute_action(page, action)
            
            if not success:
                state.dead_actions.add(action)
                continue
            
            state.executed_actions.add(action)
            
            if had_effect:
                # Получаем новое состояние
                new_dom, new_dom_vector, new_cookies, new_storage = await self._get_state_fingerprint(page)
                new_url = page.url
                
                # Создаем новое состояние
                new_actions = await self._extract_actions(page)
                new_state = State(
                    url=new_url,
                    dom_hash=new_dom,
                    dom_vector=new_dom_vector,
                    cookies_hash=new_cookies,
                    storage_hash=new_storage,
                    depth=state.depth + 1,
                    path=state.path + [action],
                    actions=new_actions
                )
                
                # Наследуем локальные отпечатки
                new_state.local_fingerprints.update(state.local_fingerprints)
                
                # Проверяем, нужно ли пропустить это состояние
                if not await self._should_skip_state(new_state, forbidden_urls):
                    # Запускаем новый краулер для исследования этой ветки АСИНХРОННО
                    child_crawler = PlaywrightScanner(
                        start_url=new_url,
                        max_depth=self.max_depth,
                        max_path_length=self.max_path_length,
                        crawler_id=f"{self.crawler_id}.{self.child_crawlers_spawned}"
                    )
                    
                    # Передаем глобальные данные
                    child_crawler.global_visited_states = self.global_visited_states
                    child_crawler.global_visited_urls = self.global_visited_urls
                    child_crawler.results = self.results
                    child_crawler.unique_endpoints = self.unique_endpoints
                    child_crawler.unique_methods_paths = self.unique_methods_paths
                    child_crawler.unique_json_keys = self.unique_json_keys
                    child_crawler.unique_graphql_ops = self.unique_graphql_ops
                    
                    # Добавляем текущий URL в запрещенные для потомка
                    new_forbidden = forbidden_urls.copy()
                    new_forbidden.add(state.url)
                    
                    # Запускаем дочерний краулер в отдельной задаче
                    task = asyncio.create_task(
                        child_crawler.explore_from_state(new_state, new_forbidden)
                    )
                    self.child_crawlers_spawned += 1
                    logger.info(f"[{self.crawler_id}] Spawned child crawler {self.child_crawlers_spawned} for {new_url}")
                
                # Возвращаемся в исходное состояние для следующего действия
                if page.url != initial_url:
                    await page.goto(initial_url, wait_until="domcontentloaded", timeout=10000)
                    await page.wait_for_timeout(500)
            else:
                state.dead_actions.add(action)
                logger.info(f"[{self.crawler_id}] Dead action [{action.semantic}]: {action.text[:30]}")
        
        logger.info(f"[{self.crawler_id}] Branch exploration complete: {len(state.executed_actions)} actions executed")
    
    async def explore_from_state(self, initial_state: State, forbidden_urls: Set[str] = None):
        """Начинаем исследование с заданного состояния"""
        if forbidden_urls is None:
            forbidden_urls = set()
        
        logger.info(f"[{self.crawler_id}] Starting exploration from {initial_state.url}")
        
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
            
            # Настройка перехвата запросов
            await page.route("**/*", self.intercept_request)
            page.on("response", self.handle_response)
            
            # Переходим на начальный URL
            await page.goto(initial_state.url, wait_until="networkidle", timeout=30000)
            await page.wait_for_timeout(2000)
            
            # Исследуем ветку
            await self.explore_branch(page, initial_state, forbidden_urls)
            
            await browser.close()
        
        logger.info(f"[{self.crawler_id}] Exploration complete: {self.request_count} requests, {self.states_explored} states, {self.child_crawlers_spawned} children spawned")
    
    async def scan(self):
        """Основной метод сканирования"""
        logger.info(f"[{self.crawler_id}] Starting scan: {self.start_url}")
        
        # Создаем начальное состояние
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
            
            await page.route("**/*", self.intercept_request)
            page.on("response", self.handle_response)
            
            await page.goto(self.start_url, wait_until="networkidle", timeout=30000)
            await page.wait_for_timeout(2000)
            
            # Получаем начальное состояние
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
            
            await browser.close()
        
        # Начинаем рекурсивное исследование
        await self.explore_from_state(initial_state, set())
        
        # Ждем завершения всех дочерних краулеров
        await asyncio.sleep(2)  # Даем время дочерним краулерам завершиться
        
        logger.info(f"""
[MAIN] Scan completed:
  Total Requests: {self.request_count}
  Unique Endpoints: {len(self.unique_endpoints)}
  Methods/Paths: {len(self.unique_methods_paths)}
  JSON Keys: {len(self.unique_json_keys)}
  GraphQL Ops: {len(self.unique_graphql_ops)}
  States Explored: {self.states_explored}
  Child Crawlers Spawned: {self.child_crawlers_spawned}
  Unique URLs Visited: {len(self.global_visited_urls)}
""")


async def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "No URL provided"}), file=sys.stderr)
        sys.exit(1)
    
    url = sys.argv[1]
    max_depth = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    
    crawler = PlaywrightScanner(
        start_url=url,
        max_depth=max_depth,
        crawler_id="main"
    )
    
    try:
        await crawler.scan()
    except Exception as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())