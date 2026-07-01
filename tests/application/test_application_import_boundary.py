from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(".")
APPLICATION_ROOT = ROOT / "src/api/application"

# Temporary allowlist for already-known boundary leaks. This test is an AST gate:
# it should fail when a new application -> infrastructure import appears. Shrink
# this list as compatibility aliases and legacy execution seams are removed.
_ALLOWED_INFRASTRUCTURE_IMPORTS = {
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



def test_application_composition_root_aliases_stay_removed() -> None:
    assert not (APPLICATION_ROOT / "di.py").exists()
    assert not (APPLICATION_ROOT / "container.py").exists()

    removed_paths = {"api.application.di", "api.application.container"}
    found = _imports_from_src(lambda _path, module: module in removed_paths)

    assert sorted(found) == []



def test_application_pipeline_infrastructure_aliases_stay_removed() -> None:
    removed_paths = {
        APPLICATION_ROOT / "pipeline/builder.py",
        APPLICATION_ROOT / "pipeline/catalog.py",
        APPLICATION_ROOT / "pipeline/run_state_reporter.py",
    }

    assert [path.as_posix() for path in sorted(removed_paths) if path.exists()] == []

    removed_modules = {
        "api.application.pipeline.builder",
        "api.application.pipeline.catalog",
        "api.application.pipeline.run_state_reporter",
    }
    found = _imports_from_src(lambda _path, module: module in removed_modules)

    assert sorted(found) == []


def test_mvp_research_compat_aliases_stay_removed() -> None:
    removed_paths = {
        APPLICATION_ROOT / "mvp_research_workflow.py",
        APPLICATION_ROOT / "mvp_research_readiness.py",
        APPLICATION_ROOT / "mvp_research_state_graph.py",
        APPLICATION_ROOT / "langgraph_inbox_handoff.py",
    }

    assert [path.as_posix() for path in sorted(removed_paths) if path.exists()] == []

    removed_modules = {
        "api.application.mvp_research_workflow",
        "api.application.mvp_research_readiness",
        "api.application.mvp_research_state_graph",
        "api.application.langgraph_inbox_handoff",
    }
    found = _imports_from_src(lambda _path, module: module in removed_modules)

    assert sorted(found) == []

    resume_source = (ROOT / "src/api/infrastructure/langgraph_resume.py").read_text(
        encoding="utf-8"
    )
    assert "MvpResearchAutoResumer" not in resume_source




def test_flat_agent_task_langgraph_modules_stay_removed() -> None:
    removed_paths = {
        APPLICATION_ROOT / "agent_task_langgraph_context.py",
        APPLICATION_ROOT / "agent_task_langgraph_factory.py",
        APPLICATION_ROOT / "agent_task_langgraph_graph.py",
        APPLICATION_ROOT / "agent_task_langgraph_helpers.py",
        APPLICATION_ROOT / "agent_task_langgraph_models.py",
        APPLICATION_ROOT / "agent_task_langgraph_result.py",
        APPLICATION_ROOT / "agent_task_langgraph_runtime.py",
    }
    assert [path.as_posix() for path in sorted(removed_paths) if path.exists()] == []

    removed_modules = {
        "api.application.agent_task_langgraph_context",
        "api.application.agent_task_langgraph_factory",
        "api.application.agent_task_langgraph_graph",
        "api.application.agent_task_langgraph_helpers",
        "api.application.agent_task_langgraph_models",
        "api.application.agent_task_langgraph_result",
        "api.application.agent_task_langgraph_runtime",
    }
    found = _imports_from_src(lambda _path, module: module in removed_modules)

    assert sorted(found) == []



def test_flat_agent_task_role_modules_stay_removed() -> None:
    removed_paths = {
        APPLICATION_ROOT / "agent_task_role_composer.py",
        APPLICATION_ROOT / "agent_task_role_context.py",
        APPLICATION_ROOT / "agent_task_role_models.py",
        APPLICATION_ROOT / "agent_task_role_proposals.py",
        APPLICATION_ROOT / "agent_task_role_text.py",
        APPLICATION_ROOT / "agent_task_roles.py",
    }
    assert [path.as_posix() for path in sorted(removed_paths) if path.exists()] == []

    removed_modules = {
        "api.application.agent_task_role_composer",
        "api.application.agent_task_role_context",
        "api.application.agent_task_role_models",
        "api.application.agent_task_role_proposals",
        "api.application.agent_task_role_text",
        "api.application.agent_task_roles",
    }
    found = _imports_from_src(lambda _path, module: module in removed_modules)

    assert sorted(found) == []


def test_flat_agent_task_inbox_modules_stay_removed() -> None:
    removed_paths = {
        APPLICATION_ROOT / "agent_task_inbox_bridge.py",
        APPLICATION_ROOT / "agent_task_inbox_bridge_models.py",
        APPLICATION_ROOT / "agent_task_inbox_payload.py",
        APPLICATION_ROOT / "agent_task_inbox_processor.py",
    }
    assert [path.as_posix() for path in sorted(removed_paths) if path.exists()] == []

    removed_modules = {
        "api.application.agent_task_inbox_bridge",
        "api.application.agent_task_inbox_bridge_models",
        "api.application.agent_task_inbox_payload",
        "api.application.agent_task_inbox_processor",
    }
    found = _imports_from_src(lambda _path, module: module in removed_modules)

    assert sorted(found) == []


def test_action_catalog_resolver_service_stays_removed() -> None:
    assert not (APPLICATION_ROOT / "services/action_catalog_resolver.py").exists()

    found = _imports_from_src(
        lambda _path, module: module == "api.application.services.action_catalog_resolver"
    )

    assert sorted(found) == []

    compiler_source = (APPLICATION_ROOT / "services/action_command/compiler.py").read_text(
        encoding="utf-8"
    )
    assert "class ActionCatalogResolver" not in compiler_source
    assert "def bind(" not in compiler_source
    assert "bind_profile" not in compiler_source


def test_action_command_compiler_stays_packaged() -> None:
    assert not (APPLICATION_ROOT / "services/action_command_compiler.py").exists()
    package_root = APPLICATION_ROOT / "services/action_command"
    expected = {"__init__.py", "budget.py", "compiler.py", "metadata.py", "options.py"}
    assert expected.issubset({path.name for path in package_root.iterdir()})

    compiler_source = (package_root / "compiler.py").read_text(encoding="utf-8")
    assert "normalize_options" not in compiler_source
    assert "resolve_execution_budget" not in compiler_source
    assert "effective_budget" not in compiler_source


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



def test_deprecated_process_event_schema_alias_stays_removed() -> None:
    assert not (ROOT / "src/api/infrastructure/schemas/models/process_event.py").exists()

    found = _imports_from_src(
        lambda _path, module: module == "api.infrastructure.schemas.models.process_event"
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
