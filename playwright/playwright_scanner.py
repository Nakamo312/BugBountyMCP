"""
Playwright-based state-aware web crawler with BFS exploration
"""
import asyncio
import json
import logging
import sys
import hashlib
import re
import time
from typing import Set, Dict, Any, List, Optional, Tuple
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
    from playwright.async_api import async_playwright, Page, Route, Response, ElementHandle, BrowserContext
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

TRACKER_DOMAINS = {
    'google-analytics.com', 'googletagmanager.com', 'facebook.net',
    'doubleclick.net', 'amazon-adsystem.com', 'analytics.google.com',
    'segment.com', 'mixpanel.com', 'hotjar.com', 'matomo.cloud'
}


@dataclass
class Action:
    selector: str
    text: str
    tag: str
    event_type: str = "click"
    semantic: str = "unknown"
    importance: int = 1

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
    discovered_forms: Set[str] = field(default_factory=set)
    is_volatile: bool = False
    visited_count: int = 0

    def __hash__(self):
        parsed = urlparse(self.url)
        normalized_url = f"{parsed.netloc}{parsed.path}"
        query_keys = frozenset(parse_qs(parsed.query).keys()) if parsed.query else frozenset()
        return hash((normalized_url, query_keys, self.cookies_hash, self.dom_hash[:8]))

    def get_fingerprint(self):
        parsed = urlparse(self.url)
        normalized_url = f"{parsed.netloc}{parsed.path}"
        query_keys = frozenset(parse_qs(parsed.query).keys()) if parsed.query else frozenset()
        return (normalized_url, query_keys, self.cookies_hash, self.dom_hash[:8])

    def is_exhausted(self, no_new_endpoints: bool, no_new_clusters: bool) -> bool:
        all_executed = len(self.executed_actions) >= len(self.actions)
        return all_executed or (no_new_endpoints and no_new_clusters) or self.visited_count > 2


class PlaywrightScanner:
    def __init__(self, url: str, max_depth: int = 4, timeout: int = 600, 
                 max_actions_per_state: int = 100, max_path_length: int = 20,
                 concurrent_pages: int = 3, headless: bool = True):
        self.start_url = url
        self.max_depth = max_depth
        self.timeout = timeout
        self.max_actions_per_state = max_actions_per_state
        self.max_path_length = max_path_length
        self.concurrent_pages = concurrent_pages
        self.headless = headless

        self.visited_states: Set[tuple] = set()
        self.state_queue: deque[State] = deque()
        self.results: list[Dict[str, Any]] = []
        self.pending_requests: Dict[str, Dict[str, Any]] = {}
        self.seen_requests: Set[str] = set()

        self.unique_endpoints: Set[str] = set()
        self.unique_methods_paths: Set[str] = set()
        self.unique_json_keys: Set[str] = set()
        self.unique_graphql_ops: Set[str] = set()
        self.unique_forms: Set[str] = set()
        
        self.request_count = 0
        self.last_request_count = 0
        self.last_endpoint_count = 0
        self.last_keys_count = 0
        self.last_graphql_count = 0
        self.last_forms_count = 0
        self.stale_iterations = 0
        
        self.start_time = time.time()
        self.pages_pool: List[Page] = []
        self.context: Optional[BrowserContext] = None
        self.browser = None
        
        self.total_actions_executed = 0
        self.total_states_explored = 0

    def _is_static_resource(self, url: str) -> bool:
        lower_url = url.lower()
        parsed = urlparse(lower_url)
        
        if any(lower_url.endswith(ext) for ext in STATIC_EXTENSIONS):
            return True
            
        if any(tracker in parsed.netloc for tracker in TRACKER_DOMAINS):
            return True
            
        if parsed.path.endswith(('.js', '.css')):
            if 'chunk' in parsed.path or 'bundle' in parsed.path or 'vendor' in parsed.path:
                return True
                
        return False

    def _classify_action_semantic(self, text: str, selector: str, tag: str) -> Tuple[str, int]:
        text_lower = text.lower()
        selector_lower = selector.lower()
        
        importance = 1
        
        if any(k in text_lower for k in ['login', 'sign in', 'signin', 'authenticate']):
            return 'auth_login', 10
        if any(k in text_lower for k in ['signup', 'register', 'create account']):
            return 'auth_register', 10
        if any(k in text_lower for k in ['logout', 'sign out']):
            return 'auth_logout', 5
        if any(k in text_lower for k in ['submit', 'save', 'create', 'add', 'post', 'send']):
            return 'submit', 8
        if any(k in text_lower for k in ['delete', 'remove', 'destroy']):
            return 'delete', 8
        if any(k in text_lower for k in ['edit', 'update', 'modify']):
            return 'edit', 7
        if any(k in text_lower for k in ['next', '»', '>', 'forward']):
            return 'pagination_next', 6
        if any(k in text_lower for k in ['prev', 'previous', '«', '<', 'back']):
            return 'pagination_prev', 6
        if any(k in text_lower for k in ['filter', 'sort', 'order', 'search']):
            return 'filter', 7
        if any(k in text_lower for k in ['load more', 'show more', 'expand', 'view all']):
            return 'data_loader', 6
        if any(k in text_lower for k in ['download', 'export', 'csv', 'pdf']):
            return 'download', 5
        if any(k in text_lower for k in ['upload', 'browse', 'choose file']):
            return 'upload', 7
        if any(k in text_lower for k in ['settings', 'profile', 'account', 'preferences']):
            return 'settings', 6
        if any(k in text_lower for k in ['admin', 'dashboard', 'panel']):
            return 'admin', 9
        if tag == 'form' or 'form' in selector_lower:
            return 'form', 8
        if tag == 'a' and ('http' in selector_lower or 'mailto:' in text_lower):
            return 'external_link', 1
        if tag == 'a' or 'nav' in selector_lower or 'menu' in selector_lower:
            return 'navigation', 4
        if tag in ['input', 'textarea', 'select']:
            return 'form_input', 5
        if tag == 'button':
            return 'button', 5
            
        return 'interaction', 3

    def _make_request_key(self, method: str, url: str, body: str = None) -> str:
        parsed = urlparse(url)
        normalized_path = parsed.path or '/'
        
        query_params = parse_qs(parsed.query) if parsed.query else {}
        query_sig = '&'.join(f"{k}={sorted(v)[0] if v else ''}" for k, v in sorted(query_params.items()))
        
        body_schema = ''
        if body:
            try:
                body_obj = json.loads(body)
                if isinstance(body_obj, dict):
                    keys = sorted(body_obj.keys())
                    body_schema = ','.join(keys[:5])
                elif isinstance(body_obj, list):
                    body_schema = f'list[{len(body_obj)}]'
            except:
                body_schema = str(len(body))
                
        return f"{method}:{normalized_path}:{query_sig}:{body_schema}"

    async def _get_dom_hash(self, page: Page) -> str:
        fingerprint = await page.evaluate("""
            () => {
                const elements = {
                    forms: document.querySelectorAll('form').length,
                    buttons: document.querySelectorAll('button, [role="button"]').length,
                    links: document.querySelectorAll('a[href]').length,
                    inputs: document.querySelectorAll('input, textarea, select').length,
                    tables: document.querySelectorAll('table').length,
                    lists: document.querySelectorAll('ul, ol').length,
                    iframes: document.querySelectorAll('iframe').length,
                };
                
                const inputTypes = {};
                document.querySelectorAll('input').forEach(input => {
                    const type = input.type || 'text';
                    inputTypes[type] = (inputTypes[type] || 0) + 1;
                });
                
                const structural = `${location.pathname}|${elements.forms}|${elements.buttons}|${elements.inputs}`;
                const types = Object.entries(inputTypes).sort().map(([k, v]) => `${k}:${v}`).join(',');
                
                return structural + '|' + types;
            }
        """)
        return hashlib.sha256(fingerprint.encode()).hexdigest()[:16]

    async def _get_state_fingerprint(self, page: Page):
        cookies = await page.context.cookies()
        cookies_hash = hashlib.sha256(json.dumps(cookies, sort_keys=True, default=str).encode()).hexdigest()[:16]

        storage = await page.evaluate("""
            () => JSON.stringify({
                localStorage: Object.keys(localStorage).sort().map(k => k + ':' + localStorage[k].length),
                sessionStorage: Object.keys(sessionStorage).sort().map(k => k + ':' + sessionStorage[k].length)
            })
        """)
        storage_hash = hashlib.sha256(storage.encode()).hexdigest()[:16]

        dom_hash = await self._get_dom_hash(page)
        return dom_hash, cookies_hash, storage_hash

    def _get_action_selectors(self) -> List[str]:
        return [
            "button:not([disabled])",
            "a[href]:not([href^='javascript:']):not([href^='#']):not([href*='.css']):not([href*='.js'])",
            "input:not([type='hidden']):not([disabled])",
            "textarea:not([disabled])",
            "select:not([disabled])",
            "[onclick]", "[ondblclick]", "[onchange]", "[onsubmit]", "[onmouseover]",
            "[role='button']", "[role='link']", "[role='menuitem']", "[role='tab']", "[role='option']",
            "[tabindex]:not([tabindex='-1'])",
            "[data-action]", "[data-target]", "[data-toggle]", "[data-bs-toggle]",
            "[type='checkbox']", "[type='radio']",
            "summary",
            "label[for]",
            ".btn, .button, .nav-link, .pagination-link, .page-link",
            "[class*='btn-']", "[class*='button-']", "[class*='nav-']",
            "[aria-label*='page']", "[aria-label*='next']", "[aria-label*='prev']",
            "[aria-label*='first']", "[aria-label*='last']",
            "[data-sort]", "[data-filter]", "[data-order]",
            ".sortable, .filterable, .search-input, .search-button",
            "[data-modal]", "[data-dialog]", "[data-popup]",
            "form",
            "[contenteditable='true']"
        ]

    async def _extract_actions(self, page: Page) -> Set[Action]:
        actions = set()
        seen_selectors = set()
        
        selectors = self._get_action_selectors()
        
        for selector in selectors:
            try:
                elements = await page.query_selector_all(selector)
                
                for el in elements[:self.max_actions_per_state]:
                    try:
                        if not await el.is_visible():
                            continue
                            
                        bounding_box = await el.bounding_box()
                        if not bounding_box or bounding_box['width'] * bounding_box['height'] < 10:
                            continue
                            
                        selector_str = await self._generate_selector(el)
                        if not selector_str or selector_str in seen_selectors:
                            continue
                            
                        text = (await el.text_content() or "").strip()[:200]
                        
                        tag = await el.evaluate("el => el.tagName.toLowerCase()")
                        
                        semantic, importance = self._classify_action_semantic(text, selector_str, tag)
                        
                        event_type = "click"
                        if tag in ["input", "textarea", "select"]:
                            event_type = "change"
                        elif tag == "form":
                            event_type = "submit"
                        elif await el.get_attribute("type") == "submit":
                            event_type = "submit"
                            
                        action = Action(
                            selector=selector_str,
                            text=text,
                            tag=tag,
                            event_type=event_type,
                            semantic=semantic,
                            importance=importance
                        )
                        
                        actions.add(action)
                        seen_selectors.add(selector_str)
                        
                    except Exception as e:
                        continue
                        
            except Exception as e:
                continue
        
        await self._extract_form_actions(page, actions, seen_selectors)
        await self._extract_dynamic_actions(page, actions, seen_selectors)
        
        logger.info(f"Found {len(actions)} actions on {page.url}")
        return actions

    async def _extract_form_actions(self, page: Page, actions: Set[Action], seen_selectors: Set[str]):
        try:
            forms = await page.query_selector_all('form')
            
            for form in forms:
                try:
                    form_selector = await self._generate_selector(form)
                    if not form_selector or form_selector in seen_selectors:
                        continue
                        
                    form_id = await form.get_attribute('id') or ''
                    form_action = await form.get_attribute('action') or ''
                    form_method = await form.get_attribute('method') or 'GET'
                    
                    form_key = f"{form_method}:{form_action}:{form_id}"
                    if form_key not in self.unique_forms:
                        self.unique_forms.add(form_key)
                        
                        action = Action(
                            selector=form_selector,
                            text=f"Form: {form_id or form_action or 'unnamed'}",
                            tag="form",
                            event_type="submit",
                            semantic="form",
                            importance=8
                        )
                        actions.add(action)
                        seen_selectors.add(form_selector)
                        
                except:
                    continue
                    
        except:
            pass

    async def _extract_dynamic_actions(self, page: Page, actions: Set[Action], seen_selectors: Set[str]):
        try:
            scripts = await page.evaluate("""
                () => {
                    const scripts = [];
                    document.querySelectorAll('script:not([src])').forEach(script => {
                        if (script.textContent.includes('addEventListener') || 
                            script.textContent.includes('onclick') ||
                            script.textContent.includes('submit') ||
                            script.textContent.includes('fetch') ||
                            script.textContent.includes('XMLHttpRequest')) {
                            scripts.push(script.textContent.substring(0, 500));
                        }
                    });
                    return scripts;
                }
            """)
            
            if scripts:
                logger.debug(f"Found {len(scripts)} inline scripts with event handlers")
                
        except:
            pass

    async def _generate_selector(self, el: ElementHandle) -> str:
        try:
            selector = await el.evaluate("""
                (element) => {
                    function getUniqueSelector(el) {
                        if (el.id) return '#' + el.id;
                        if (el.dataset.testid) return `[data-testid="${el.dataset.testid}"]`;
                        if (el.dataset.id) return `[data-id="${el.dataset.id}"]`;
                        if (el.name && el.tagName === 'INPUT') return `input[name="${el.name}"]`;
                        if (el.getAttribute("aria-label")) return `[aria-label="${el.getAttribute("aria-label")}"]`;
                        
                        let path = [];
                        let current = el;
                        
                        while (current && current.nodeType === Node.ELEMENT_NODE) {
                            let selector = current.tagName.toLowerCase();
                            
                            if (current.className && typeof current.className === 'string') {
                                const classes = current.className.split(/\s+/).filter(c => c);
                                if (classes.length > 0) {
                                    selector += '.' + classes.join('.');
                                }
                            }
                            
                            const siblings = Array.from(current.parentElement.children)
                                .filter(child => child.tagName === current.tagName);
                            if (siblings.length > 1) {
                                const index = siblings.indexOf(current) + 1;
                                selector += `:nth-of-type(${index})`;
                            }
                            
                            path.unshift(selector);
                            
                            if (current.parentElement === document.body || path.length >= 3) {
                                break;
                            }
                            
                            current = current.parentElement;
                        }
                        
                        return path.join(' > ');
                    }
                    
                    return getUniqueSelector(element);
                }
            """)
            return selector
        except:
            return None

    async def _smart_fill_form(self, page: Page, form: ElementHandle = None):
        try:
            if form:
                inputs = await form.query_selector_all('input, textarea, select')
            else:
                inputs = await page.query_selector_all('input, textarea, select')
                
            for inp in inputs:
                try:
                    input_type = await inp.get_attribute('type') or 'text'
                    tag_name = await inp.evaluate("el => el.tagName.toLowerCase()")
                    name = await inp.get_attribute('name') or ''
                    id_attr = await inp.get_attribute('id') or ''
                    
                    if input_type == 'hidden':
                        continue
                        
                    current_value = await inp.evaluate("el => el.value")
                    if current_value:
                        continue
                    
                    if not await inp.is_visible():
                        continue
                    
                    if tag_name == 'select':
                        options = await inp.query_selector_all('option:not([disabled]):not([value=""])')
                        if options:
                            await options[0].click()
                            
                    elif input_type == 'checkbox' or input_type == 'radio':
                        await inp.click()
                        
                    elif input_type == 'email':
                        await inp.fill('test@example.com')
                        
                    elif input_type == 'password':
                        await inp.fill('TestPassword123!')
                        
                    elif input_type == 'number' or input_type == 'range':
                        await inp.fill('42')
                        
                    elif input_type == 'tel':
                        await inp.fill('+1234567890')
                        
                    elif input_type == 'url':
                        await inp.fill('https://example.com')
                        
                    elif input_type == 'date':
                        await inp.fill('2024-01-01')
                        
                    elif input_type == 'color':
                        await inp.fill('#ff0000')
                        
                    else:
                        test_values = {
                            'username': 'testuser',
                            'login': 'testlogin',
                            'email': 'test@example.com',
                            'password': 'TestPassword123!',
                            'search': 'test search',
                            'query': 'test query',
                            'q': 'test',
                            'name': 'Test User',
                            'title': 'Test Title',
                            'description': 'Test description for field',
                            'message': 'Test message content',
                            'comment': 'Test comment here',
                            'content': 'Test content value',
                            'text': 'Sample text input',
                            'firstname': 'John',
                            'lastname': 'Doe',
                            'phone': '+1234567890',
                            'address': '123 Test Street',
                            'city': 'Test City',
                            'zip': '12345',
                            'country': 'Testland'
                        }
                        
                        filled = False
                        for key, value in test_values.items():
                            if key in name.lower() or key in id_attr.lower():
                                await inp.fill(value)
                                filled = True
                                break
                                
                        if not filled:
                            placeholder = await inp.get_attribute('placeholder') or ''
                            if placeholder:
                                await inp.fill(placeholder)
                            else:
                                await inp.fill('test')
                                
                    await inp.dispatch_event('input')
                    await inp.dispatch_event('change')
                    await page.wait_for_timeout(50)
                    
                except Exception as e:
                    continue
                    
            await page.wait_for_timeout(100)
            
        except Exception as e:
            logger.debug(f"Form fill error: {e}")

    async def _execute_action(self, page: Page, action: Action) -> Tuple[bool, bool]:
        try:
            initial_request_count = self.request_count
            initial_url = page.url
            initial_endpoints = self.unique_endpoints.copy()
            
            await page.evaluate(f"""
                (selector) => {{
                    const el = document.querySelector(selector);
                    if (el) {{
                        el.scrollIntoView({{behavior: 'instant', block: 'center'}});
                    }}
                }}
            """, action.selector)
            
            await page.wait_for_timeout(50)
            
            if action.event_type == "change" and action.tag in ["input", "textarea", "select"]:
                element = await page.query_selector(action.selector)
                if element:
                    await self._smart_fill_form(page)
                    
            elif action.event_type == "submit" or action.tag == "form":
                if action.tag == "form":
                    await self._smart_fill_form(page)
                    await page.evaluate(f"""
                        (selector) => {{
                            const form = document.querySelector(selector);
                            if (form) form.submit();
                        }}
                    """, action.selector)
                else:
                    element = await page.query_selector(action.selector)
                    if element:
                        await self._smart_fill_form(page)
                        await element.click()
                        
            else:
                await page.evaluate(f"""
                    (selector) => {{
                        const el = document.querySelector(selector);
                        if (el) {{
                            const rect = el.getBoundingClientRect();
                            const x = rect.left + rect.width / 2;
                            const y = rect.top + rect.height / 2;
                            
                            const clickEvent = new MouseEvent('click', {{
                                view: window,
                                bubbles: true,
                                cancelable: true,
                                clientX: x,
                                clientY: y
                            }});
                            el.dispatchEvent(clickEvent);
                        }}
                    }}
                """, action.selector)
            
            try:
                await page.wait_for_load_state("networkidle", timeout=3000)
            except:
                pass
                
            await page.wait_for_timeout(200)
            
            request_delta = self.request_count - initial_request_count
            url_changed = page.url != initial_url
            new_endpoints = self.unique_endpoints - initial_endpoints
            
            had_effect = request_delta > 0 or url_changed or len(new_endpoints) > 0
            
            if had_effect:
                logger.debug(f"Action successful: {action.semantic} - {action.text[:30]}")
                
            return True, had_effect
            
        except Exception as e:
            logger.debug(f"Action failed: {action.text[:30]} - {e}")
            return False, False

    async def intercept_request(self, route: Route):
        request = route.request

        if self._is_static_resource(request.url):
            await route.continue_()
            return

        if request.resource_type in ["beacon", "ping", "csp_report", "font"]:
            await route.continue_()
            return

        parsed = urlparse(request.url)
        start_domain = urlparse(self.start_url).netloc

        if start_domain != parsed.netloc:
            await route.continue_()
            return

        result = {
            "request": {
                "method": request.method,
                "url": request.url,
                "endpoint": parsed.path,
                "headers": dict(request.headers),
                "resource_type": request.resource_type,
            },
            "timestamp": time.time()
        }

        if request.method in ["POST", "PUT", "PATCH", "DELETE"] and request.post_data:
            result["request"]["body"] = request.post_data
            
            try:
                if request.post_data:
                    body_obj = json.loads(request.post_data)
                    if isinstance(body_obj, dict):
                        result["request"]["body_keys"] = list(body_obj.keys())
            except:
                pass

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

            logger.info(f"{Colors.CYAN}Request: {request.method} {parsed.path}{Colors.RESET}")

            self.request_count += 1
            self.unique_endpoints.add(request.url)
            endpoint = f"{request.method} {parsed.path}"
            self.unique_methods_paths.add(endpoint)

            if request.post_data:
                keys = self._extract_json_keys(request.post_data)
                self.unique_json_keys.update(keys)
                
                content_type = request.headers.get("content-type", "")
                graphql_op = self._extract_graphql_operation(request.post_data, content_type, request.url)
                if graphql_op:
                    self.unique_graphql_ops.add(graphql_op)

            print(json.dumps(result), flush=True)

        await route.continue_()

    def _extract_json_keys(self, data: str) -> Set[str]:
        keys = set()
        try:
            obj = json.loads(data)
            
            def extract_keys(obj, path=""):
                if isinstance(obj, dict):
                    for key, value in obj.items():
                        full_key = f"{path}.{key}" if path else key
                        keys.add(full_key)
                        extract_keys(value, full_key)
                elif isinstance(obj, list) and obj:
                    extract_keys(obj[0], f"{path}[]" if path else "[]")
                    
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
                for item in obj:
                    if isinstance(item, dict):
                        if "query" in item or "mutation" in item:
                            return item.get("operationName", "graphql_batch")
                            
            elif isinstance(obj, dict):
                if "query" in obj:
                    query = obj["query"]
                    match = re.search(r'(query|mutation)\s+(\w+)', query)
                    if match:
                        return match.group(2)
                    return "anonymous_graphql"
                elif "id" in obj and "variables" in obj:
                    return "graphql_persisted"
                    
        except:
            pass
        return None

    async def handle_response(self, response: Response):
        request = response.request
        key = self._make_request_key(request.method, request.url, request.post_data)

        if key in self.pending_requests:
            result = self.pending_requests.pop(key)

            try:
                body = await response.text()
                result["response"] = {
                    "status_code": response.status,
                    "headers": dict(response.headers),
                    "body_size": len(body),
                }
                
                if response.status >= 400:
                    logger.warning(f"{Colors.YELLOW}Error {response.status}: {request.method} {request.url}{Colors.RESET}")
                else:
                    logger.info(f"{Colors.GREEN}Response {response.status}: {request.method} {request.url}{Colors.RESET}")
                    
                if body and len(body) < 10000:
                    try:
                        json.loads(body)
                        result["response"]["is_json"] = True
                    except:
                        pass
                        
            except Exception as e:
                result["response"] = {
                    "status_code": response.status,
                    "headers": dict(response.headers),
                    "error": str(e)
                }

            self.results.append(result)
            
            print(json.dumps(result), flush=True)

    async def _explore_state(self, page: Page, state: State):
        state.visited_count += 1
        self.total_states_explored += 1
        
        logger.info(f"{Colors.MAGENTA}Exploring state: {state.url} (depth={state.depth}, actions={len(state.actions)}, visited={state.visited_count}){Colors.RESET}")

        try:
            if state.path and page.url != state.url:
                await page.goto(state.url, wait_until="domcontentloaded", timeout=10000)
                await page.wait_for_timeout(500)
        except:
            try:
                await page.goto(self.start_url, wait_until="domcontentloaded", timeout=10000)
                for action in state.path:
                    await self._execute_action(page, action)
            except:
                logger.error(f"Failed to navigate to state: {state.url}")
                return

        await self._smart_fill_form(page)
        
        try:
            await page.mouse.wheel(0, 3000)
            await page.wait_for_timeout(300)
            await page.mouse.wheel(0, 3000)
            await page.wait_for_timeout(300)
        except:
            pass

        initial_endpoints = state.discovered_endpoints.copy()
        initial_clusters = state.executed_clusters.copy()

        actions_by_importance = sorted(state.actions, key=lambda a: a.importance, reverse=True)
        
        for action in actions_by_importance:
            if action in state.executed_actions or action in state.dead_actions:
                continue
                
            if action.get_cluster_key() in state.executed_clusters:
                state.executed_actions.add(action)
                continue

            success, had_effect = await self._execute_action(page, action)
            self.total_actions_executed += 1
            
            if success:
                state.executed_actions.add(action)
                state.executed_clusters.add(action.get_cluster_key())
                
                if had_effect:
                    current_endpoints = self.unique_endpoints.copy()
                    new_endpoints = current_endpoints - initial_endpoints
                    state.discovered_endpoints.update(new_endpoints)
                    
                    if new_endpoints:
                        logger.info(f"{Colors.BLUE}Action [{action.semantic}] found {len(new_endpoints)} new endpoints{Colors.RESET}")
                    
                    try:
                        new_dom, new_cookies, new_storage = await self._get_state_fingerprint(page)
                        new_url = page.url
                        
                        start_domain = urlparse(self.start_url).netloc
                        new_domain = urlparse(new_url).netloc
                        
                        if state.depth < self.max_depth and len(state.path) < self.max_path_length and start_domain == new_domain:
                            try:
                                new_actions = await self._extract_actions(page)
                                new_state = State(
                                    url=new_url,
                                    dom_hash=new_dom,
                                    cookies_hash=new_cookies,
                                    storage_hash=new_storage,
                                    depth=state.depth + 1,
                                    path=state.path + [action],
                                    actions=new_actions
                                )
                                
                                state_fingerprint = new_state.get_fingerprint()
                                if state_fingerprint not in self.visited_states:
                                    self.visited_states.add(state_fingerprint)
                                    self.state_queue.append(new_state)
                                    logger.info(f"{Colors.GREEN}New state queued: {new_url} (actions={len(new_actions)}){Colors.RESET}")
                            except Exception as e:
                                logger.debug(f"Failed to create new state: {e}")
                                
                    except Exception as e:
                        logger.debug(f"Failed to get new state fingerprint: {e}")
                        
                else:
                    state.dead_actions.add(action)
                    logger.debug(f"Dead action: {action.text[:30]}")
                    
            new_endpoints_delta = len(state.discovered_endpoints) - len(initial_endpoints)
            new_clusters_delta = len(state.executed_clusters) - len(initial_clusters)
            
            if state.is_exhausted(new_endpoints_delta == 0, new_clusters_delta == 0):
                logger.info(f"State exhausted: executed {len(state.executed_actions)}/{len(state.actions)} actions")
                break
                
            if self.total_actions_executed % 10 == 0:
                self._print_progress()
                
        logger.info(f"State exploration complete: {len(state.executed_actions)} actions executed")

    async def _check_convergence(self) -> bool:
        endpoints_delta = len(self.unique_endpoints) - self.last_endpoint_count
        requests_delta = self.request_count - self.last_request_count
        keys_delta = len(self.unique_json_keys) - self.last_keys_count
        graphql_delta = len(self.unique_graphql_ops) - self.last_graphql_count
        forms_delta = len(self.unique_forms) - self.last_forms_count

        if endpoints_delta == 0 and requests_delta == 0 and keys_delta == 0 and graphql_delta == 0 and forms_delta == 0:
            self.stale_iterations += 1
        else:
            self.stale_iterations = 0

        self.last_request_count = self.request_count
        self.last_endpoint_count = len(self.unique_endpoints)
        self.last_keys_count = len(self.unique_json_keys)
        self.last_graphql_count = len(self.unique_graphql_ops)
        self.last_forms_count = len(self.unique_forms)

        if self.stale_iterations >= 3:
            logger.info(f"{Colors.YELLOW}Convergence detected: no new discoveries for {self.stale_iterations} iterations{Colors.RESET}")
            return True

        return False

    def _print_progress(self):
        duration = time.time() - self.start_time
        eps = self.total_actions_executed / duration if duration > 0 else 0
        
        logger.info(f"{Colors.CYAN}Progress: {self.total_states_explored} states, {self.total_actions_executed} actions, {self.request_count} requests, {len(self.unique_endpoints)} endpoints, {eps:.1f} actions/s{Colors.RESET}")

    async def scan(self):
        logger.info(f"{Colors.GREEN}Starting scan: {self.start_url}{Colors.RESET}")
        logger.info(f"Max depth: {self.max_depth}, Timeout: {self.timeout}s, Concurrent pages: {self.concurrent_pages}")

        async with async_playwright() as p:
            self.browser = await p.chromium.launch(
                headless=self.headless,
                args=[
                    '--no-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-gpu',
                    '--disable-blink-features=AutomationControlled',
                    '--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                ]
            )

            self.context = await self.browser.new_context(
                ignore_https_errors=True,
                viewport={'width': 1920, 'height': 1080},
                java_script_enabled=True,
                bypass_csp=True
            )

            for i in range(self.concurrent_pages):
                page = await self.context.new_page()
                
                await page.route("**/*", lambda route: self.intercept_request(route))
                page.on("response", lambda response: self.handle_response(response))
                
                await page.add_init_script("""
                    window.__CRAWLER_DETECTED_EVENTS = [];
                    const originalAdd = EventTarget.prototype.addEventListener;
                    EventTarget.prototype.addEventListener = function(type, listener, options) {
                        if (['click', 'submit', 'change', 'mouseover', 'focus'].includes(type)) {
                            window.__CRAWLER_DETECTED_EVENTS.push({
                                type: type,
                                target: this.tagName + (this.className ? '.' + this.className : ''),
                                time: Date.now()
                            });
                        }
                        return originalAdd.call(this, type, listener, options);
                    };
                """)
                
                self.pages_pool.append(page)

            main_page = self.pages_pool[0]
            await main_page.goto(self.start_url, wait_until="networkidle", timeout=30000)
            await main_page.wait_for_timeout(1000)

            dom_hash, cookies_hash, storage_hash = await self._get_state_fingerprint(main_page)
            initial_actions = await self._extract_actions(main_page)

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

            logger.info(f"Initial state: {len(initial_actions)} actions found")

            while self.state_queue:
                if time.time() - self.start_time > self.timeout:
                    logger.warning(f"{Colors.RED}Timeout reached after {self.timeout}s{Colors.RESET}")
                    break

                state = self.state_queue.popleft()

                page = self.pages_pool[self.total_states_explored % len(self.pages_pool)]
                
                try:
                    await self._explore_state(page, state)
                except Exception as e:
                    logger.error(f"{Colors.RED}Error exploring state {state.url}: {e}{Colors.RESET}")

                if await self._check_convergence() and len(self.state_queue) < 2:
                    logger.info(f"{Colors.GREEN}Convergence reached, stopping exploration{Colors.RESET}")
                    break

            await self.browser.close()

        self._print_final_statistics()

    def _print_final_statistics(self):
        duration = time.time() - self.start_time
        
        print("\n" + "="*80, file=sys.stderr)
        print(f"SCAN COMPLETED IN {duration:.2f} SECONDS", file=sys.stderr)
        print("="*80, file=sys.stderr)
        print(f"States explored:       {self.total_states_explored}", file=sys.stderr)
        print(f"Actions executed:      {self.total_actions_executed}", file=sys.stderr)
        print(f"HTTP requests:         {self.request_count}", file=sys.stderr)
        print(f"Unique endpoints:      {len(self.unique_endpoints)}", file=sys.stderr)
        print(f"Unique methods/paths:  {len(self.unique_methods_paths)}", file=sys.stderr)
        print(f"Unique JSON keys:      {len(self.unique_json_keys)}", file=sys.stderr)
        print(f"Unique GraphQL ops:    {len(self.unique_graphql_ops)}", file=sys.stderr)
        print(f"Unique forms:          {len(self.unique_forms)}", file=sys.stderr)
        print(f"Visited states:        {len(self.visited_states)}", file=sys.stderr)
        print("="*80, file=sys.stderr)
        
        if self.unique_methods_paths:
            print("\nDISCOVERED ENDPOINTS:", file=sys.stderr)
            for endpoint in sorted(self.unique_methods_paths):
                print(f"  {endpoint}", file=sys.stderr)


async def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "No URL provided"}), file=sys.stderr)
        sys.exit(1)

    url = sys.argv[1]
    
    max_depth = 4
    concurrent_pages = 3
    timeout = 600
    
    for i, arg in enumerate(sys.argv[2:]):
        if arg == "--max-depth" and i + 3 < len(sys.argv):
            max_depth = int(sys.argv[i + 3])
        elif arg == "--concurrent" and i + 3 < len(sys.argv):
            concurrent_pages = int(sys.argv[i + 3])
        elif arg == "--timeout" and i + 3 < len(sys.argv):
            timeout = int(sys.argv[i + 3])
        elif arg == "--headless":
            pass
        elif arg.startswith("--"):
            print(json.dumps({"error": f"Unknown option: {arg}"}), file=sys.stderr)
            sys.exit(1)

    scanner = PlaywrightScanner(
        url, 
        max_depth=max_depth,
        timeout=timeout,
        concurrent_pages=concurrent_pages,
        headless="--headless" in sys.argv
    )

    try:
        await scanner.scan()
    except KeyboardInterrupt:
        print(json.dumps({"error": "Scan interrupted by user"}), file=sys.stderr)
        scanner._print_final_statistics()
    except Exception as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        scanner._print_final_statistics()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())