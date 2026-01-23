import asyncio
import json
import logging
import sys
import hashlib
from typing import Set, Dict, Any, List, Tuple
from urllib.parse import urlparse, parse_qs
from dataclasses import dataclass, field

from collections import deque

try:
    from playwright.async_api import async_playwright, Page, Route, Response, ElementHandle
except ImportError:
    print(json.dumps({"error": "playwright not installed. Run: pip install playwright && playwright install"}), file=sys.stderr)
    sys.exit(1)

STATIC_EXTENSIONS = {".css", ".svg", ".png", ".jpg", ".jpeg", ".gif", ".ico", ".webp", ".woff", ".woff2", ".ttf", ".eot", ".otf", ".mp4", ".mp3", ".avi", ".webm", ".flv", ".wav", ".ogg", ".pdf", ".zip", ".tar", ".gz", ".rar", ".7z", ".exe", ".dll", ".bin", ".dmg", ".iso", ".map", ".min.js", ".min.css"}

logger = logging.getLogger("playwright_scanner")
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s", datefmt="%H:%M:%S"))
logger.addHandler(handler)

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
    visited_count: int = 0

    def get_fingerprint(self):
        parsed = urlparse(self.url)
        normalized_url = f"{parsed.netloc}{parsed.path}"
        query_keys = frozenset(parse_qs(parsed.query).keys()) if parsed.query else frozenset()
        action_signature = hash(frozenset(a.get_cluster_key() for a in self.actions))
        dom_vector_str = json.dumps(sorted(self.dom_vector.items()), sort_keys=True)
        dom_hash = hashlib.sha256(dom_vector_str.encode()).hexdigest()[:16]
        return (normalized_url, query_keys, self.cookies_hash, self.storage_hash, dom_hash, action_signature)

    def get_semantic_key(self):
        parsed = urlparse(self.url)
        normalized_url = f"{parsed.netloc}{parsed.path}"
        key_features = {
            'forms': self.dom_vector.get('forms', 0),
            'buttons': self.dom_vector.get('buttons', 0),
            'links': self.dom_vector.get('links', 0),
        }
        return f"{normalized_url}:{key_features['forms']}:{key_features['buttons']}:{key_features['links']}"

class PlaywrightScanner:
    def __init__(self, url: str, max_depth: int = 2, max_actions_per_state: int = 20, max_path_length: int = 10):
        self.start_url = url
        self.max_depth = max_depth
        self.max_actions_per_state = max_actions_per_state
        self.max_path_length = max_path_length

        # Tracking
        self.visited_states: Set[Tuple] = set()
        self.semantic_states: Set[str] = set()
        self.visited_sequences: Set[str] = set()

        self.unique_endpoints: Set[str] = set()
        self.results: List[Dict[str, Any]] = []

        self.request_count = 0

    def _is_static_resource(self, url: str) -> bool:
        lower_url = url.lower().split('?')[0]
        return any(lower_url.endswith(ext) for ext in STATIC_EXTENSIONS)

    async def _get_dom_vector(self, page: Page) -> Dict[str, int]:
        return await page.evaluate("""
            () => {
                const v = {};
                const inc = k => v[k] = (v[k] || 0) + 1;
                const importantTags = ['form','input','button','a','select','textarea','nav'];
                importantTags.forEach(tag => inc(tag + ':' + document.querySelectorAll(tag).length));
                inc('forms:' + document.forms.length);
                inc('buttons:' + document.querySelectorAll('button,[role="button"]').length);
                inc('links:' + document.querySelectorAll('a').length);
                return v;
            }
        """)

    async def _get_state_fingerprint(self, page: Page):
        cookies = await page.context.cookies()
        cookies_hash = hashlib.sha256(json.dumps(cookies, sort_keys=True).encode()).hexdigest()[:16]
        storage = await page.evaluate("""() => JSON.stringify({ localStorage: {...localStorage}, sessionStorage: {...sessionStorage} })""")
        storage_hash = hashlib.sha256(storage.encode()).hexdigest()[:16]
        dom_vector = await self._get_dom_vector(page)
        dom_hash = hashlib.sha256(json.dumps(sorted(dom_vector.items()), sort_keys=True).encode()).hexdigest()[:16]
        return dom_hash, dom_vector, cookies_hash, storage_hash

    async def _extract_actions(self, page: Page) -> Set[Action]:
        actions = set()
        elements = await page.query_selector_all("button, a, input[type=submit], [role=button]")
        for el in elements[:self.max_actions_per_state]:
            try:
                if not await el.is_visible() or not await el.is_enabled():
                    continue
                text = (await el.text_content() or '').strip()[:50]
                tag = await el.evaluate('el => el.tagName.toLowerCase()')
                selector = await el.evaluate('el => el.tagName.toLowerCase() + (el.id ? "#" + el.id : "")')
                actions.add(Action(selector=selector, text=text, tag=tag))
            except:
                pass
        return actions

    async def _execute_action(self, page: Page, action: Action) -> bool:
        try:
            el = await page.query_selector(action.selector)
            if el and await el.is_visible():
                await el.click(timeout=1000)
                await page.wait_for_timeout(300)
                return True
        except:
            return False

    async def _should_skip_state(self, state: State) -> bool:
        fp = state.get_fingerprint()
        seq = ':'.join(a.get_cluster_key() for a in state.path)
        sk = state.get_semantic_key()
        if fp in self.visited_states or sk in self.semantic_states or seq in self.visited_sequences:
            return True
        if state.depth > self.max_depth or len(state.path) > self.max_path_length:
            return True
        return False

    async def _explore_state_recursive(self, page: Page, state: State, prohibited_states: Set[Tuple]):
        if await self._should_skip_state(state) or state.get_fingerprint() in prohibited_states:
            return

        self.visited_states.add(state.get_fingerprint())
        self.semantic_states.add(state.get_semantic_key())
        seq_key = ':'.join(a.get_cluster_key() for a in state.path)
        self.visited_sequences.add(seq_key)

        actions = state.actions
        for action in actions:
            success = await self._execute_action(page, action)
            if not success:
                state.dead_actions.add(action)
                continue

            new_url = page.url
            dom_hash, dom_vector, cookies_hash, storage_hash = await self._get_state_fingerprint(page)
            new_actions = await self._extract_actions(page)

            new_state = State(
                url=new_url,
                dom_hash=dom_hash,
                dom_vector=dom_vector,
                cookies_hash=cookies_hash,
                storage_hash=storage_hash,
                depth=state.depth+1,
                path=state.path + [action],
                actions=new_actions
            )

            await self._explore_state_recursive(page, new_state, prohibited_states)

    async def scan(self):
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context()
            page = await context.new_page()

            await page.goto(self.start_url, wait_until='networkidle')

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

            prohibited_states = set()
            await self._explore_state_recursive(page, initial_state, prohibited_states)

            await browser.close()

async def main():
    url = sys.argv[1] if len(sys.argv) > 1 else ''
    if not url:
        print(json.dumps({"error": "No URL provided"}), file=sys.stderr)
        sys.exit(1)

    scanner = PlaywrightScanner(url)
    await scanner.scan()

if __name__ == '__main__':
    asyncio.run(main())
