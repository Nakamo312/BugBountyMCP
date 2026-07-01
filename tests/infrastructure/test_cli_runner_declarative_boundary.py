from __future__ import annotations

from pathlib import Path

from api.infrastructure.runners.cli_specs.registry import CLI_TOOL_SPECS

ROOT = Path(".")
RUNNERS_ROOT = ROOT / "src/api/infrastructure/runners"

DECLARATIVE_CLI_TOOLS = {
    "amass",
    "asnmap",
    "dnsx",
    "ffuf",
    "hakip2host",
    "httpx",
    "katana",
    "linkfinder",
    "mantra",
    "mapcidr",
    "naabu",
    "smap",
    "subfinder",
    "tlsx",
    "waymore",
}

REMOVED_WRAPPER_MODULES = {
    "amass_cli.py",
    "asnmap_cli.py",
    "dnsx_cli.py",
    "dnsx_runners.py",
    "ffuf_cli.py",
    "hakip2host_cli.py",
    "httpx_cli.py",
    "katana_cli.py",
    "linkfinder_cli.py",
    "mantra_cli.py",
    "mapcidr_cli.py",
    "mapcidr_runners.py",
    "naabu_cli.py",
    "smap_cli.py",
    "subfinder_cli.py",
    "tlsx_cli.py",
    "tlsx_runners.py",
    "waymore_cli.py",
    "cli_tool_specs.py",
}


def test_common_cli_tools_are_declarative_specs() -> None:
    assert DECLARATIVE_CLI_TOOLS <= set(CLI_TOOL_SPECS)


def test_declarative_cli_tools_do_not_have_wrapper_modules() -> None:
    existing = sorted(
        module.name for module in RUNNERS_ROOT.iterdir() if module.name in REMOVED_WRAPPER_MODULES
    )

    assert existing == []


def test_remaining_runner_classes_are_intentional_special_cases() -> None:
    remaining = sorted(path.name for path in RUNNERS_ROOT.glob("*_cli.py"))

    assert remaining == ["playwright_cli.py", "subjack_cli.py"]
