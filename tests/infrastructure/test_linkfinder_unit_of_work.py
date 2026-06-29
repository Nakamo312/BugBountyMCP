from __future__ import annotations

from pathlib import Path


def test_linkfinder_unit_of_work_exposes_javascript_reference_repository() -> None:
    source = Path("src/api/infrastructure/unit_of_work/adapters/linkfinder.py").read_text(encoding="utf-8")
    interface = Path("src/api/infrastructure/unit_of_work/interfaces/linkfinder.py").read_text(encoding="utf-8")

    assert "JavaScriptReferenceRepository" in interface
    assert "SQLAlchemyJavaScriptReferenceRepository" in source
    assert "self.javascript_references = SQLAlchemyJavaScriptReferenceRepository" in source
