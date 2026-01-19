"""
User Behavior Simulator - Crawler that mimics real user to capture ALL network requests
"""
import asyncio
import json
import sys
import time
import hashlib
from urllib.parse import urlparse, urljoin
from collections import deque
from dataclasses import dataclass, field
from typing import Set, List, Deque, Dict, Any


@dataclass
class PageState:
    url: str
    dom_hash: str
    depth: int
    actions_taken: Set[str] = field(default_factory=set)


async def capture_all_requests(page, domain, captured_requests):
    """Setup to capture EVERY request including AJAX/fetch/XHR"""
    
    # Monkey-patch fetch to log requests
    await page.add_init_script("""
        // Capture fetch requests
        const originalFetch = window.fetch;
        window.fetch = async function(...args) {
            const [resource, config] = args;
            console.log('[FETCH]', resource, config?.method || 'GET', config?.body);
            return originalFetch.apply(this, args);
        };
        
        // Capture XMLHttpRequest
        const originalXHROpen = XMLHttpRequest.prototype.open;
        const originalXHRSend = XMLHttpRequest.prototype.send;
        
        XMLHttpRequest.prototype.open = function(method, url) {
            this._method = method;
            this._url = url;
            return originalXHROpen.apply(this, arguments);
        };
        
        XMLHttpRequest.prototype.send = function(body) {
            console.log('[XHR]', this._method, this._url, body);
            return originalXHRSend.apply(this, arguments);
        };
        
        // Log all click events
        document.addEventListener('click', function(e) {
            console.log('[CLICK]', e.target.tagName, e.target.className, e.target.id);
        }, true);
        
        // Log all form submissions
        document.addEventListener('submit', function(e) {
            console.log('[SUBMIT]', e.target.tagName, e.target.className, e.target.id);
        }, true);
    """)
    
    # Intercept ALL network requests
    async def intercept(route):
        request = route.request
        url = request.url
        
        # Skip only obvious static files
        static_exts = ['.css', '.woff', '.woff2', '.ttf', '.png', '.jpg', '.jpeg', '.gif', '.ico', '.svg']
        if any(url.lower().endswith(ext) for ext in static_exts):
            await route.continue_()
            return
        
        parsed = urlparse(url)
        
        # Capture request data
        req_data = {
            'timestamp': time.time(),
            'method': request.method,
            'url': url,
            'domain': parsed.netloc,
            'path': parsed.path,
            'headers': dict(request.headers),
            'post_data': request.post_data,
            'resource_type': request.resource_type,
            'frame_url': request.frame.url if request.frame else None,
        }
        
        # Output immediately
        print(json.dumps(req_data, ensure_ascii=False), flush=True)
        
        await route.continue_()
    
    await page.route("**/*", intercept)


async def get_dom_hash(page):
    """Get fingerprint of current DOM state"""
    try:
        return await page.evaluate("""
            () => {
                return document.documentElement.outerHTML.length + '|' + 
                       document.querySelectorAll('*').length;
            }
        """)
    except:
        return "error"


async def find_all_clickables(page, current_url):
    """Find ALL elements that can be clicked"""
    elements = []
    
    # Все возможные кликабельные элементы
    selectors = [
        "a[href]", 
        "button", 
        "input[type='submit']", 
        "input[type='button']",
        "[onclick]", 
        "[role='button']",
        "label[for]",  # Клик по label чекает checkbox/radio
        "summary",     # Для details/summary
        "[tabindex]:not([tabindex='-1'])",
        ".btn", ".button",  
        "li", "div", "span"  
    ]
    
    for selector in selectors:
        try:
            found = await page.query_selector_all(selector)
            for el in found[:100]:  # Ограничим, но много
                try:
                    if await el.is_visible():
                        # Получаем уникальный идентификатор
                        ident = await el.evaluate("""
                            el => {
                                if (el.id) return '#' + el.id;
                                if (el.name) return '[name="' + el.name + '"]';
                                if (el.className) {
                                    const cls = el.className.toString().split(' ')[0];
                                    if (cls) return '.' + cls;
                                }
                                return el.tagName + ':' + el.textContent?.slice(0, 20);
                            }
                        """)
                        
                        # Определяем тип действия
                        tag = await el.evaluate("el => el.tagName.toLowerCase()")
                        href = await el.get_attribute('href') if tag == 'a' else None
                        
                        elements.append({
                            'selector': ident,
                            'tag': tag,
                            'href': href,
                            'type': 'click'
                        })
                except:
                    continue
        except:
            continue
    
    return elements


async def find_all_forms(page):
    """Find ALL forms and their inputs"""
    forms = []
    try:
        form_elements = await page.query_selector_all('form')
        
        for form in form_elements:
            try:
                form_id = await form.get_attribute('id') or ''
                form_action = await form.get_attribute('action') or ''
                form_method = await form.get_attribute('method') or 'GET'
                
                # Находим все inputs в форме
                inputs = await form.query_selector_all('input, textarea, select')
                input_data = []
                
                for inp in inputs:
                    inp_type = await inp.get_attribute('type') or 'text'
                    inp_name = await inp.get_attribute('name') or ''
                    if inp_name:  # Только named inputs
                        input_data.append({
                            'name': inp_name,
                            'type': inp_type
                        })
                
                forms.append({
                    'selector': f"form#{form_id}" if form_id else 'form',
                    'action': form_action,
                    'method': form_method,
                    'inputs': input_data,
                    'type': 'form'
                })
            except:
                continue
    except:
        pass
    
    return forms


async def fill_and_submit_form(page, form_info):
    """Fill form with realistic data and submit"""
    try:
        form = await page.query_selector(form_info['selector'])
        if not form:
            return
        
        # Заполняем каждый input
        for inp_info in form_info['inputs']:
            input_sel = f"input[name='{inp_info['name']}'],textarea[name='{inp_info['name']}'],select[name='{inp_info['name']}']"
            inp = await page.query_selector(input_sel)
            if inp:
                inp_type = inp_info['type'].lower()
                
                if inp_type in ['text', 'search', 'url']:
                    await inp.fill('test')
                elif inp_type == 'email':
                    await inp.fill('test@test.com')
                elif inp_type == 'password':
                    await inp.fill('Password123!')
                elif inp_type == 'number':
                    await inp.fill('1')
                elif inp_type == 'tel':
                    await inp.fill('+1234567890')
                elif inp_type == 'checkbox':
                    await inp.click()
                elif inp_type == 'radio':
                    await inp.click()
                elif inp_type == 'date':
                    await inp.fill('2024-01-01')
                elif inp_type == 'hidden':
                    continue
                
                # Триггерим события для JS handlers
                await inp.dispatch_event('input')
                await inp.dispatch_event('change')
        
        # Ждем немного для JS валидации
        await asyncio.sleep(0.1)
        
        # Сабмитим форму
        await form.evaluate("form => form.submit()")
        
        # Ждем запросы
        await asyncio.sleep(0.5)
        
    except Exception as e:
        print(f"Form error: {e}", file=sys.stderr)


async def click_element(page, element_info):
    """Click on element and capture resulting requests"""
    try:
        element = await page.query_selector(element_info['selector'])
        if not element:
            return
        
        # Прокручиваем к элементу
        await element.scroll_into_view_if_needed()
        
        # Кликаем
        await element.click()
        
        # Ждем AJAX/requests
        await asyncio.sleep(0.3)
        
    except Exception as e:
        print(f"Click error: {e}", file=sys.stderr)


async def explore_page_fully(page, state, visited, queue, max_depth, domain):
    """Explore ALL interactive elements on current page"""
    current_url = page.url
    print(f"\n[EXPLORING] {current_url}", file=sys.stderr)
    
    # Ждем полной загрузки и динамического контента
    await asyncio.sleep(1)
    
    # Находим ВСЕ кликабельные элементы
    clickables = await find_all_clickables(page, current_url)
    forms = await find_all_forms(page)
    
    all_actions = clickables + forms
    print(f"[ACTIONS] Found {len(all_actions)} interactive elements", file=sys.stderr)
    
    # Выполняем ВСЕ действия
    for action in all_actions:
        action_id = f"{action['type']}:{action['selector']}"
        
        if action_id in state.actions_taken:
            continue
        
        # Сохраняем текущий URL перед действием
        original_url = page.url
        original_hash = await get_dom_hash(page)
        
        print(f"[ACTION] {action['type']}: {action['selector'][:50]}", file=sys.stderr)
        
        if action['type'] == 'form':
            await fill_and_submit_form(page, action)
        else:
            await click_element(page, action)
        
        state.actions_taken.add(action_id)
        
        # Ждем все фоновые запросы
        await asyncio.sleep(0.5)
        
        # Проверяем, изменилась ли страница (новая state)
        current_url_after = page.url
        current_hash = await get_dom_hash(page)
        
        # Если страница изменилась и мы не превысили глубину
        if (current_url_after != original_url or current_hash != original_hash):
            if urlparse(current_url_after).netloc == domain and state.depth < max_depth:
                new_state = PageState(
                    url=current_url_after,
                    dom_hash=current_hash,
                    depth=state.depth + 1
                )
                
                state_id = f"{current_url_after}:{current_hash}"
                if state_id not in visited:
                    visited.add(state_id)
                    queue.append(new_state)
                    print(f"[NEW STATE] {current_url_after} (depth: {new_state.depth})", file=sys.stderr)
        
        # Возвращаемся к исходной странице для следующего действия
        if page.url != original_url:
            await page.goto(original_url, wait_until="networkidle", timeout=10000)
            await asyncio.sleep(0.5)


async def bfs_crawl(start_url, max_depth=3):
    """Main BFS crawl that mimics real user"""
    from playwright.async_api import async_playwright
    
    domain = urlparse(start_url).netloc
    visited = set()
    queue = deque()
    captured_requests = []
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                '--no-sandbox',
                '--disable-dev-shm-usage',
                '--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            ]
        )
        
        context = await browser.new_context(
            ignore_https_errors=True,
            viewport={'width': 1920, 'height': 1080},
            java_script_enabled=True
        )
        
        page = await context.new_page()
        
        # Setup request capturing BEFORE anything else
        await capture_all_requests(page, domain, captured_requests)
        
        # Navigate to start URL
        print(f"[START] Navigating to {start_url}", file=sys.stderr)
        await page.goto(start_url, wait_until="networkidle", timeout=30000)
        await asyncio.sleep(2)  # Wait for all initial requests
        
        # Create initial state
        initial_hash = await get_dom_hash(page)
        initial_state = PageState(
            url=start_url,
            dom_hash=initial_hash,
            depth=0
        )
        
        visited.add(f"{start_url}:{initial_hash}")
        queue.append(initial_state)
        
        # BFS loop
        start_time = time.time()
        timeout = 600  # 10 minutes max
        
        while queue and (time.time() - start_time) < timeout:
            current_state = queue.popleft()
            
            # Navigate to this state's URL
            if page.url != current_state.url:
                await page.goto(current_state.url, wait_until="networkidle", timeout=10000)
                await asyncio.sleep(1)
            
            # Explore ALL actions on this page
            await explore_page_fully(page, current_state, visited, queue, max_depth, domain)
        
        await browser.close()
    
    print(f"\n[CRAWL COMPLETE]", file=sys.stderr)
    print(f"States visited: {len(visited)}", file=sys.stderr)
    print(f"Queue size: {len(queue)}", file=sys.stderr)


async def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "No URL provided"}))
        sys.exit(1)
    
    url = sys.argv[1]
    max_depth = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    
    try:
        await bfs_crawl(url, max_depth)
    except KeyboardInterrupt:
        print("\n[CRAWL INTERRUPTED]", file=sys.stderr)
    except Exception as e:
        print(f"\n[ERROR] {e}", file=sys.stderr)


if __name__ == "__main__":
    asyncio.run(main())