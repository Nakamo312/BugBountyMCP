from __future__ import annotations

from collections.abc import Iterable
from urllib.parse import urlparse

from api.infrastructure.parsers.line_process_event_parsers import (
    KatanaStdoutParser,
    LinkFinderStdoutParser,
    MantraStdoutParser,
    WaymoreStdoutParser,
)
from api.infrastructure.runners.cli_command import as_list, stdin_lines
from api.infrastructure.runners.cli_tool import CliCommandPlan, CliToolSpec, ToolErrorPolicy
from api.application.process_event_contracts import ProcessEvent


def _katana_commands(
    executable: str,
    targets: list[str] | str,
    *,
    depth: int = 3,
    js_crawl: bool = True,
    headless: bool = True,
    concurrency: int = 1,
) -> Iterable[CliCommandPlan]:
    command = [
        executable,
        "-list",
        "-",
        "-d",
        str(depth),
        "-silent",
        "-jsonl",
        "-aff",
        "-xhr",
        "-time-stable",
        "10",
        "-mfc",
        "100",
        "-nos",
        "-c",
        str(concurrency),
        "-p",
        str(concurrency),
        "-j",
        "-tech-detect",
        "-known-files",
        "sitemapxml",
        "-f",
        "qurl",
        "-ef",
        "png,jpg,jpeg,gif,svg,ico,css,woff,woff2,ttf,eot,otf,mp4,mp3,avi,webm,flv,wav,pdf,zip,tar,gz,rar,7z,exe,dll,bin,dmg,iso",
    ]
    if headless:
        command.append("-hl")
    if js_crawl:
        command.append("-jc")
    yield CliCommandPlan(command, stdin=stdin_lines(as_list(targets)), label="katana")


def _linkfinder_commands(executable: str, js_urls: list[str]) -> Iterable[CliCommandPlan]:
    for target in js_urls:
        parsed = urlparse(target)
        host = parsed.hostname or parsed.netloc
        if not host:
            continue
        command = [executable, "-i", target]
        if not parsed.path or parsed.path == "/" or "*" in target:
            command.append("-d")
        yield CliCommandPlan(
            command + ["-o", "cli"],
            label="linkfinder",
            error_policy=ToolErrorPolicy.LOG_AND_CONTINUE,
            before_events=(
                ProcessEvent(type="target", payload={"target": target, "host": host}),
            ),
        )


def _mantra_commands(executable: str, js_urls: list[str]) -> Iterable[CliCommandPlan]:
    if js_urls:
        yield CliCommandPlan(
            [executable, "-s"],
            stdin=stdin_lines(js_urls),
            label="mantra",
            error_policy=ToolErrorPolicy.LOG_AND_CONTINUE,
        )


def _waymore_commands(executable: str, targets: list[str] | str) -> Iterable[CliCommandPlan]:
    command = [
        executable,
        "-i",
        "-",
        "-mode",
        "U",
        "-oU",
        "-",
        "--stream",
        "-xcc",
        "-fc",
        "404,410,429,500,502,503",
        "-t",
        "30",
    ]
    yield CliCommandPlan(command, stdin=stdin_lines(as_list(targets)), label="waymore")


KATANA_SPEC = CliToolSpec(
    name="katana",
    executable="katana",
    build_commands=_katana_commands,
    parser_factory=KatanaStdoutParser,
    timeout=600,
)
LINKFINDER_SPEC = CliToolSpec(
    name="linkfinder",
    executable="linkfinder",
    build_commands=_linkfinder_commands,
    parser_factory=LinkFinderStdoutParser,
    timeout=15,
)
MANTRA_SPEC = CliToolSpec(
    name="mantra",
    executable="mantra",
    build_commands=_mantra_commands,
    parser_factory=MantraStdoutParser,
    timeout=300,
)
WAYMORE_SPEC = CliToolSpec(
    name="waymore",
    executable="waymore",
    build_commands=_waymore_commands,
    parser_factory=WaymoreStdoutParser,
    timeout=1800,
)

JS_SPECS = (KATANA_SPEC, LINKFINDER_SPEC, MANTRA_SPEC, WAYMORE_SPEC)
