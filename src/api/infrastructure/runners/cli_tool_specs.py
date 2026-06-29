"""Compatibility facade for CLI tool specs grouped under cli_specs/."""
from __future__ import annotations

from api.infrastructure.runners.cli_specs.discovery import (
    AMASS_SPEC,
    ASNMAP_SPEC,
    HAKIP2HOST_SPEC,
    SUBFINDER_SPEC,
)
from api.infrastructure.runners.cli_specs.dns import DNSX_SPEC
from api.infrastructure.runners.cli_specs.http import FFUF_SPEC, HTTPX_SPEC
from api.infrastructure.runners.cli_specs.js import (
    KATANA_SPEC,
    LINKFINDER_SPEC,
    MANTRA_SPEC,
    WAYMORE_SPEC,
)
from api.infrastructure.runners.cli_specs.network import (
    MAPCIDR_SPEC,
    NAABU_SPEC,
    SMAP_SPEC,
    TLSX_SPEC,
)
from api.infrastructure.runners.cli_specs.registry import CLI_TOOL_SPECS

__all__ = [
    "AMASS_SPEC",
    "ASNMAP_SPEC",
    "CLI_TOOL_SPECS",
    "DNSX_SPEC",
    "FFUF_SPEC",
    "HAKIP2HOST_SPEC",
    "HTTPX_SPEC",
    "KATANA_SPEC",
    "LINKFINDER_SPEC",
    "MANTRA_SPEC",
    "MAPCIDR_SPEC",
    "NAABU_SPEC",
    "SMAP_SPEC",
    "SUBFINDER_SPEC",
    "TLSX_SPEC",
    "WAYMORE_SPEC",
]
