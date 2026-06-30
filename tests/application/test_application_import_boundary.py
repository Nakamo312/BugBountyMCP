from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(".")
APPLICATION_ROOT = ROOT / "src/api/application"

# Temporary allowlist for already-known boundary leaks. This test is an AST gate:
# it should fail when a new application -> infrastructure import appears. Shrink
# this list as compatibility aliases and legacy execution seams are removed.
_ALLOWED_INFRASTRUCTURE_IMPORTS = {
    # Compatibility composition root: api.application.di still assembles the app
    # using infrastructure providers until imports move to the actual entrypoint.
    ("src/api/application/di.py", "api.infrastructure.providers.action_runtime"),
    ("src/api/application/di.py", "api.infrastructure.providers.agent_runtime"),
    ("src/api/application/di.py", "api.infrastructure.providers.batch_processors"),
    ("src/api/application/di.py", "api.infrastructure.providers.credentials"),
    ("src/api/application/di.py", "api.infrastructure.providers.database"),
    ("src/api/application/di.py", "api.infrastructure.providers.ingestors"),
    ("src/api/application/di.py", "api.infrastructure.providers.pipeline"),
    ("src/api/application/di.py", "api.infrastructure.providers.read_models"),
    ("src/api/application/di.py", "api.infrastructure.providers.research_runtime"),
    ("src/api/application/di.py", "api.infrastructure.providers.runners"),
    ("src/api/application/di.py", "api.infrastructure.providers.services"),
    # Deprecated compatibility aliases after moving concrete catalog/builders.
    ("src/api/application/pipeline/builder.py", "api.infrastructure.pipeline.builder"),
    ("src/api/application/pipeline/catalog.py", "api.infrastructure.pipeline.catalog"),
    # Deprecated compatibility aliases after moving provider wiring.
    ("src/api/application/providers/action_runtime.py", "api.infrastructure.providers.action_runtime"),
    ("src/api/application/providers/agent_runtime.py", "api.infrastructure.providers.agent_runtime"),
    ("src/api/application/providers/batch_processors.py", "api.infrastructure.providers.batch_processors"),
    ("src/api/application/providers/credentials.py", "api.infrastructure.providers.credentials"),
    ("src/api/application/providers/database.py", "api.infrastructure.providers.database"),
    ("src/api/application/providers/ingestors.py", "api.infrastructure.providers.ingestors"),
    ("src/api/application/providers/pipeline.py", "api.infrastructure.providers.pipeline"),
    ("src/api/application/providers/read_models.py", "api.infrastructure.providers.read_models"),
    ("src/api/application/providers/research_runtime.py", "api.infrastructure.providers.research_runtime"),
    ("src/api/application/providers/runners.py", "api.infrastructure.providers.runners"),
    ("src/api/application/providers/services.py", "api.infrastructure.providers.services"),
    # Remaining legacy seams are UoW protocols and raw artifact parsing.
    # Runner refs/factories, event bus, EventType, and queue topology are
    # no longer allowed here.
    ("src/api/application/services/analysis.py", "api.infrastructure.unit_of_work.interfaces.httpx"),
    ("src/api/application/services/host.py", "api.infrastructure.unit_of_work.interfaces.httpx"),
    ("src/api/application/services/infrastructure.py", "api.infrastructure.unit_of_work.interfaces.infrastructure"),
    ("src/api/application/services/program.py", "api.infrastructure.unit_of_work.interfaces.program"),
    ("src/api/application/services/raw_artifact_parser.py", "api.infrastructure.parsers.raw_artifact_parser"),
}


def _infrastructure_imports() -> set[tuple[str, str]]:
    imports: set[tuple[str, str]] = set()
    for path in APPLICATION_ROOT.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        rel_path = path.as_posix()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                modules = [node.module or ""]
            else:
                continue
            for module in modules:
                if module.startswith("api.infrastructure"):
                    imports.add((rel_path, module))
    return imports


def test_application_infrastructure_imports_do_not_grow() -> None:
    found = _infrastructure_imports()

    new_imports = sorted(found - _ALLOWED_INFRASTRUCTURE_IMPORTS)
    assert new_imports == []


def test_application_infrastructure_import_allowlist_stays_honest() -> None:
    found = _infrastructure_imports()

    stale_allowlist_entries = sorted(_ALLOWED_INFRASTRUCTURE_IMPORTS - found)
    assert stale_allowlist_entries == []


def _imports_from_src(predicate) -> set[tuple[str, str]]:
    imports: set[tuple[str, str]] = set()
    for path in (ROOT / "src").rglob("*.py"):
        rel_path = path.as_posix()
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                modules = [node.module or ""]
            else:
                continue
            for module in modules:
                if predicate(rel_path, module):
                    imports.add((rel_path, module))
    return imports


def test_application_does_not_import_transport_event_bus_or_queue_config() -> None:
    forbidden = {
        "api.infrastructure.events.event_bus",
        "api.infrastructure.events.queue_config",
    }

    found = _imports_from_src(
        lambda path, module: (
            path.startswith("src/api/application/") and module in forbidden
        )
    )

    assert sorted(found) == []


def test_application_does_not_import_concrete_runner_infrastructure() -> None:
    forbidden = {
        "api.infrastructure.runners.cli_tool",
        "api.infrastructure.runners.cli_tool_factory",
    }

    found = _imports_from_src(
        lambda path, module: (
            path.startswith("src/api/application/") and module in forbidden
        )
    )

    assert sorted(found) == []


def test_no_new_deprecated_event_type_imports() -> None:
    found = _imports_from_src(
        lambda path, module: (
            module == "api.infrastructure.events.event_types"
            and path != "src/api/infrastructure/events/event_types.py"
        )
    )

    assert sorted(found) == []


def _application_provider_imports() -> set[tuple[str, str]]:
    imports: set[tuple[str, str]] = set()
    for root in (ROOT / "src").rglob("*.py"):
        rel_path = root.as_posix()
        if rel_path.startswith("src/api/application/providers/"):
            continue
        source = root.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(root))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                modules = [node.module or ""]
            else:
                continue
            for module in modules:
                if module == "api.application.providers" or module.startswith("api.application.providers."):
                    imports.add((rel_path, module))
    return imports


def test_no_new_application_provider_compat_imports() -> None:
    assert sorted(_application_provider_imports()) == []


def _application_publish_dict_calls() -> list[tuple[str, int]]:
    calls: list[tuple[str, int]] = []
    for path in APPLICATION_ROOT.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        rel_path = path.as_posix()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not node.args:
                continue
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr == "publish" and isinstance(node.args[0], ast.Dict):
                calls.append((rel_path, node.lineno))
    return calls


def _application_publish_local_dict_calls() -> list[tuple[str, int, str]]:
    calls: list[tuple[str, int, str]] = []
    for path in APPLICATION_ROOT.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        rel_path = path.as_posix()
        functions = (ast.FunctionDef, ast.AsyncFunctionDef)
        for function in (node for node in ast.walk(tree) if isinstance(node, functions)):
            local_dict_names: set[str] = set()
            for node in ast.walk(function):
                if isinstance(node, ast.Assign) and isinstance(node.value, ast.Dict):
                    local_dict_names.update(
                        target.id for target in node.targets if isinstance(target, ast.Name)
                    )
                elif (
                    isinstance(node, ast.AnnAssign)
                    and isinstance(node.target, ast.Name)
                    and isinstance(node.value, ast.Dict)
                ):
                    local_dict_names.add(node.target.id)
            for node in ast.walk(function):
                if not isinstance(node, ast.Call) or not node.args:
                    continue
                func = node.func
                if (
                    isinstance(func, ast.Attribute)
                    and func.attr == "publish"
                    and isinstance(node.args[0], ast.Name)
                    and node.args[0].id in local_dict_names
                ):
                    calls.append((rel_path, node.lineno, node.args[0].id))
    return calls


def test_application_does_not_publish_legacy_event_dict_literals() -> None:
    assert _application_publish_dict_calls() == []


def test_application_does_not_publish_locally_built_legacy_event_dicts() -> None:
    assert _application_publish_local_dict_calls() == []
