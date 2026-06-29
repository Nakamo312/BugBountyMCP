from __future__ import annotations

from collections.abc import Iterable

from api.infrastructure.parsers.process_event_parsers import JSONStdoutProcessEventParser
from api.infrastructure.runners.cli_command import as_list, stdin_lines
from api.infrastructure.runners.cli_tool import CliCommandPlan, CliToolSpec


def _dnsx_commands(
    executable: str,
    values: list[str] | str,
    *,
    mode: str = "deep",
) -> Iterable[CliCommandPlan]:
    values = as_list(values)
    base = [executable, "-json", "-silent"]
    if mode == "ptr":
        flags = ["-ptr"]
    elif mode == "deep":
        flags = ["-a", "-aaaa", "-cname", "-mx", "-txt", "-ns", "-soa"]
    else:
        raise ValueError(f"Unsupported dnsx mode: {mode}")
    yield CliCommandPlan(
        base + flags + ["-resp-only", "-t", str(min(len(values), 100))],
        stdin=stdin_lines(values),
        label=f"dnsx {mode}",
    )


DNSX_SPEC = CliToolSpec(
    name="dnsx",
    executable="dnsx",
    build_commands=_dnsx_commands,
    parser_factory=JSONStdoutProcessEventParser,
    timeout=600,
    variants={
        "deep": {"mode": "deep"},
        "ptr": {"mode": "ptr"},
    },
)

DNS_SPECS = (DNSX_SPEC,)
