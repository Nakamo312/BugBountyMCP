from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from api.infrastructure.parsers.httpx_parser import HTTPXProcessEventParser
from api.infrastructure.parsers.line_process_event_parsers import FFUFStdoutParser
from api.infrastructure.runners.cli_command import as_list, stdin_lines
from api.infrastructure.runners.cli_specs.common import number_arg
from api.infrastructure.runners.cli_tool import CliCommandPlan, CliToolSpec


def _ffuf_commands(
    executable: str,
    target_url: str,
    *,
    wordlist: str,
    rate_limit: int,
    rate: int | float | None = None,
    concurrency: int | None = None,
) -> Iterable[CliCommandPlan]:
    command = [
        executable,
        "-u",
        f"{target_url}/FUZZ",
        "-w",
        wordlist,
        "-recursion",
        "-json",
        "-p",
        "0.1-0.3",
        "-se",
        "-sf",
        "-ac",
        "-rate",
        number_arg(rate_limit if rate is None else rate),
    ]
    if concurrency is not None:
        command.extend(["-t", str(concurrency)])
    yield CliCommandPlan(command, label="ffuf")


def _ffuf_options(settings: Any) -> dict[str, Any]:
    return {
        "wordlist": settings.FFUF_WORDLIST,
        "rate_limit": settings.FFUF_RATE_LIMIT,
    }


def _httpx_commands(
    executable: str,
    targets: list[str] | str,
    *,
    concurrency: int | None = None,
) -> Iterable[CliCommandPlan]:
    values = as_list(targets)
    command = [
        executable,
        "-json",
        "-silent",
        "-status-code",
        "-tech-detect",
        "-title",
        "-ip",
        "-cdn",
        "-asn",
        "-favicon",
        "-method",
        "-cname",
        "-websocket",
        "-extract-fqdn",
        "-follow-redirects",
        "-filter-duplicates",
        "-t",
        str(min(len(values), 20, concurrency or 20)),
        "-s",
    ]
    if isinstance(targets, str):
        yield CliCommandPlan(command + ["-u", targets], label="httpx")
    else:
        yield CliCommandPlan(command, stdin=stdin_lines(values), label="httpx")


FFUF_SPEC = CliToolSpec(
    name="ffuf",
    executable="ffuf",
    build_commands=_ffuf_commands,
    parser_factory=FFUFStdoutParser,
    timeout=600,
    static_options_from_settings=_ffuf_options,
)
HTTPX_SPEC = CliToolSpec(
    name="httpx",
    executable="httpx",
    build_commands=_httpx_commands,
    parser_factory=HTTPXProcessEventParser,
    timeout=600,
)

HTTP_SPECS = (FFUF_SPEC, HTTPX_SPEC)
