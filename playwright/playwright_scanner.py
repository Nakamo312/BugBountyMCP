"""
Enhanced Playwright crawler with deep DOM analysis, form discovery, and state-aware crawling
"""
import asyncio
import json
import logging
import sys
import hashlib
import re
from typing import Set, Dict, Any, List, Optional, Tuple
from urllib.parse import urlparse, parse_qs, urljoin
from dataclasses import dataclass, field
from collections import deque, defaultdict
import time

from playwright.async_api import async_playwright, Page, Route, Response, ElementHandle, Request

# ---------------- Enhanced Logging ----------------
class Colors:
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    RESET = '\033[0m'

class ColorFormatter(logging.Formatter):
    LEVEL_COLORS = {
        'INFO': Colors.GREEN,
        'WARNING': Colors.YELLOW,
        'ERROR': Colors.RED,
        'DEBUG': Colors.BLUE,
        'FORM': Colors.CYAN,
        'STATE': Colors.MAGENTA
    }
    
    def format(self, record):
        timestamp = self.formatTime(record, '%H:%M:%S')
        level = record.levelname
        color = self.LEVEL_COLORS.get(level, Colors.RESET)
        return f"[{timestamp}] [{color}{level:8}{Colors.RESET}] {record.getMessage()}"

logger = logging.getLogger("deep_crawler")
logger.setLevel(logging.DEBUG)
handler = logging.StreamHandler()
handler.setFormatter(ColorFormatter())
logger.addHandler(handler)

# Custom log levels for form and state discovery
logging.addLevelName(25, "FORM")
logging.addLevelName(26, "STATE")

def log_form(msg, *args, **kwargs):
    logger.log(25, msg, *args, **kwargs)

def log_state(msg, *args, **kwargs):
    logger.log(26, msg, *args, **kwargs)

# ---------------- Extended Constants ----------------
STATIC_EXTENSIONS = {
    ".css", ".svg", ".png", ".jpg", ".jpeg", ".gif", ".ico", ".webp",
    ".woff", ".woff2", ".ttf", ".eot", ".otf",
    ".mp4", ".mp3", ".avi", ".webm", ".flv", ".wav", ".ogg",
    ".pdf", ".zip", ".tar", ".gz", ".rar", ".7z",
    ".exe", ".dll", ".bin", ".dmg", ".iso",
    ".map", ".min.js", ".min.css"
}

# Form-related patterns
FORM_KEYWORDS = ['login', 'signup', 'register', 'auth', 'submit', 'create', 
                 'update', 'delete', 'post', 'put', 'send', 'save', 'upload',
                 'comment', 'message', 'contact', 'search', 'filter', 'apply']

# ---------------- Enhanced Data Classes ----------------
@dataclass
class FormData:
    """Represents a discovered form with all its fields"""
    id: str
    action: str
    method: str = "GET"
    enctype: str = "application/x-www-form-urlencoded"
    fields: Dict[str, Dict] = field(default_factory=dict)
    buttons: List[Dict] = field(default_factory=list)
    javascript_handlers: List[str] = field(default_factory=list)
    xhr_endpoints: Set[str] = field(default_factory=set)
    discovered_at: str = ""
    submitted: bool = False
    
    def get_signature(self) -> str:
        """Create unique signature for form deduplication"""
        field_names = ','.join(sorted(self.fields.keys()))
        return f"{self.method}:{self.action}:{field_names}"

@dataclass
class Action:
    selector: str
    action_type: str  # click, form_submit, xhr_trigger, state_change
    element_data: Dict[str, Any]
    semantic: str = "unknown"
    priority: int = 1  # 1-5, where 5 is highest
    
    def __hash__(self):
        return hash((self.selector, self.action_type, self.semantic))
    
    def __eq__(self, other):
        return isinstance(other, Action) and hash(self) == hash(other)

@dataclass
class State:
    url: str
    dom_signature: str
    form_signatures: Set[str] = field(default_factory=set)
    discovered_forms: List[FormData] = field(default_factory=list)
    depth: int = 0
    actions_taken: List[Action] = field(default_factory=list)
    
    def get_fingerprint(self) -> str:
        """More robust fingerprint including forms"""
        form_sig = ','.join(sorted(self.form_signatures))
        return f"{self.url}:{self.dom_signature}:{form_sig}"

# ---------------- Enhanced Scanner ----------------
class PlaywrightScanner:
    def __init__(self, start_url: str, max_depth: int = 5, timeout: int = 300):
        self.start_url = start_url
        self.max_depth = max_depth
        self.timeout = timeout
        
        # State tracking
        self.visited_states: Set[str] = set()
        self.state_queue: deque[State] = deque()
        self.all_discovered_forms: Dict[str, FormData] = {}
        self.results: List[Dict] = []
        
        # Performance tracking
        self.request_count = 0
        self.form_submissions = 0
        self.xhr_captures = 0
        
        # JavaScript analysis
        self.js_event_listeners: Dict[str, List[str]] = defaultdict(list)
        self.dynamic_endpoints: Set[str] = set()

    # ---------------- Enhanced DOM Analysis ----------------
    async def _analyze_dom_deeply(self, page: Page) -> Tuple[str, List[FormData]]:
        """Deep analysis of DOM for forms and interactive elements"""
        
        # 1. Find ALL forms (including hidden, dynamically created)
        forms_data = await self._extract_all_forms(page)
        
        # 2. Find JavaScript event listeners
        await self._extract_js_listeners(page)
        
        # 3. Find AJAX/fetch endpoints in JavaScript
        await self._extract_js_endpoints(page)
        
        # 4. Create comprehensive DOM signature
        dom_signature = await self._create_dom_signature(page, forms_data)
        
        log_state(f"Found {len(forms_data)} forms, {len(self.js_event_listeners)} JS listeners")
        
        return dom_signature, forms_data
    
    async def _extract_all_forms(self, page: Page) -> List[FormData]:
        """Extract forms including those created by JavaScript"""
        forms = []
        
        # Method 1: Standard HTML forms
        form_elements = await page.query_selector_all("form")
        for form_el in form_elements:
            try:
                form_data = await self._analyze_html_form(form_el)
                if form_data:
                    forms.append(form_data)
                    log_form(f"Found HTML form: {form_data.method} {form_data.action}")
            except Exception as e:
                logger.debug(f"Error analyzing form: {e}")
        
        # Method 2: JavaScript-created forms (divs with form-like behavior)
        potential_forms = await page.query_selector_all(
            "div[class*='form'], div[class*='Form'], "
            "section[class*='form'], [role='form']"
        )
        
        for div in potential_forms:
            try:
                # Check if this div behaves like a form
                has_inputs = await div.query_selector_all("input, textarea, select")
                has_buttons = await div.query_selector_all("button, [type='submit']")
                
                if len(has_inputs) > 0 or len(has_buttons) > 0:
                    form_data = await self._analyze_div_form(div)
                    if form_data:
                        forms.append(form_data)
                        log_form(f"Found div-based form: {form_data.id}")
            except:
                continue
        
        # Method 3: Single input "forms" (like search boxes)
        standalone_inputs = await page.query_selector_all(
            "input[type='text'], input[type='search'], input[type='email']"
        )
        
        for inp in standalone_inputs[:10]:  # Limit to prevent explosion
            try:
                # Check if input is inside a form already
                parent_form = await inp.evaluate_handle("el => el.closest('form')")
                if parent_form.as_element():
                    continue
                    
                # Check for nearby submit elements
                form_data = await self._analyze_standalone_input(inp)
                if form_data:
                    forms.append(form_data)
                    log_form(f"Found standalone input form: {form_data.id}")
            except:
                continue
        
        return forms
    
    async def _analyze_html_form(self, form_el: ElementHandle) -> Optional[FormData]:
        """Analyze standard HTML form element"""
        try:
            form_id = await form_el.get_attribute("id") or f"form_{hash(form_el)}"
            action = await form_el.get_attribute("action") or ""
            method = (await form_el.get_attribute("method") or "GET").upper()
            enctype = await form_el.get_attribute("enctype") or "application/x-www-form-urlencoded"
            
            # Get current page URL for relative actions
            page_url = await form_el.owner_frame().url()
            if action and not action.startswith(('http://', 'https://')):
                action = urljoin(page_url, action)
            
            form_data = FormData(
                id=form_id,
                action=action or page_url,
                method=method,
                enctype=enctype,
                discovered_at=page_url
            )
            
            # Extract all input fields
            inputs = await form_el.query_selector_all(
                "input:not([type='hidden']), textarea, select"
            )
            
            for inp in inputs:
                try:
                    field_name = await inp.get_attribute("name") or await inp.get_attribute("id") or ""
                    field_type = await inp.get_attribute("type") or "text"
                    field_value = await inp.get_attribute("value") or ""
                    
                    if field_name:
                        form_data.fields[field_name] = {
                            "type": field_type,
                            "value": field_value,
                            "required": await inp.get_attribute("required") is not None
                        }
                except:
                    continue
            
            # Extract hidden fields separately (often contain tokens)
            hidden_inputs = await form_el.query_selector_all("input[type='hidden']")
            for inp in hidden_inputs:
                try:
                    name = await inp.get_attribute("name")
                    value = await inp.get_attribute("value") or ""
                    if name:
                        form_data.fields[name] = {
                            "type": "hidden",
                            "value": value,
                            "required": False
                        }
                except:
                    continue
            
            # Find submit buttons
            submit_elements = await form_el.query_selector_all(
                "button, input[type='submit'], input[type='image']"
            )
            for btn in submit_elements:
                try:
                    btn_type = await btn.get_attribute("type") or "submit"
                    btn_name = await btn.get_attribute("name") or ""
                    btn_value = await btn.get_attribute("value") or ""
                    
                    form_data.buttons.append({
                        "type": btn_type,
                        "name": btn_name,
                        "value": btn_value
                    })
                except:
                    continue
            
            # Look for JavaScript form handlers
            js_handlers = await form_el.evaluate("""
                el => {
                    const handlers = [];
                    for (const attr of el.getAttributeNames()) {
                        if (attr.startsWith('on')) handlers.push(attr);
                    }
                    return handlers;
                }
            """)
            form_data.javascript_handlers = js_handlers
            
            return form_data
            
        except Exception as e:
            logger.debug(f"Error in form analysis: {e}")
            return None
    
    async def _analyze_div_form(self, div_el: ElementHandle) -> Optional[FormData]:
        """Analyze div-based 'form' (common in SPAs)"""
        try:
            # Generate unique ID
            div_id = await div_el.get_attribute("id") or f"div_form_{hash(div_el)}"
            
            # Look for data-action or similar attributes
            data_action = await div_el.get_attribute("data-action")
            page_url = await div_el.owner_frame().url()
            
            form_data = FormData(
                id=div_id,
                action=data_action or page_url,
                method="POST",  # Assume POST for div forms
                enctype="application/json",  # Common for SPA forms
                discovered_at=page_url
            )
            
            # Extract input fields within this div
            inputs = await div_el.query_selector_all(
                "input, textarea, select, [contenteditable='true']"
            )
            
            for inp in inputs:
                try:
                    # Try various ways to get field identifier
                    field_name = (
                        await inp.get_attribute("name") or 
                        await inp.get_attribute("id") or 
                        await inp.get_attribute("data-name") or
                        await inp.get_attribute("aria-label") or
                        f"field_{hash(inp)}"
                    )
                    
                    field_type = await inp.get_attribute("type") or "text"
                    
                    form_data.fields[field_name] = {
                        "type": field_type,
                        "value": "",
                        "required": await inp.get_attribute("required") is not None
                    }
                except:
                    continue
            
            # Look for buttons that might submit this "form"
            buttons = await div_el.query_selector_all(
                "button, [role='button'], [data-submit], [data-action='submit']"
            )
            
            for btn in buttons:
                try:
                    btn_text = await btn.text_content() or ""
                    btn_action = await btn.get_attribute("data-action")
                    
                    form_data.buttons.append({
                        "type": "button",
                        "text": btn_text[:50],
                        "action": btn_action
                    })
                except:
                    continue
            
            return form_data
            
        except Exception as e:
            logger.debug(f"Error analyzing div form: {e}")
            return None
    
    async def _analyze_standalone_input(self, input_el: ElementHandle) -> Optional[FormData]:
        """Analyze standalone input that might be a form"""
        try:
            # Check if there's a submit mechanism nearby
            page_url = await input_el.owner_frame().url()
            
            # Look for a submit button within a reasonable distance in DOM
            submit_candidate = await input_el.evaluate_handle("""
                el => {
                    // Look in parent elements
                    let current = el.parentElement;
                    for (let i = 0; i < 3 && current; i++) {
                        const submitBtn = current.querySelector('button, input[type="submit"]');
                        if (submitBtn) return submitBtn;
                        current = current.parentElement;
                    }
                    return null;
                }
            """)
            
            if submit_candidate.as_element():
                form_id = f"standalone_{hash(input_el)}"
                field_name = await input_el.get_attribute("name") or await input_el.get_attribute("id") or "input"
                
                form_data = FormData(
                    id=form_id,
                    action=page_url,
                    method="GET",  # Common for search-like inputs
                    enctype="application/x-www-form-urlencoded",
                    discovered_at=page_url
                )
                
                form_data.fields[field_name] = {
                    "type": await input_el.get_attribute("type") or "text",
                    "value": "",
                    "required": False
                }
                
                return form_data
                
        except Exception as e:
            logger.debug(f"Error analyzing standalone input: {e}")
        
        return None
    
    # ---------------- JavaScript Analysis ----------------
    async def _extract_js_listeners(self, page: Page):
        """Extract JavaScript event listeners from the page"""
        try:
            listeners = await page.evaluate("""
                () => {
                    const allListeners = {};
                    
                    // Get all elements with event listeners
                    const allElements = document.querySelectorAll('*');
                    
                    allElements.forEach(el => {
                        const elListeners = [];
                        
                        // Check for on* attributes
                        for (const attr of el.getAttributeNames()) {
                            if (attr.startsWith('on') && attr.length > 2) {
                                elListeners.push(attr);
                            }
                        }
                        
                        // Check for addEventListener (limited detection)
                        if (el.__events) {
                            for (const eventType in el.__events) {
                                elListeners.push(eventType);
                            }
                        }
                        
                        if (elListeners.length > 0) {
                            const selector = (el.id ? '#' + el.id : 
                                            el.className ? '.' + el.className.split(' ')[0] : 
                                            el.tagName.toLowerCase());
                            allListeners[selector] = elListeners;
                        }
                    });
                    
                    return allListeners;
                }
            """)
            
            self.js_event_listeners.update(listeners)
            
        except Exception as e:
            logger.debug(f"Could not extract JS listeners: {e}")
    
    async def _extract_js_endpoints(self, page: Page):
        """Extract API endpoints from JavaScript code"""
        try:
            # Get all script tags content
            scripts = await page.query_selector_all("script")
            
            for script in scripts:
                try:
                    content = await script.text_content()
                    if not content:
                        continue
                    
                    # Look for URLs in JavaScript
                    url_patterns = [
                        r'["\'](https?://[^"\'\s]+)["\']',
                        r'["\'](/[^"\'\s]+)["\']',
                        r'fetch\(["\']([^"\']+)["\']',
                        r'axios\.(get|post|put|delete)\(["\']([^"\']+)["\']',
                        r'\.ajax\([^{]*url:\s*["\']([^"\']+)["\']'
                    ]
                    
                    for pattern in url_patterns:
                        matches = re.findall(pattern, content, re.IGNORECASE)
                        for match in matches:
                            if isinstance(match, tuple):
                                url = match[1] if len(match) > 1 else match[0]
                            else:
                                url = match
                            
                            if not any(url.endswith(ext) for ext in STATIC_EXTENSIONS):
                                self.dynamic_endpoints.add(url)
                                
                except:
                    continue
                    
        except Exception as e:
            logger.debug(f"Could not extract JS endpoints: {e}")
    
    # ---------------- Form Submission ----------------
    async def _submit_form_intelligently(self, page: Page, form_data: FormData) -> bool:
        """Intelligently submit form with appropriate data"""
        try:
            # Fill form with realistic test data
            await self._fill_form_with_data(page, form_data)
            
            # Take screenshot before submission for debugging
            screenshot_path = f"form_{form_data.id}_{int(time.time())}.png"
            await page.screenshot(path=screenshot_path, full_page=False)
            
            # Submit the form
            if form_data.method == "GET":
                # For GET forms, we might need to click a submit button
                if form_data.buttons:
                    first_button = form_data.buttons[0]
                    if first_button.get('name'):
                        selector = f"[name='{first_button['name']}']"
                    else:
                        selector = "button, input[type='submit']"
                    
                    await page.click(selector)
                else:
                    # Just press Enter in the first input
                    await page.press("input, textarea, select", "Enter")
            else:
                # For POST forms, look for submit mechanism
                submit_selectors = [
                    "input[type='submit']",
                    "button[type='submit']",
                    "button:has-text('Submit')",
                    "button:has-text('Send')",
                    "button:has-text('Save')",
                    "[data-submit]"
                ]
                
                submitted = False
                for selector in submit_selectors:
                    try:
                        await page.click(selector, timeout=2000)
                        submitted = True
                        break
                    except:
                        continue
                
                if not submitted:
                    # Fallback: press Enter
                    await page.press("input, textarea, select", "Enter")
            
            # Wait for navigation or network activity
            try:
                await page.wait_for_load_state("networkidle", timeout=5000)
            except:
                pass
            
            form_data.submitted = True
            self.form_submissions += 1
            
            log_form(f"Submitted form {form_data.id} via {form_data.method} to {form_data.action}")
            return True
            
        except Exception as e:
            logger.error(f"Error submitting form {form_data.id}: {e}")
            return False
    
    async def _fill_form_with_data(self, page: Page, form_data: FormData):
        """Fill form fields with appropriate test data"""
        test_data = {
            'email': 'test@example.com',
            'username': 'testuser',
            'password': 'TestPassword123!',
            'name': 'Test User',
            'first_name': 'Test',
            'last_name': 'User',
            'phone': '+1234567890',
            'message': 'This is a test message',
            'comment': 'Test comment',
            'search': 'test query',
            'title': 'Test Title',
            'description': 'Test description',
            'content': 'Test content',
            'url': 'https://example.com',
            'address': '123 Test Street',
            'city': 'Test City',
            'zip': '12345',
            'country': 'US'
        }
        
        for field_name, field_info in form_data.fields.items():
            field_lower = field_name.lower()
            field_type = field_info.get('type', 'text')
            
            # Find appropriate test value
            test_value = ""
            for key, value in test_data.items():
                if key in field_lower:
                    test_value = value
                    break
            
            if not test_value:
                # Type-based fallback
                if field_type in ['email', 'mail']:
                    test_value = test_data['email']
                elif field_type == 'password':
                    test_value = test_data['password']
                elif 'phone' in field_lower or field_type == 'tel':
                    test_value = test_data['phone']
                elif field_type == 'url':
                    test_value = test_data['url']
                elif field_type in ['number', 'range']:
                    test_value = '1'
                elif field_type == 'checkbox':
                    test_value = 'checked'
                else:
                    test_value = f"test_{field_name}"
            
            # Try to fill the field
            try:
                selector = f"[name='{field_name}'], [id='{field_name}']"
                await page.fill(selector, test_value)
                
                # Trigger change events
                await page.dispatch_event(selector, 'change')
                await page.dispatch_event(selector, 'input')
                
                logger.debug(f"Filled field {field_name} with {test_value[:20]}...")
            except Exception as e:
                logger.debug(f"Could not fill field {field_name}: {e}")
    
    # ---------------- Enhanced Request Interception ----------------
    async def intercept_request(self, route: Route):
        """Intercept and analyze all requests"""
        request = route.request
        
        # Skip static resources
        if any(request.url.endswith(ext) for ext in STATIC_EXTENSIONS):
            await route.continue_()
            return
        
        # Analyze request
        request_data = {
            "method": request.method,
            "url": request.url,
            "headers": dict(request.headers),
            "post_data": request.post_data,
            "resource_type": request.resource_type,
            "frame": request.frame.url if request.frame else None
        }
        
        # Store for response correlation
        request_key = f"{request.method}:{request.url}:{hash(request.post_data or '')}"
        self.pending_requests[request_key] = request_data
        
        # Continue the request
        await route.continue_()
    
    async def handle_response(self, response: Response):
        """Handle and analyze responses"""
        try:
            request = response.request
            request_key = f"{request.method}:{request.url}:{hash(request.post_data or '')}"
            
            if request_key in self.pending_requests:
                request_data = self.pending_requests.pop(request_key)
                
                # Try to get response body for non-binary responses
                response_body = ""
                try:
                    if response.ok and 'text' in response.headers.get('content-type', ''):
                        response_body = await response.text()
                except:
                    pass
                
                result = {
                    "timestamp": time.time(),
                    "request": request_data,
                    "response": {
                        "url": response.url,
                        "status": response.status,
                        "headers": dict(response.headers),
                        "body_preview": response_body[:1000] if response_body else "",
                        "body_length": len(response_body) if response_body else 0
                    }
                }
                
                self.results.append(result)
                self.request_count += 1
                
                # Output as JSON for pipeline processing
                print(json.dumps(result, default=str), flush=True)
                
                # Log interesting findings
                if response.status >= 400:
                    logger.warning(f"HTTP {response.status} for {request.method} {request.url}")
                elif request.method in ['POST', 'PUT', 'DELETE']:
                    log_form(f"Captured {request.method} to {request.url}")
                
        except Exception as e:
            logger.error(f"Error handling response: {e}")
    
    # ---------------- Main Exploration Loop ----------------
    async def explore_state(self, page: Page, state: State):
        """Explore a single state deeply"""
        logger.info(f"Exploring state at depth {state.depth}: {state.url}")
        
        # 1. Submit all discovered forms
        for form_data in state.discovered_forms:
            if not form_data.submitted and form_data.id not in self.all_discovered_forms:
                success = await self._submit_form_intelligently(page, form_data)
                if success:
                    self.all_discovered_forms[form_data.id] = form_data
                    
                    # Wait for state to stabilize
                    await asyncio.sleep(1)
                    
                    # Capture new state
                    new_dom_sig, new_forms = await self._analyze_dom_deeply(page)
                    new_url = page.url
                    
                    if state.depth < self.max_depth:
                        new_state = State(
                            url=new_url,
                            dom_signature=new_dom_sig,
                            form_signatures={f.get_signature() for f in new_forms},
                            discovered_forms=new_forms,
                            depth=state.depth + 1,
                            actions_taken=state.actions_taken.copy()
                        )
                        
                        state_fingerprint = new_state.get_fingerprint()
                        if state_fingerprint not in self.visited_states:
                            self.visited_states.add(state_fingerprint)
                            self.state_queue.append(new_state)
                            log_state(f"Discovered new state at depth {new_state.depth}")
        
        # 2. Trigger JavaScript events
        await self._trigger_js_events(page)
        
        # 3. Explore dynamic endpoints found in JS
        await self._explore_dynamic_endpoints(page)
    
    async def _trigger_js_events(self, page: Page):
        """Trigger JavaScript event listeners to discover hidden functionality"""
        for selector, events in self.js_event_listeners.items():
            for event in events[:3]:  # Limit to 3 events per element
                try:
                    # Skip common events we already handle
                    if event in ['onclick', 'onsubmit', 'onchange']:
                        continue
                    
                    logger.debug(f"Triggering {event} on {selector}")
                    
                    # Trigger the event
                    await page.evaluate(f"""
                        (selector, eventName) => {{
                            const el = document.querySelector(selector);
                            if (el) {{
                                const event = new Event(eventName.replace('on', ''), {{ bubbles: true }});
                                el.dispatchEvent(event);
                            }}
                        }}
                    """, selector, event)
                    
                    await asyncio.sleep(0.5)
                    
                except Exception as e:
                    logger.debug(f"Could not trigger {event} on {selector}: {e}")
    
    async def _explore_dynamic_endpoints(self, page: Page):
        """Make requests to dynamically discovered endpoints"""
        for endpoint in list(self.dynamic_endpoints)[:10]:  # Limit exploration
            try:
                # Skip if already visited
                if endpoint in self.visited_endpoints:
                    continue
                
                logger.info(f"Exploring dynamic endpoint: {endpoint}")
                
                # Try different HTTP methods
                methods = ['GET', 'POST', 'PUT', 'DELETE']
                for method in methods:
                    try:
                        # Make the request
                        response = await page.request.fetch(
                            endpoint,
                            method=method,
                            headers={'X-Test': 'true'},
                            timeout=5000
                        )
                        
                        logger.debug(f"{method} {endpoint} -> {response.status}")
                        
                        # Mark as visited
                        self.visited_endpoints.add(endpoint)
                        
                        # Short delay
                        await asyncio.sleep(0.5)
                        
                    except Exception as e:
                        logger.debug(f"Failed {method} {endpoint}: {e}")
                        
            except Exception as e:
                logger.debug(f"Error exploring endpoint {endpoint}: {e}")
    
    # ---------------- Main Scan Method ----------------
    async def scan(self):
        """Main scanning entry point"""
        logger.info(f"Starting deep scan of {self.start_url}")
        
        async with async_playwright() as p:
            # Launch browser with more capabilities
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    '--disable-web-security',
                    '--disable-features=IsolateOrigins,site-per-process',
                    '--aggressive-cache-discard',
                    '--disable-cache',
                    '--disable-application-cache',
                    '--disable-offline-load-stale-cache',
                    '--disk-cache-size=0'
                ]
            )
            
            context = await browser.new_context(
                ignore_https_errors=True,
                viewport={'width': 1280, 'height': 800},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )
            
            page = await context.new_page()
            
            # Set up interception
            await page.route("**/*", self.intercept_request)
            page.on("response", self.handle_response)
            
            # Navigate to start URL
            await page.goto(self.start_url, wait_until="networkidle", timeout=30000)
            
            # Initial deep analysis
            initial_dom_sig, initial_forms = await self._analyze_dom_deeply(page)
            initial_state = State(
                url=self.start_url,
                dom_signature=initial_dom_sig,
                form_signatures={f.get_signature() for f in initial_forms},
                discovered_forms=initial_forms,
                depth=0
            )
            
            self.visited_states.add(initial_state.get_fingerprint())
            self.state_queue.append(initial_state)
            
            # Main exploration loop
            iteration = 0
            while self.state_queue and iteration < 50:  # Safety limit
                state = self.state_queue.popleft()
                
                # Navigate to state URL if different
                if page.url != state.url:
                    await page.goto(state.url, wait_until="networkidle", timeout=10000)
                
                await self.explore_state(page, state)
                
                iteration += 1
                
                # Progress logging
                if iteration % 5 == 0:
                    logger.info(
                        f"Progress: {iteration} iterations, "
                        f"{len(self.visited_states)} states, "
                        f"{self.form_submissions} forms submitted, "
                        f"{self.request_count} requests captured"
                    )
            
            # Final cleanup
            await browser.close()
        
        # Summary
        logger.info("=" * 60)
        logger.info("SCAN COMPLETE")
        logger.info(f"Total requests captured: {self.request_count}")
        logger.info(f"Forms discovered: {len(self.all_discovered_forms)}")
        logger.info(f"Forms submitted: {self.form_submissions}")
        logger.info(f"Unique states visited: {len(self.visited_states)}")
        logger.info(f"Dynamic endpoints found: {len(self.dynamic_endpoints)}")
        logger.info("=" * 60)

# ---------------- Runner ----------------
async def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "No URL provided"}), file=sys.stderr)
        sys.exit(1)
    
    url = sys.argv[1]
    max_depth = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    
    scanner = DeepPlaywrightScanner(url, max_depth=max_depth)
    await scanner.scan()

if __name__ == "__main__":
    asyncio.run(main())