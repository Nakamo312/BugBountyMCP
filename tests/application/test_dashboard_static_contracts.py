from __future__ import annotations

import re
from pathlib import Path


def _lucide_imports(source: str) -> set[str]:
    match = re.search(r"from 'lucide-react'", source)
    assert match is not None
    prefix = source[: match.start()]
    import_start = prefix.rfind("import {")
    assert import_start != -1
    block = source[import_start + len("import {") : match.start()]
    return {name.strip().strip(",") for name in block.splitlines() if name.strip()}


def test_agent_task_detail_imports_every_lucide_icon_it_uses() -> None:
    source = Path("BugBountyDashBoard/src/pages/AgentTaskDetail.jsx").read_text(
        encoding="utf-8"
    )

    imported = _lucide_imports(source)

    assert "Inbox" in imported
