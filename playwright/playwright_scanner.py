"""
Playwright-based state-aware web crawler with BFS exploration.
Tracks DOM states to avoid infinite loops and maximize coverage.
"""
import asyncio
import json
import sys
from typing import Set, Dict, Tuple
from urllib.parse import urlparse
from collections import deque, defaultdict

from crawler.dom import (
    classify_action_semantic,
    dom_similarity,
    fill_forms,
    generate_selector,
    get_dom_hash,
    get_dom_vector,
    get_state_fingerprint,
)
from crawler.network import NetworkCapture
from crawler.state_match import state_observation_mismatch
from crawler.models import Action, State
from crawler.scanner_logging import logger

try:
    from playwright.async_api import (
        async_playwright,
        Page,
        ElementHandle,
        Error as PlaywrightError,
        TimeoutError as PlaywrightTimeoutError,
    )
except ImportError:
    print(json.dumps({"error": "playwright not installed. Run: pip install playwright && playwright install"}), file=sys.stderr)
    sys.exit(1)


class PlaywrightScanner:
    def __init__(self, url: str, max_depth: int = 2, timeout: int = 300, max_actions_per_state: int = 20, max_path_length: int = 10):
        self.start_url = url
        self.max_depth = max_depth
        self.timeout = timeout
        self.max_actions_per_state = max_actions_per_state
        self.max_path_length = max_path_length
        self.state_queue: deque[State] = deque()
        self.network = NetworkCapture(
            start_url=self.start_url,
            response_body_errors=(PlaywrightError,),
        )
        self.visited_states: Set[Tuple] = set()
        self.last_request_count = 0
        self.last_endpoint_count = 0
        self.last_keys_count = 0
        self.last_graphql_count = 0
        self.stale_iterations = 0
        
        # Fingerprint bucket for fuzzy state deduplication.
        self.state_index = defaultdict(list)

    def _classify_action_semantic(self, text: str, selector: str, tag: str) -> str:
        return classify_action_semantic(text, selector, tag)

    async def _get_dom_vector(self, page: Page) -> Dict[str, int]:
        return await get_dom_vector(page)

    async def _get_dom_hash(self, page: Page) -> str:
        return await get_dom_hash(page)

    def _dom_similarity(self, a: Dict[str, int], b: Dict[str, int]) -> float:
        return dom_similarity(a, b)

    async def _get_state_fingerprint(self, page: Page):
        return await get_state_fingerprint(page)

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
                if not selector:
                    continue
                semantic = self._classify_action_semantic(text, selector, tag)
                actions.add(Action(selector=selector, text=text, tag=tag, semantic=semantic))
            except PlaywrightError as exc:
                logger.debug(f"Skipping action extraction for unstable element: {exc}")

        return actions

    async def _generate_selector(self, el: ElementHandle) -> str | None:
        return await generate_selector(el, recover_from=PlaywrightError, logger=logger)

    async def _fill_forms(self, page: Page) -> None:
        await fill_forms(page)

    async def _execute_action(self, page: Page, action: Action) -> tuple[bool, bool]:
        """Execute single action and return (success, had_effect)"""
        try:
            element = await page.query_selector(action.selector)
            if element and await element.is_visible() and await element.is_enabled():
                initial_request_count = self.network.request_count

                await element.scroll_into_view_if_needed()
                await element.click(timeout=1000)

                try:
                    await page.wait_for_load_state("domcontentloaded", timeout=500)
                except PlaywrightTimeoutError:
                    pass

                await page.wait_for_timeout(200)

                had_effect = self.network.request_count > initial_request_count
                return True, had_effect
        except PlaywrightError as exc:
            logger.debug(f"Action execution failed for {action.text[:30]}: {exc}")
        return False, False

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

    async def _page_state_mismatch(self, page: Page, target_state: State) -> str | None:
        """Return why the current page does not match target_state."""
        current_dom_vector = await self._get_dom_vector(page)
        current_actions = await self._extract_actions(page)
        return state_observation_mismatch(
            target_state,
            current_url=page.url,
            current_dom_vector=current_dom_vector,
            current_actions=current_actions,
        )

    async def _page_matches_state(self, page: Page, target_state: State) -> bool:
        return await self._page_state_mismatch(page, target_state) is None

    async def _replay_state(
        self,
        page: Page,
        start_url: str,
        target_state: State,
    ) -> bool:
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
                except PlaywrightTimeoutError:
                    pass
                await page.wait_for_timeout(500)

            mismatch = await self._page_state_mismatch(page, target_state)
            if mismatch:
                logger.warning(f"Replay mismatch: {mismatch}")
                return False

            return True

        except PlaywrightError as e:
            logger.error(f"State replay failed: {e}")
            return False


    async def _explore_state(self, page: Page, state: State):
        """Explore single state by executing representative actions from each cluster"""
        logger.info(f"Exploring state: {state.url} (depth={state.depth}, actions={len(state.actions)})")

        await self._fill_forms(page)

        try:
            await page.mouse.wheel(0, 5000)
            await page.wait_for_timeout(500)
        except PlaywrightError as exc:
            logger.debug(f"Initial scroll failed: {exc}")

        action_clusters = {}
        for action in state.actions:
            if action not in state.executed_actions and action not in state.dead_actions:
                cluster_key = action.get_cluster_key()
                if cluster_key not in action_clusters:
                    action_clusters[cluster_key] = action

        logger.info(f"Action clusters: {len(action_clusters)} ({', '.join(k.split(':')[0] for k in action_clusters.keys())})")

        initial_state_endpoints = len(state.discovered_endpoints)
        initial_state_clusters = len(state.executed_clusters)

        for cluster_key, action in action_clusters.items():
            if cluster_key in state.executed_clusters:
                continue

            try:
                dom_hash, dom_vector, cookies_hash, storage_hash = await self._get_state_fingerprint(page)
            except PlaywrightError as e:
                logger.warning(f"Failed to get state fingerprint before action: {e}")
                break

            initial_request_count = self.network.request_count
            initial_endpoints = self.network.unique_endpoints.copy()

            if action.semantic in ['submit', 'interaction', 'auth']:
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
            except PlaywrightError as e:
                logger.warning(f"Failed to get state fingerprint after action (navigation?): {e}")
                break

            request_delta = self.network.request_count - initial_request_count
            new_endpoints = self.network.unique_endpoints - initial_endpoints
            dom_changed = new_dom != dom_hash
            cookies_changed = new_cookies != cookies_hash
            storage_changed = new_storage != storage_hash

            had_effect = request_delta > 0 or dom_changed or cookies_changed or storage_changed

            if not had_effect:
                state.dead_actions.add(action)
                logger.info(f"Dead action [{action.semantic}]: {action.text[:30]} (no requests, no state change)")
                continue

            state.discovered_endpoints.update(new_endpoints)
            if new_endpoints:
                logger.info(f"Action [{action.semantic}] discovered {len(new_endpoints)} new endpoints")

            start_domain = urlparse(self.start_url).netloc
            new_domain = urlparse(new_url).netloc

            current_fingerprint = None
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
                    current_fingerprint = new_state.get_fingerprint()
                    
                    # Avoid queueing near-duplicate DOM states for the same fingerprint.
                    skip_state = False
                    for existing_state in self.state_index.get(current_fingerprint, []):
                        similarity = self._dom_similarity(existing_state.dom_vector, new_state.dom_vector)
                        if similarity > 0.92:  # 92% similarity threshold
                            logger.info(f"Duplicate state (similarity={similarity:.2f}): {new_url}")
                            skip_state = True
                            break
                    
                    if not skip_state:
                        self.state_index[current_fingerprint].append(new_state)
                        self.state_queue.append(new_state)
                        logger.info(f"New state: {new_url} (clusters={len(actions)}, path_len={len(new_state.path)})")
                        
                except PlaywrightError as e:
                    logger.warning(f"Failed to extract actions for new state: {e}")

            new_endpoints_delta = len(state.discovered_endpoints) - initial_state_endpoints
            new_clusters_delta = len(state.executed_clusters) - initial_state_clusters
            if state.is_exhausted(new_endpoints_delta == 0, new_clusters_delta == 0):
                logger.info(f"State exhausted: {len(state.executed_clusters)} clusters executed, {len(state.discovered_endpoints)} endpoints discovered")
                break

    async def _check_convergence(self) -> bool:
        """Check if crawler has converged (no new discoveries)"""
        endpoints_delta = len(self.network.unique_endpoints) - self.last_endpoint_count
        requests_delta = self.network.request_count - self.last_request_count
        keys_delta = len(self.network.unique_json_keys) - self.last_keys_count
        graphql_delta = len(self.network.unique_graphql_ops) - self.last_graphql_count

        if endpoints_delta == 0 and requests_delta == 0 and keys_delta == 0 and graphql_delta == 0:
            self.stale_iterations += 1
        else:
            self.stale_iterations = 0

        self.last_request_count = self.network.request_count
        self.last_endpoint_count = len(self.network.unique_endpoints)
        self.last_keys_count = len(self.network.unique_json_keys)
        self.last_graphql_count = len(self.network.unique_graphql_ops)

        if self.stale_iterations >= 3:
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

            page.on("request", self.network.log_request)

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

            await page.route("**/*", self.network.intercept_request)
            page.on("response", self.network.handle_response)

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

            self.visited_states.add(initial_state.get_fingerprint())
            self.state_index[initial_state.get_fingerprint()].append(initial_state)
            self.state_queue.append(initial_state)

            while self.state_queue:
                if await self._check_convergence() and len(self.state_queue) < 2:
                    break
                state = self.state_queue.popleft()

                try:
                    if state.path and not await self._page_matches_state(page, state):
                        if not await self._replay_state(page, self.start_url, state):
                            logger.warning(f"Skipping state after failed replay: {state.url}")
                            continue
                    await self._explore_state(page, state)
                except PlaywrightError as e:
                    logger.error(f"Error exploring {state.url}: {e}")

            await browser.close()

        logger.info(f"Scan completed: {self.network.request_count} requests, {len(self.network.unique_endpoints)} endpoints, {len(self.network.unique_methods_paths)} methods, {len(self.network.unique_json_keys)} JSON keys, {len(self.network.unique_graphql_ops)} GraphQL ops, {sum(len(v) for v in self.state_index.values())} states")


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