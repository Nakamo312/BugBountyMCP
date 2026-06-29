#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

SOURCE_SUFFIXES = {".py", ".js", ".jsx", ".ts", ".tsx"}
PYTHON_SUFFIXES = {".py"}
DEFAULT_SCAN_ROOTS = ("src", "services", "BugBountyDashBoard/src", "tests", "scripts", "alembic", "playwright", "docs")
DEFAULT_ALLOWLIST = "governance/review_gates_allowlist.json"
DEFAULT_MAX_FILE_LINES = 500
DEFAULT_MAX_FUNCTION_LINES = 80
WRITE_CYPHER_RE = re.compile(r"\b(MERGE|CREATE|DELETE|DETACH\s+DELETE|SET|REMOVE)\b", re.IGNORECASE)
READ_PATH_RE = re.compile(r"(^|/)([^/]*(gds|reader|scoring)[^/]*)\.py$", re.IGNORECASE)
STORE_SCORE_CALL_RE = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*ScoreCalculator\.calculate\s*\(")
STORE_MATH_IMPORTS = {"math", "statistics", "numpy", "scipy"}


@dataclass(frozen=True)
class Violation:
    rule: str
    path: str
    message: str
    symbol: str | None = None
    line: int | None = None

    def render(self) -> str:
        where = self.path
        if self.line is not None:
            where = f"{where}:{self.line}"
        if self.symbol:
            where = f"{where}::{self.symbol}"
        return f"[{self.rule}] {where} - {self.message}"


def _rel(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def _iter_source_files(root: Path, scan_roots: Sequence[str]) -> Iterable[Path]:
    for scan_root in scan_roots:
        base = root / scan_root
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if path.is_file() and path.suffix in SOURCE_SUFFIXES:
                yield path


def _line_count(path: Path) -> int:
    with path.open("r", encoding="utf-8", errors="ignore") as handle:
        return sum(1 for _ in handle)


def _load_allowlist(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"review gate allowlist must be a JSON object: {path}")
    return payload


def _allow_entry(allowlist: Mapping[str, Any], group: str, key: str) -> Mapping[str, Any] | None:
    entries = allowlist.get(group, {})
    if not isinstance(entries, Mapping):
        return None
    entry = entries.get(key)
    return entry if isinstance(entry, Mapping) else None


def _allow_reason_ok(entry: Mapping[str, Any] | None) -> bool:
    if entry is None:
        return False
    reason = entry.get("reason")
    return isinstance(reason, str) and len(reason.strip()) >= 20


def _allow_max_lines(entry: Mapping[str, Any] | None) -> int | None:
    if entry is None:
        return None
    value = entry.get("max_lines")
    return value if isinstance(value, int) else None


def check_long_files(
    root: Path,
    files: Sequence[Path],
    allowlist: Mapping[str, Any],
    *,
    max_lines: int = DEFAULT_MAX_FILE_LINES,
) -> list[Violation]:
    violations: list[Violation] = []
    for path in files:
        rel = _rel(path, root)
        count = _line_count(path)
        if count <= max_lines:
            continue
        entry = _allow_entry(allowlist, "long_files", rel)
        allowed_max = _allow_max_lines(entry)
        if not _allow_reason_ok(entry):
            violations.append(
                Violation(
                    "long-file",
                    rel,
                    f"{count} lines; files above {max_lines} lines need an allowlist entry with a reason",
                )
            )
            continue
        if allowed_max is None or count > allowed_max:
            violations.append(
                Violation(
                    "long-file-growth",
                    rel,
                    f"{count} lines; allowed legacy maximum is {allowed_max}",
                )
            )
    return violations


def _python_files(files: Sequence[Path]) -> Iterable[Path]:
    return (path for path in files if path.suffix in PYTHON_SUFFIXES)


def _qualnames(tree: ast.AST) -> dict[ast.AST, str]:
    names: dict[ast.AST, str] = {}

    def visit(node: ast.AST, prefix: tuple[str, ...]) -> None:
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            current = (*prefix, node.name)
            names[node] = ".".join(current)
            for child in node.body:
                visit(child, current)
            return
        for child in ast.iter_child_nodes(node):
            visit(child, prefix)

    visit(tree, ())
    return names


def check_long_functions(
    root: Path,
    files: Sequence[Path],
    allowlist: Mapping[str, Any],
    *,
    max_lines: int = DEFAULT_MAX_FUNCTION_LINES,
) -> list[Violation]:
    violations: list[Violation] = []
    for path in _python_files(files):
        rel = _rel(path, root)
        try:
            tree = ast.parse(_read_text(path), filename=rel)
        except SyntaxError as exc:
            violations.append(Violation("python-parse", rel, str(exc), line=exc.lineno))
            continue
        names = _qualnames(tree)
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if not hasattr(node, "end_lineno"):
                continue
            length = int(node.end_lineno) - int(node.lineno) + 1
            if length <= max_lines:
                continue
            qualname = names.get(node, node.name)
            key = f"{rel}::{qualname}"
            entry = _allow_entry(allowlist, "long_functions", key)
            allowed_max = _allow_max_lines(entry)
            if not _allow_reason_ok(entry):
                violations.append(
                    Violation(
                        "long-function",
                        rel,
                        f"{length} lines; functions above {max_lines} lines need an allowlist entry with a reason",
                        symbol=qualname,
                        line=node.lineno,
                    )
                )
                continue
            if allowed_max is None or length > allowed_max:
                violations.append(
                    Violation(
                        "long-function-growth",
                        rel,
                        f"{length} lines; allowed legacy maximum is {allowed_max}",
                        symbol=qualname,
                        line=node.lineno,
                    )
                )
    return violations


def _contains_store_score_math(class_node: ast.ClassDef, source_segment: str) -> bool:
    for node in ast.walk(class_node):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            imported = {alias.name.split(".", 1)[0] for alias in getattr(node, "names", [])}
            if imported & STORE_MATH_IMPORTS:
                return True
        if isinstance(node, ast.Call):
            call_text = ast.get_source_segment(source_segment, node) or ""
            if STORE_SCORE_CALL_RE.search(call_text):
                return True
        if isinstance(node, ast.FunctionDef) and "score" in node.name.lower():
            return True
    return False


def check_store_score_math(root: Path, files: Sequence[Path], allowlist: Mapping[str, Any]) -> list[Violation]:
    violations: list[Violation] = []
    for path in _python_files(files):
        rel = _rel(path, root)
        try:
            source = _read_text(path)
            tree = ast.parse(source, filename=rel)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef) or not node.name.endswith("Store"):
                continue
            if not _contains_store_score_math(node, source):
                continue
            key = f"{rel}::{node.name}"
            entry = _allow_entry(allowlist, "store_score_math", key)
            if _allow_reason_ok(entry):
                continue
            violations.append(
                Violation(
                    "store-score-math",
                    rel,
                    "Store classes must persist/read data, not calculate ranking or utility scores",
                    symbol=node.name,
                    line=node.lineno,
                )
            )
    return violations


def _string_constants(tree: ast.AST) -> Iterable[tuple[int, str]]:
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            yield getattr(node, "lineno", 1), node.value
        elif isinstance(node, ast.JoinedStr):
            parts: list[str] = []
            for value in node.values:
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    parts.append(value.value)
            if parts:
                yield getattr(node, "lineno", 1), "".join(parts)


def check_read_path_writes(root: Path, files: Sequence[Path], allowlist: Mapping[str, Any]) -> list[Violation]:
    del allowlist
    violations: list[Violation] = []
    for path in _python_files(files):
        rel = _rel(path, root)
        if not READ_PATH_RE.search(rel):
            continue
        try:
            tree = ast.parse(_read_text(path), filename=rel)
        except SyntaxError:
            continue
        for line, value in _string_constants(tree):
            if not ("MATCH" in value.upper() or "CALL" in value.upper()):
                continue
            match = WRITE_CYPHER_RE.search(value)
            if match:
                violations.append(
                    Violation(
                        "read-path-write-cypher",
                        rel,
                        f"reader/GDS/scoring path contains write Cypher token {match.group(0)!r}",
                        line=line,
                    )
                )
    return violations


def _cypher_string_name(parent: ast.AST) -> str | None:
    if isinstance(parent, ast.Assign):
        names = []
        for target in parent.targets:
            if isinstance(target, ast.Name):
                names.append(target.id)
            elif isinstance(target, ast.Attribute):
                names.append(target.attr)
        return ",".join(names) or None
    return None


def _parent_map(tree: ast.AST) -> dict[ast.AST, ast.AST]:
    parents: dict[ast.AST, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[child] = parent
    return parents


def _is_query_artifact(rel: str) -> bool:
    name = Path(rel).name
    return name.endswith("_queries.py") or name in {"query_templates.py"}


def check_long_cypher(root: Path, files: Sequence[Path], allowlist: Mapping[str, Any]) -> list[Violation]:
    violations: list[Violation] = []
    for path in _python_files(files):
        rel = _rel(path, root)
        if _is_query_artifact(rel):
            continue
        try:
            tree = ast.parse(_read_text(path), filename=rel)
        except SyntaxError:
            continue
        parents = _parent_map(tree)
        for node in ast.walk(tree):
            value: str | None = None
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                value = node.value
            if not value:
                continue
            upper = value.upper()
            if not ("MATCH" in upper and "RETURN" in upper):
                continue
            lines = [line for line in value.strip().splitlines() if line.strip()]
            if len(lines) <= 60:
                continue
            name = _cypher_string_name(parents.get(node, tree)) or "<string>"
            key = f"{rel}::{name}"
            entry = _allow_entry(allowlist, "long_cypher", key)
            if _allow_reason_ok(entry):
                continue
            violations.append(
                Violation(
                    "long-cypher-inline",
                    rel,
                    f"{len(lines)} Cypher lines; move query text into *_queries.py or an explicit query artifact",
                    symbol=name,
                    line=getattr(node, "lineno", None),
                )
            )
    return violations


def run_checks(
    root: Path,
    *,
    allowlist_path: Path | None = None,
    scan_roots: Sequence[str] = DEFAULT_SCAN_ROOTS,
    max_file_lines: int = DEFAULT_MAX_FILE_LINES,
    max_function_lines: int = DEFAULT_MAX_FUNCTION_LINES,
) -> list[Violation]:
    root = root.resolve()
    allowlist = _load_allowlist(allowlist_path)
    files = tuple(sorted(_iter_source_files(root, scan_roots)))
    violations: list[Violation] = []
    violations.extend(check_long_files(root, files, allowlist, max_lines=max_file_lines))
    violations.extend(check_long_functions(root, files, allowlist, max_lines=max_function_lines))
    violations.extend(check_store_score_math(root, files, allowlist))
    violations.extend(check_read_path_writes(root, files, allowlist))
    violations.extend(check_long_cypher(root, files, allowlist))
    return violations


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run repository review gates.")
    parser.add_argument("--root", default=".", help="repository root")
    parser.add_argument("--allowlist", default=DEFAULT_ALLOWLIST, help="JSON allowlist path relative to root")
    parser.add_argument("--scan-root", action="append", dest="scan_roots", help="source root to scan; may be repeated")
    parser.add_argument("--max-file-lines", type=int, default=DEFAULT_MAX_FILE_LINES)
    parser.add_argument("--max-function-lines", type=int, default=DEFAULT_MAX_FUNCTION_LINES)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    root = Path(args.root)
    allowlist = Path(args.allowlist)
    if not allowlist.is_absolute():
        allowlist = root / allowlist
    violations = run_checks(
        root,
        allowlist_path=allowlist,
        scan_roots=tuple(args.scan_roots or DEFAULT_SCAN_ROOTS),
        max_file_lines=args.max_file_lines,
        max_function_lines=args.max_function_lines,
    )
    if violations:
        print("review gates failed:", file=sys.stderr)
        for violation in violations:
            print(f"  {violation.render()}", file=sys.stderr)
        return 1
    print("review gates passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
