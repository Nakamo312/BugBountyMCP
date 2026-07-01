from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(".")
PLAYWRIGHT_ROOT = ROOT / "playwright"
SCANNER_PATH = PLAYWRIGHT_ROOT / "playwright_scanner.py"
DOCKERFILE_PATH = PLAYWRIGHT_ROOT / "Dockerfile"
INFRA_RUNNERS = ROOT / "src/api/infrastructure/runners"


def _scanner_tree() -> ast.Module:
    return ast.parse(SCANNER_PATH.read_text())


def test_playwright_scanner_models_live_in_crawler_package() -> None:
    sys.path.insert(0, str(PLAYWRIGHT_ROOT))
    try:
        from crawler.models import Action, State
    finally:
        sys.path.remove(str(PLAYWRIGHT_ROOT))

    assert Action.__module__ == "crawler.models"
    assert State.__module__ == "crawler.models"


def test_playwright_scanner_http_capture_lives_in_crawler_package() -> None:
    sys.path.insert(0, str(PLAYWRIGHT_ROOT))
    try:
        from crawler.http_capture import (
            build_request_capture,
            extract_graphql_operation,
            extract_json_keys,
            make_request_key,
        )
    finally:
        sys.path.remove(str(PLAYWRIGHT_ROOT))

    capture = build_request_capture(
        method="POST",
        url="https://example.test/api/users?debug=1",
        headers={"content-type": "application/json"},
        resource_type="fetch",
        post_data='{"query":"query Users { users { id } }","operationName":"Users"}',
    )

    assert make_request_key("POST", "https://example.test/api/users?debug=1", '{"b":2,"a":1}') == "POST:/api/users:debug:a,b"
    assert capture["request"]["body"].startswith("{")
    assert "POST /api/users?debug=1 HTTP/1.1" in capture["request"]["raw"]
    assert extract_json_keys('{"a":{"nested":1},"b":2}') == {"a", "nested", "b"}
    assert extract_graphql_operation('{"query":"query Users { users { id } }","operationName":"Users"}', "application/json", "https://example.test/graphql") == "graphql_raw"


def test_playwright_docker_image_copies_crawler_package() -> None:
    dockerfile = DOCKERFILE_PATH.read_text()

    assert "COPY crawler ./crawler" in dockerfile
    assert dockerfile.index("COPY crawler ./crawler") < dockerfile.index("COPY playwright_scanner.py .")


def test_infrastructure_playwright_scanner_duplicate_stays_removed() -> None:
    assert not (INFRA_RUNNERS / "playwright_scanner.py").exists()


def test_playwright_scanner_has_no_bare_except_handlers() -> None:
    for node in ast.walk(_scanner_tree()):
        if isinstance(node, ast.ExceptHandler):
            assert node.type is not None, f"bare except at line {node.lineno}"


def test_playwright_scanner_limits_broad_exception_to_cli_boundary() -> None:
    broad_handlers = []
    parent_by_child = {}
    tree = _scanner_tree()
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parent_by_child[child] = parent

    for node in ast.walk(tree):
        if not isinstance(node, ast.ExceptHandler) or not isinstance(node.type, ast.Name):
            continue
        if node.type.id != "Exception":
            continue

        current = node
        owner_name = None
        while current in parent_by_child:
            current = parent_by_child[current]
            if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef)):
                owner_name = current.name
                break
        broad_handlers.append(owner_name)

    assert broad_handlers == ["main"]


def test_playwright_scanner_delegates_http_capture_helpers() -> None:
    scanner_source = SCANNER_PATH.read_text()

    assert "def _make_request_key" not in scanner_source
    assert "def _extract_json_keys" not in scanner_source
    assert "def _extract_graphql_operation" not in scanner_source
    assert "def _is_static_resource" not in scanner_source
    assert "from crawler.network import NetworkCapture" in scanner_source
    assert "from crawler.http_capture import" not in scanner_source


def test_playwright_network_capture_owns_request_response_state() -> None:
    sys.path.insert(0, str(PLAYWRIGHT_ROOT))
    try:
        from crawler.network import NetworkCapture
    finally:
        sys.path.remove(str(PLAYWRIGHT_ROOT))

    capture = NetworkCapture(start_url="https://example.test")

    assert capture.should_capture("https://example.test/api", "fetch")
    assert not capture.should_capture("https://cdn.example.test/api", "fetch")
    assert not capture.should_capture("https://example.test/app.png", "image")


def test_playwright_scanner_dom_helpers_live_in_crawler_package() -> None:
    sys.path.insert(0, str(PLAYWRIGHT_ROOT))
    try:
        from crawler.dom import classify_action_semantic, dom_similarity, dom_vector_hash
    finally:
        sys.path.remove(str(PLAYWRIGHT_ROOT))

    assert classify_action_semantic("Submit", "button", "button") == "submit"
    assert classify_action_semantic("Open", "nav > a", "a") == "navigation"
    assert dom_similarity({"a": 2, "b": 1}, {"a": 1, "b": 1}) == 2 / 3
    assert len(dom_vector_hash({"forms:1": 1})) == 16


def test_playwright_scanner_delegates_dom_and_form_helpers() -> None:
    scanner_source = SCANNER_PATH.read_text()

    assert "from crawler.dom import" in scanner_source
    assert "document.querySelectorAll('input, textarea, select')" not in scanner_source
    assert "document.querySelectorAll('*')" not in scanner_source
    assert "el.dataset.testid" not in scanner_source


def test_playwright_network_response_handler_pops_pending_request_once() -> None:
    scanner_source = SCANNER_PATH.read_text()
    network_source = (PLAYWRIGHT_ROOT / "crawler/network.py").read_text()

    assert "pending_requests" not in scanner_source
    assert network_source.count("self.pending_requests.pop(key, None)") == 1


def test_playwright_state_matching_rejects_same_url_with_different_state() -> None:
    sys.path.insert(0, str(PLAYWRIGHT_ROOT))
    try:
        from crawler.models import Action, State
        from crawler.state_match import state_observation_mismatch
    finally:
        sys.path.remove(str(PLAYWRIGHT_ROOT))

    expected_action = Action(selector="button#save", text="Save", tag="button", semantic="submit")
    target = State(
        url="https://example.test/app",
        dom_hash="old",
        dom_vector={"forms:1": 3, "buttons": 2},
        cookies_hash="cookies",
        storage_hash="storage",
        depth=1,
        path=[expected_action],
        actions={expected_action},
    )

    mismatch = state_observation_mismatch(
        target,
        current_url="https://example.test/app",
        current_dom_vector={"completely:different": 7},
        current_actions={expected_action},
    )

    assert mismatch == "DOM similarity 0.00"


def test_playwright_state_matching_accepts_same_route_when_dom_and_actions_match() -> None:
    sys.path.insert(0, str(PLAYWRIGHT_ROOT))
    try:
        from crawler.models import Action, State
        from crawler.state_match import state_observation_matches
    finally:
        sys.path.remove(str(PLAYWRIGHT_ROOT))

    expected_action = Action(selector="button#save", text="Save", tag="button", semantic="submit")
    target = State(
        url="https://example.test/app",
        dom_hash="old",
        dom_vector={"forms:1": 3, "buttons": 2},
        cookies_hash="cookies",
        storage_hash="storage",
        depth=1,
        path=[expected_action],
        actions={expected_action},
    )

    assert state_observation_matches(
        target,
        current_url="https://example.test/app",
        current_dom_vector={"forms:1": 3, "buttons": 2},
        current_actions={expected_action},
    )


def test_playwright_scanner_does_not_use_url_equality_as_replay_gate() -> None:
    scanner_source = SCANNER_PATH.read_text()

    assert "page.url != state.url" not in scanner_source
    assert "from crawler.state_match import state_observation_mismatch" in scanner_source
    assert "async def _page_matches_state" in scanner_source
