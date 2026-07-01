from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
RENDER_ROOT = REPO_ROOT / "services" / "bb-cli" / "bb_cli" / "render"


def test_bb_cli_render_stays_packaged() -> None:
    assert not (REPO_ROOT / "services" / "bb-cli" / "bb_cli" / "render.py").exists()
    expected = {
        "__init__.py",
        "activity.py",
        "common.py",
        "projection.py",
        "proposals.py",
        "tasks.py",
        "worker.py",
        "workspace.py",
    }
    assert expected <= {path.name for path in RENDER_ROOT.iterdir()}


def test_projection_rendering_uses_shared_boundary_renderer() -> None:
    projection_source = (RENDER_ROOT / "projection.py").read_text(encoding="utf-8")
    assert "append_boundary" in projection_source
    assert projection_source.count("Boundary") == 0
    assert 'lines.append(f"  {key}: {value}")' not in projection_source


def test_render_allowlist_does_not_keep_removed_render_file() -> None:
    allowlist_source = (REPO_ROOT / "governance" / "review_gates_allowlist.json").read_text(encoding="utf-8")
    assert "services/bb-cli/bb_cli/render.py" not in allowlist_source
