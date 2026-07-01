"""DOM and action helpers for the Playwright crawler."""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

DOM_VECTOR_SCRIPT = """
    () => {
        const v = {};
        const inc = k => v[k] = (v[k] || 0) + 1;

        document.querySelectorAll('*').forEach(e => inc('tag:' + e.tagName.toLowerCase()));
        document.querySelectorAll('input').forEach(e => inc('input:' + (e.type || 'text')));

        inc('forms:' + document.forms.length);
        inc('buttons:' + document.querySelectorAll('button').length);
        inc('links:' + document.querySelectorAll('a').length);
        inc('clickables:' + document.querySelectorAll('[role=button]').length);

        inc('headers:' + document.querySelectorAll('h1,h2,h3,h4,h5,h6,header').length);
        inc('navs:' + document.querySelectorAll('nav').length);
        inc('sections:' + document.querySelectorAll('section,article,main').length);

        return v;
    }
"""

FORM_FILL_SCRIPT = """
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
"""

SELECTOR_SCRIPT = """
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
"""


def classify_action_semantic(text: str, selector: str, tag: str) -> str:
    """Classify an action by user-visible text, selector, and element tag."""
    text_lower = text.lower()
    selector_lower = selector.lower()

    if any(k in text_lower for k in ["next", "prev", "page", "»", "«", ">", "<"]):
        return "pagination"
    if any(k in text_lower for k in ["filter", "sort", "search", "apply", "category", "tag"]):
        return "filter"
    if any(k in text_lower for k in ["submit", "send", "save", "post", "create", "delete", "update"]):
        return "submit"
    if any(k in text_lower for k in ["login", "signup", "logout", "register"]):
        return "auth"
    if tag == "a" or "nav" in selector_lower or "menu" in selector_lower:
        return "navigation"
    if any(k in text_lower for k in ["load", "more", "show", "expand", "view"]):
        return "data_loader"

    return "interaction"


async def get_dom_vector(page: Any) -> dict[str, int]:
    """Get a semantic DOM feature vector."""
    return await page.evaluate(DOM_VECTOR_SCRIPT)


def dom_vector_hash(vector: Mapping[str, int]) -> str:
    """Hash a DOM feature vector with stable ordering."""
    vector_str = json.dumps(sorted(vector.items()), sort_keys=True)
    return hashlib.sha256(vector_str.encode()).hexdigest()[:16]


async def get_dom_hash(page: Any) -> str:
    """Get a semantic DOM fingerprint ignoring dynamic content."""
    return dom_vector_hash(await get_dom_vector(page))


def dom_similarity(a: Mapping[str, int], b: Mapping[str, int]) -> float:
    """Calculate Jaccard similarity between DOM feature vectors."""
    if not a or not b:
        return 0.0

    keys = set(a) | set(b)
    inter = sum(min(a.get(k, 0), b.get(k, 0)) for k in keys)
    union = sum(max(a.get(k, 0), b.get(k, 0)) for k in keys)
    return inter / union if union > 0 else 0.0


async def get_state_fingerprint(page: Any) -> tuple[str, dict[str, int], str, str]:
    """Get DOM, cookies, and storage fingerprints for a browser state."""
    cookies = await page.context.cookies()
    cookies_hash = hashlib.sha256(json.dumps(cookies, sort_keys=True, default=str).encode()).hexdigest()[:16]

    storage = await page.evaluate("""
        () => JSON.stringify({
            localStorage: {...localStorage},
            sessionStorage: {...sessionStorage}
        })
    """)
    storage_hash = hashlib.sha256(storage.encode()).hexdigest()[:16]

    dom_vector = await get_dom_vector(page)
    dom_hash = dom_vector_hash(dom_vector)

    return dom_hash, dom_vector, cookies_hash, storage_hash


async def generate_selector(
    element: Any,
    *,
    recover_from: type[BaseException] | tuple[type[BaseException], ...],
    logger: Any,
) -> str | None:
    """Generate a stable CSS selector for an element."""
    try:
        return await element.evaluate(SELECTOR_SCRIPT)
    except recover_from as exc:
        logger.debug(f"Failed to generate selector: {exc}")
        return None


async def fill_forms(page: Any) -> None:
    """Fill basic form controls with deterministic placeholder values."""
    await page.evaluate(FORM_FILL_SCRIPT)
