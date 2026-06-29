from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from api.infrastructure.parsers.amass_parser import AmassGraphParser
from api.infrastructure.parsers.line_process_event_parsers import (
    Hakip2HostStdoutParser,
    SubfinderStdoutParser,
)
from api.infrastructure.parsers.process_event_parsers import JSONStdoutProcessEventParser
from api.infrastructure.runners.cli_command import as_list, stdin_lines
from api.infrastructure.runners.cli_tool import CliCommandPlan, CliToolSpec


def _amass_commands(
    executable: str,
    domain: str,
    *,
    active: bool = False,
    wordlist: str | None = None,
) -> Iterable[CliCommandPlan]:
    command = [executable, "enum", "-d", domain]
    if active:
        command.append("-active")
        if wordlist:
            command.extend(["-brute", "-w", wordlist])
    yield CliCommandPlan(command, label="amass")


def _amass_options(settings: Any) -> dict[str, Any]:
    return {"wordlist": settings.AMASS_WORDLIST}


def _asnmap_commands(
    executable: str,
    values: list[str] | str,
    *,
    option: str = "-d",
) -> Iterable[CliCommandPlan]:
    command = [executable, "-json", "-silent", "-duc"]
    for value in as_list(values):
        command.extend([option, value])
    yield CliCommandPlan(command, label="asnmap")


def _hakip2host_commands(
    executable: str,
    targets: list[str],
) -> Iterable[CliCommandPlan]:
    yield CliCommandPlan([executable], stdin=stdin_lines(targets), label="hakip2host")


def _subfinder_commands(
    executable: str,
    targets: list[str],
) -> Iterable[CliCommandPlan]:
    for domain in targets:
        yield CliCommandPlan(
            [executable, "-d", domain, "-silent", "-all", "-json"],
            label="subfinder",
        )


AMASS_SPEC = CliToolSpec(
    name="amass",
    executable="amass",
    build_commands=_amass_commands,
    parser_factory=AmassGraphParser,
    timeout=1800,
    static_options_from_settings=_amass_options,
)
ASNMAP_SPEC = CliToolSpec(
    name="asnmap",
    executable="asnmap",
    build_commands=_asnmap_commands,
    parser_factory=JSONStdoutProcessEventParser,
    timeout=300,
)
HAKIP2HOST_SPEC = CliToolSpec(
    name="hakip2host",
    executable="hakip2host",
    build_commands=_hakip2host_commands,
    parser_factory=Hakip2HostStdoutParser,
    timeout=300,
)
SUBFINDER_SPEC = CliToolSpec(
    name="subfinder",
    executable="subfinder",
    build_commands=_subfinder_commands,
    parser_factory=SubfinderStdoutParser,
    timeout=600,
)

DISCOVERY_SPECS = (AMASS_SPEC, ASNMAP_SPEC, HAKIP2HOST_SPEC, SUBFINDER_SPEC)
