from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


def _load_review_gates():
    root = Path(__file__).resolve().parents[2]
    module_path = root / "scripts" / "review_gates.py"
    spec = importlib.util.spec_from_file_location("review_gates_for_tests", module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["review_gates_for_tests"] = module
    spec.loader.exec_module(module)
    return module


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_review_gates_pass_current_repository() -> None:
    review_gates = _load_review_gates()
    root = Path(__file__).resolve().parents[2]

    violations = review_gates.run_checks(
        root,
        allowlist_path=root / "governance" / "review_gates_allowlist.json",
    )

    assert violations == []


def test_review_gates_reject_new_long_file_without_reason(tmp_path: Path) -> None:
    review_gates = _load_review_gates()
    body = "\n".join(f"value_{index} = {index}" for index in range(501))
    _write(tmp_path / "src" / "oversized.py", body)

    violations = review_gates.run_checks(tmp_path, allowlist_path=None, scan_roots=("src",))

    assert [violation.rule for violation in violations] == ["long-file"]
    assert violations[0].path == "src/oversized.py"


def test_review_gates_reject_allowed_file_growth(tmp_path: Path) -> None:
    review_gates = _load_review_gates()
    body = "\n".join(f"value_{index} = {index}" for index in range(503))
    _write(tmp_path / "src" / "legacy.py", body)
    allowlist_path = tmp_path / "governance" / "review_gates_allowlist.json"
    allowlist_path.parent.mkdir(parents=True, exist_ok=True)
    allowlist_path.write_text(
        json.dumps(
            {
                "long_files": {
                    "src/legacy.py": {
                        "max_lines": 502,
                        "reason": "Legacy file allowed only until it is reduced in a dedicated refactor.",
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    violations = review_gates.run_checks(tmp_path, allowlist_path=allowlist_path, scan_roots=("src",))

    assert [violation.rule for violation in violations] == ["long-file-growth"]


def test_review_gates_reject_new_long_function(tmp_path: Path) -> None:
    review_gates = _load_review_gates()
    function_body = "\n".join(f"    step_{index} = {index}" for index in range(81))
    _write(tmp_path / "src" / "worker.py", f"def execute():\n{function_body}\n    return step_80\n")

    violations = review_gates.run_checks(tmp_path, allowlist_path=None, scan_roots=("src",))

    assert [violation.rule for violation in violations] == ["long-function"]
    assert violations[0].symbol == "execute"


def test_review_gates_reject_score_calculation_inside_store(tmp_path: Path) -> None:
    review_gates = _load_review_gates()
    _write(
        tmp_path / "src" / "bad_store.py",
        "class UtilityScoreCalculator:\n"
        "    @staticmethod\n"
        "    def calculate():\n"
        "        return 1\n\n"
        "class ActionStore:\n"
        "    def save(self):\n"
        "        return UtilityScoreCalculator.calculate()\n",
    )

    violations = review_gates.run_checks(tmp_path, allowlist_path=None, scan_roots=("src",))

    assert [violation.rule for violation in violations] == ["store-score-math"]
    assert violations[0].symbol == "ActionStore"


def test_review_gates_reject_cypher_writes_in_gds_reader_path(tmp_path: Path) -> None:
    review_gates = _load_review_gates()
    _write(
        tmp_path / "services" / "graph-projector" / "graph_projector" / "example_gds.py",
        "QUERY = '''\n"
        "MATCH (n)\n"
        "MERGE (probe:TransientProbe {id: $id})\n"
        "RETURN n\n"
        "'''\n",
    )

    violations = review_gates.run_checks(tmp_path, allowlist_path=None, scan_roots=("services",))

    assert [violation.rule for violation in violations] == ["read-path-write-cypher"]


def test_review_gates_reject_large_inline_cypher_outside_query_artifact(tmp_path: Path) -> None:
    review_gates = _load_review_gates()
    query_lines = ["MATCH (n)"] + [f"WITH n AS n{i}" for i in range(61)] + ["RETURN n"]
    _write(tmp_path / "src" / "reader.py", "QUERY = '''\n" + "\n".join(query_lines) + "\n'''\n")

    violations = review_gates.run_checks(tmp_path, allowlist_path=None, scan_roots=("src",))

    assert [violation.rule for violation in violations] == ["long-cypher-inline"]


def test_review_gates_default_roots_cover_scripts_alembic_and_playwright() -> None:
    review_gates = _load_review_gates()

    assert "scripts" in review_gates.DEFAULT_SCAN_ROOTS
    assert "alembic" in review_gates.DEFAULT_SCAN_ROOTS
    assert "playwright" in review_gates.DEFAULT_SCAN_ROOTS
    assert "docs" in review_gates.DEFAULT_SCAN_ROOTS


def test_alembic_migration_graph_has_single_expected_head() -> None:
    root = Path(__file__).resolve().parents[2]
    revisions: dict[str, Path] = {}
    parents: dict[str, object] = {}
    import ast

    for migration in (root / "alembic" / "versions").glob("*.py"):
        tree = ast.parse(migration.read_text(encoding="utf-8"))
        revision = None
        down_revision = None
        for node in tree.body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id in {"revision", "down_revision"}:
                        value = ast.literal_eval(node.value)
                        if target.id == "revision":
                            revision = value
                        else:
                            down_revision = value
            if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                if node.target.id in {"revision", "down_revision"}:
                    value = ast.literal_eval(node.value)
                    if node.target.id == "revision":
                        revision = value
                    else:
                        down_revision = value
        assert revision is not None, migration
        revisions[revision] = migration
        parents[revision] = down_revision

    children: dict[str, list[str]] = {revision: [] for revision in revisions}
    for revision, down_revision in parents.items():
        parent_ids = [] if down_revision is None else list(down_revision) if isinstance(down_revision, tuple) else [down_revision]
        for parent in parent_ids:
            children.setdefault(parent, []).append(revision)
    heads = {revision for revision in revisions if not children.get(revision)}

    assert heads == {"u5v6w7x8y9z0"}
