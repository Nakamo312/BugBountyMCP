"""
True BFS Playwright-based web crawler with parameter discovery
"""
import asyncio
import json
import logging
import sys
import hashlib
import re
import time
from typing import Set, Dict, Any, List, Optional, Tuple, Deque
from urllib.parse import urlparse, parse_qs, urljoin, urlencode, parse_qsl
from dataclasses import dataclass, field
from collections import deque
import random


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
    href: str = ""
    event_type: str = "click"
    semantic: str = "unknown"
    importance: int = 1

    def __hash__(self):
        return hash((self.selector, self.text, self.tag, self.href))

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
    depth: int
    actions: List[Action] = field(default_factory=list)
    path: List[Action] = field(default_factory=list)
    
    def __hash__(self):
        parsed = urlparse(self.url)
        path = parsed.path
        query = frozenset(parse_qsl(parsed.query))  # Сохраняем пары ключ-значение
        fragment = parsed.fragment or ""
        return hash((parsed.netloc, path, query, fragment, self.dom_hash))

    def __eq__(self, other):
        return hash(self) == hash(other)


class PlaywrightScanner:
    def __init__(self, url: str, max_depth: int = 3, timeout: int = 300, 
                 max_actions_per_state: int = 50, headless: bool = True):
        self.start_url = url
        self.max_depth = max_depth
        self.timeout = timeout
        self.max_actions_per_state = max_actions_per_state
        self.headless = headless

        self.visited_states: Set[State] = set()
        self.state_queue: Deque[State] = deque()
        self.results: List[Dict[str, Any]] = []
        
        self.unique_endpoints: Set[str] = set()
        self.unique_methods_paths: Set[str] = set()
        self.unique_params: Set[Tuple[str, str]] = set()
        
        self.request_count = 0
        self.action_count = 0
        self.start_time = time.time()
        
        self.domain = urlparse(url).netloc

    def _is_static_resource(self, url: str) -> bool:
        """Check if URL is a static resource"""
        parsed = urlparse(url)
        path = parsed.path.lower()
        
        if any(path.endswith(ext) for ext in STATIC_EXTENSIONS):
            return True
            
        if parsed.netloc != self.domain:
            return True
            
        return False

    async def _get_dom_hash(self, page: Page) -> str:
        """Get semantic DOM fingerprint"""
        fingerprint = await page.evaluate("""
            () => {
                const elements = {
                    forms: document.querySelectorAll('form').length,
                    buttons: document.querySelectorAll('button, [role="button"]').length,
                    links: document.querySelectorAll('a[href]').length,
                    inputs: document.querySelectorAll('input, textarea, select').length,
                };
                
                const links = Array.from(document.querySelectorAll('a[href]'))
                    .map(a => a.href.split('?')[0])
                    .filter(h => h.startsWith('http'))
                    .sort()
                    .slice(0, 10)
                    .join('|');
                
                return `${location.pathname}|${elements.forms}|${elements.buttons}|${links}`;
            }
        """)
        return hashlib.sha256(fingerprint.encode()).hexdigest()[:16]

    def _classify_action(self, element: ElementHandle, selector: str, text: str, tag: str) -> Action:
        """Classify action based on element properties"""
        semantic = "unknown"
        importance = 1
        
        text_lower = text.lower()
        
        if tag == 'a':
            href = asyncio.run_coroutine_threadsafe(element.get_attribute('href'), asyncio.get_event_loop()).result() or ""
            if 'login' in text_lower or 'signin' in text_lower:
                semantic, importance = 'auth_login', 10
            elif 'register' in text_lower or 'signup' in text_lower:
                semantic, importance = 'auth_register', 10
            elif href and '?' in href:
                semantic, importance = 'param_link', 8
            else:
                semantic, importance = 'navigation', 5
        elif tag == 'form':
            semantic, importance = 'form', 9
        elif tag == 'button' or tag == 'input' and asyncio.run_coroutine_threadsafe(element.get_attribute('type'), asyncio.get_event_loop()).result() == 'submit':
            if 'submit' in text_lower or 'save' in text_lower:
                semantic, importance = 'submit', 8
            else:
                semantic, importance = 'button', 6
        elif tag in ['input', 'textarea', 'select']:
            semantic, importance = 'input', 7
        
        return Action(
            selector=selector,
            text=text[:100],
            tag=tag,
            href=asyncio.run_coroutine_threadsafe(element.get_attribute('href'), asyncio.get_event_loop()).result() if tag == 'a' else "",
            semantic=semantic,
            importance=importance
        )

    async def _extract_actions(self, page: Page, state: State) -> List[Action]:
        """Extract all possible actions from current page"""
        actions = []
        seen_selectors = set()
        
        selectors = [
            "a[href]:not([href^='javascript:']):not([href^='#'])",
            "form",
            "button:not([disabled])",
            "input[type='submit']:not([disabled])",
            "input[type='button']:not([disabled])",
            "[onclick]",
            "[role='button']",
        ]
        
        for selector in selectors:
            try:
                elements = await page.query_selector_all(selector)
                
                for element in elements[:self.max_actions_per_state]:
                    try:
                        if not await element.is_visible():
                            continue
                            
                        # Generate unique selector
                        selector_str = await self._generate_selector(element)
                        if not selector_str or selector_str in seen_selectors:
                            continue
                            
                        # Get element info
                        text = (await element.text_content() or "").strip()
                        tag = await element.evaluate("el => el.tagName.toLowerCase()")
                        
                        # Classify action
                        action = self._classify_action(element, selector_str, text, tag)
                        
                        actions.append(action)
                        seen_selectors.add(selector_str)
                        
                    except:
                        continue
                        
            except:
                continue
        
        # Sort by importance (higher first)
        actions.sort(key=lambda x: x.importance, reverse=True)
        
        logger.info(f"Found {len(actions)} actions on {page.url}")
        return actions

    async def _generate_selector(self, element: ElementHandle) -> str:
        """Generate CSS selector for element"""
        try:
            selector = await element.evaluate("""
                (el) => {
                    if (el.id) return '#' + el.id;
                    if (el.name) return `[name="${el.name}"]`;
                    
                    const classes = el.className;
                    if (classes && typeof classes === 'string') {
                        const classList = classes.split(/\\s+/).filter(c => c.length > 0);
                        if (classList.length > 0) {
                            return el.tagName.toLowerCase() + '.' + classList.join('.');
                        }
                    }
                    
                    const attrs = ['data-testid', 'data-id', 'aria-label', 'title'];
                    for (const attr of attrs) {
                        const value = el.getAttribute(attr);
                        if (value) {
                            return `[${attr}="${value}"]`;
                        }
                    }
                    
                    return el.tagName.toLowerCase();
                }
            """)
            return selector
        except:
            return None

    async def _smart_fill_and_submit_form(self, page: Page, form: ElementHandle):
        """Smart fill form with test data and submit"""
        try:
            # Get form action and method
            action = await form.get_attribute('action') or page.url
            method = (await form.get_attribute('method') or 'get').lower()
            
            # Fill all inputs
            inputs = await form.query_selector_all('input, textarea, select')
            form_data = {}
            
            for inp in inputs:
                try:
                    inp_type = await inp.get_attribute('type') or 'text'
                    inp_name = await inp.get_attribute('name')
                    
                    if not inp_name or inp_type == 'hidden':
                        continue
                    
                    # Fill based on input type and name
                    if inp_type in ['text', 'search']:
                        if 'email' in inp_name.lower():
                            await inp.fill('test@example.com')
                            form_data[inp_name] = 'test@example.com'
                        elif 'search' in inp_name.lower() or 'query' in inp_name.lower() or 'q' == inp_name:
                            await inp.fill('test')
                            form_data[inp_name] = 'test'
                        else:
                            await inp.fill('test')
                            form_data[inp_name] = 'test'
                    elif inp_type == 'password':
                        await inp.fill('password123')
                        form_data[inp_name] = 'password123'
                    elif inp_type == 'email':
                        await inp.fill('test@example.com')
                        form_data[inp_name] = 'test@example.com'
                    elif inp_type == 'number':
                        await inp.fill('1')
                        form_data[inp_name] = '1'
                    elif inp_type == 'checkbox':
                        await inp.click()
                        form_data[inp_name] = 'on'
                    elif inp_type == 'radio':
                        await inp.click()
                        form_data[inp_name] = await inp.get_attribute('value') or 'on'
                    elif inp_type == 'file':
                        # Skip file uploads for now
                        continue
                        
                except:
                    continue
            
            # Submit form
            if method == 'get':
                # For GET forms, construct URL with parameters
                parsed_action = urlparse(action)
                base_url = urljoin(page.url, parsed_action.path)
                
                existing_params = parse_qs(parsed_action.query)
                for key, value in form_data.items():
                    existing_params[key] = [value]
                
                query_string = urlencode(existing_params, doseq=True)
                target_url = f"{base_url}?{query_string}" if query_string else base_url
                
                # Navigate to URL
                await page.goto(target_url, wait_until="networkidle", timeout=10000)
                
            else:
                # For POST forms, find submit button and click
                submit_button = await form.query_selector('button[type="submit"], input[type="submit"]')
                if submit_button:
                    await submit_button.click()
                else:
                    # Fallback: submit via JavaScript
                    await page.evaluate("(form) => form.submit()", form)
                    
            await page.wait_for_timeout(1000)
            
        except Exception as e:
            logger.debug(f"Form submission error: {e}")

    async def _execute_action(self, page: Page, action: Action, state: State) -> Optional[State]:
        """Execute action and return new state if created"""
        try:
            logger.info(f"Executing action: {action.semantic} - {action.text[:30]}")
            
            if action.tag == 'a':
                # Handle links
                if action.href:
                    href = action.href
                    if href.startswith('http'):
                        target_url = href
                    else:
                        target_url = urljoin(page.url, href)
                    
                    # Extract parameters from URL
                    parsed = urlparse(target_url)
                    if parsed.query:
                        params = parse_qsl(parsed.query)
                        for key, value in params:
                            self.unique_params.add((key, value))
                    
                    await page.goto(target_url, wait_until="networkidle", timeout=10000)
                    
            elif action.tag == 'form':
                # Handle forms
                element = await page.query_selector(action.selector)
                if element:
                    await self._smart_fill_and_submit_form(page, element)
                    
            else:
                # Handle buttons and other clickable elements
                element = await page.query_selector(action.selector)
                if element:
                    await element.click()
                    await page.wait_for_timeout(500)
            
            # Wait for page to stabilize
            try:
                await page.wait_for_load_state("networkidle", timeout=3000)
            except:
                pass
            
            await page.wait_for_timeout(500)
            
            # Get new state
            new_url = page.url
            new_dom_hash = await self._get_dom_hash(page)
            
            # Check if we should create new state
            parsed_new = urlparse(new_url)
            parsed_current = urlparse(state.url)
            
            # Don't create new state if we left the domain
            if parsed_new.netloc != self.domain:
                return None
            
            # Don't create new state if depth exceeded
            if state.depth >= self.max_depth:
                return None
            
            # Extract actions from new page
            new_actions = await self._extract_actions(page, state)
            
            new_state = State(
                url=new_url,
                dom_hash=new_dom_hash,
                depth=state.depth + 1,
                path=state.path + [action],
                actions=new_actions
            )
            
            return new_state
            
        except Exception as e:
            logger.debug(f"Action execution failed: {e}")
            return None

    async def intercept_request(self, route):
        """Intercept and log HTTP requests"""
        request = route.request
        
        if self._is_static_resource(request.url):
            await route.continue_()
            return
        
        parsed = urlparse(request.url)
        
        if parsed.netloc != self.domain:
            await route.continue_()
            return
        
        # Log request
        endpoint = f"{request.method} {parsed.path}"
        self.unique_endpoints.add(request.url)
        self.unique_methods_paths.add(endpoint)
        self.request_count += 1
        
        logger.info(f"Request: {request.method} {parsed.path}")
        
        await route.continue_()

    async def _bfs_explore(self, page: Page):
        """Main BFS exploration loop"""
        # Start with initial state
        initial_dom_hash = await self._get_dom_hash(page)
        initial_actions = await self._extract_actions(page, None)
        
        initial_state = State(
            url=self.start_url,
            dom_hash=initial_dom_hash,
            depth=0,
            actions=initial_actions
        )
        
        self.visited_states.add(initial_state)
        self.state_queue.append(initial_state)
        
        logger.info(f"Starting BFS with initial state: {self.start_url}")
        logger.info(f"Queue size: {len(self.state_queue)}")
        
        while self.state_queue and (time.time() - self.start_time) < self.timeout:
            # Get next state from queue (BFS)
            current_state = self.state_queue.popleft()
            
            logger.info(f"Processing state {len(self.visited_states)}/{len(self.state_queue)}: {current_state.url} (depth={current_state.depth})")
            
            # Navigate to state URL
            try:
                if page.url != current_state.url:
                    await page.goto(current_state.url, wait_until="networkidle", timeout=10000)
                    await page.wait_for_timeout(500)
            except:
                logger.warning(f"Failed to navigate to {current_state.url}")
                continue
            
            # Execute actions from this state
            for action in current_state.actions[:20]:  # Limit actions per state
                if (time.time() - self.start_time) > self.timeout:
                    break
                
                self.action_count += 1
                
                # Execute action
                new_state = await self._execute_action(page, action, current_state)
                
                if new_state and new_state not in self.visited_states:
                    # New state discovered, add to queue
                    self.visited_states.add(new_state)
                    self.state_queue.append(new_state)
                    
                    logger.info(f"New state discovered and added to queue: {new_state.url}")
                    logger.info(f"Queue size: {len(self.state_queue)}, Visited: {len(self.visited_states)}")
                
                # Navigate back to original state for next action
                if page.url != current_state.url:
                    await page.goto(current_state.url, wait_until="networkidle", timeout=10000)
                    await page.wait_for_timeout(500)
            
            # Print progress
            elapsed = time.time() - self.start_time
            actions_per_sec = self.action_count / elapsed if elapsed > 0 else 0
            
            logger.info(f"Progress: {len(self.visited_states)} states, {self.action_count} actions, {self.request_count} requests, {actions_per_sec:.1f} actions/s")
            
            # Check for convergence
            if len(self.state_queue) == 0:
                logger.info("Queue empty, BFS complete")
                break

    async def scan(self):
        """Main scanning function"""
        logger.info(f"Starting scan: {self.start_url}")
        logger.info(f"Max depth: {self.max_depth}, Timeout: {self.timeout}s")
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=self.headless,
                args=[
                    '--no-sandbox',
                    '--disable-dev-shm-usage',
                    '--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                ]
            )
            
            context = await browser.new_context(
                ignore_https_errors=True,
                viewport={'width': 1920, 'height': 1080}
            )
            
            page = await context.new_page()
            
            # Setup request interception
            await page.route("**/*", lambda route: self.intercept_request(route))
            
            # Navigate to start URL
            await page.goto(self.start_url, wait_until="networkidle", timeout=30000)
            await page.wait_for_timeout(1000)
            
            # Run BFS exploration
            await self._bfs_explore(page)
            
            await browser.close()
        
        # Print results
        self._print_results()

    def _print_results(self):
        """Print scanning results"""
        elapsed = time.time() - self.start_time
        
        print("\n" + "="*80, file=sys.stderr)
        print("SCAN RESULTS", file=sys.stderr)
        print("="*80, file=sys.stderr)
        print(f"Time elapsed: {elapsed:.2f}s", file=sys.stderr)
        print(f"States visited: {len(self.visited_states)}", file=sys.stderr)
        print(f"Actions executed: {self.action_count}", file=sys.stderr)
        print(f"HTTP requests: {self.request_count}", file=sys.stderr)
        print(f"Unique endpoints: {len(self.unique_endpoints)}", file=sys.stderr)
        print(f"Unique methods/paths: {len(self.unique_methods_paths)}", file=sys.stderr)
        print(f"Unique parameters: {len(self.unique_params)}", file=sys.stderr)
        print("="*80, file=sys.stderr)
        
        if self.unique_methods_paths:
            print("\nDISCOVERED ENDPOINTS:", file=sys.stderr)
            for endpoint in sorted(self.unique_methods_paths):
                print(f"  {endpoint}", file=sys.stderr)
        
        if self.unique_params:
            print("\nDISCOVERED PARAMETERS:", file=sys.stderr)
            for param, value in sorted(self.unique_params):
                print(f"  {param} = {value}", file=sys.stderr)


async def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "No URL provided"}), file=sys.stderr)
        sys.exit(1)

    url = sys.argv[1]
    
    max_depth = 3
    timeout = 300
    
    scanner = PlaywrightScanner(
        url, 
        max_depth=max_depth,
        timeout=timeout,
        headless=True
    )

    try:
        await scanner.scan()
    except KeyboardInterrupt:
        print("\nScan interrupted by user", file=sys.stderr)
        scanner._print_results()
    except Exception as e:
        print(f"\nError: {e}", file=sys.stderr)
        scanner._print_results()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())