from __future__ import annotations

import re
from uuid import uuid4


def _safe_graph_name(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]{0,80}", value):
        raise ValueError("unsafe GDS graph name")
    return value


def _safe_probe_id(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", value):
        raise ValueError("unsafe surface component probe id")
    return value


def _unique_graph_name(prefix: str) -> str:
    safe_prefix = _safe_graph_name(prefix)
    max_prefix = 64
    if len(safe_prefix) > max_prefix:
        safe_prefix = safe_prefix[:max_prefix].rstrip("_.-") or "surface_graph"
    return _safe_graph_name(f"{safe_prefix}_{uuid4().hex[:12]}")
