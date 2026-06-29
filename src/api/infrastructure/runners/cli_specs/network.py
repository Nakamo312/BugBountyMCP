from __future__ import annotations

from collections.abc import Iterable

from api.infrastructure.parsers.line_process_event_parsers import (
    NaabuStdoutParser,
    StdoutLineResultParser,
)
from api.infrastructure.parsers.process_event_parsers import (
    JSONStdoutItemsProcessEventParser,
    JSONStdoutProcessEventParser,
)
from api.infrastructure.runners.cli_command import as_list, stdin_lines
from api.infrastructure.runners.cli_specs.common import number_arg
from api.infrastructure.runners.cli_tool import CliCommandPlan, CliToolSpec


def _mapcidr_commands(
    executable: str,
    values: list[str] | str,
    *,
    mode: str = "expand",
    skip_base: bool = False,
    skip_broadcast: bool = False,
    shuffle: bool = False,
    count: int | None = None,
    host_count: int | None = None,
) -> Iterable[CliCommandPlan]:
    command = [executable, "-silent"]
    if mode == "expand":
        if skip_base:
            command.append("-skip-base")
        if skip_broadcast:
            command.append("-skip-broadcast")
        if shuffle:
            command.append("-si")
    elif mode == "slice_by_count":
        command.extend(["-sbc", str(count)])
    elif mode == "slice_by_host_count":
        command.extend(["-sbh", str(host_count)])
    elif mode == "count_hosts":
        command.append("-count")
    elif mode == "aggregate":
        command.append("-aggregate")
    else:
        raise ValueError(f"Unsupported mapcidr mode: {mode}")
    yield CliCommandPlan(
        command,
        stdin=stdin_lines(as_list(values)),
        label=f"mapcidr {mode}",
    )


def _naabu_commands(
    executable: str,
    hosts: list[str] | str,
    *,
    ports: str | None = None,
    top_ports: str = "1000",
    rate: int = 1000,
    scan_mode: str = "active",
    scan_type: str = "c",
    exclude_cdn: bool = True,
    concurrency: int | None = None,
) -> Iterable[CliCommandPlan]:
    hosts = as_list(hosts)
    if scan_mode == "passive":
        yield CliCommandPlan(
            [executable, "-json", "-silent", "-passive"],
            stdin=stdin_lines(hosts),
            label="naabu",
        )
        return
    if scan_mode != "active":
        raise ValueError(f"Unsupported naabu scan_mode: {scan_mode}")
    command = [executable, "-json", "-silent", "-s", scan_type, "-rate", number_arg(rate)]
    if concurrency is not None:
        command.extend(["-c", str(concurrency)])
    command.extend(["-p", ports] if ports else ["-top-ports", top_ports])
    if exclude_cdn:
        command.append("-exclude-cdn")
    yield CliCommandPlan(command, stdin=stdin_lines(hosts), label="naabu")


def _smap_commands(executable: str, targets: list[str]) -> Iterable[CliCommandPlan]:
    yield CliCommandPlan(
        [executable, "-iL", "-", "-oJ", "-"],
        stdin=stdin_lines(targets),
        label="smap",
    )


def _tlsx_commands(
    executable: str,
    targets: list[str] | str,
    *,
    ports: list[int] | None = None,
    include_cipher: bool = False,
    include_hash: bool = False,
    include_jarm: bool = False,
) -> Iterable[CliCommandPlan]:
    command = [executable, "-json", "-silent", "-san", "-cn"]
    for port in ports or [443, 8443]:
        command.extend(["-port", str(port)])
    if include_cipher:
        command.append("-cipher")
    if include_hash:
        command.extend(["-hash", "sha256"])
    if include_jarm:
        command.append("-jarm")
    yield CliCommandPlan(command, stdin=stdin_lines(as_list(targets)), label="tlsx")


MAPCIDR_SPEC = CliToolSpec(
    name="mapcidr",
    executable="mapcidr",
    build_commands=_mapcidr_commands,
    parser_factory=StdoutLineResultParser,
    timeout=300,
    variants={
        "expand": {"mode": "expand"},
        "slice_by_count": {"mode": "slice_by_count"},
        "slice_by_host_count": {"mode": "slice_by_host_count"},
        "count_hosts": {"mode": "count_hosts"},
        "aggregate": {"mode": "aggregate"},
    },
)
NAABU_SPEC = CliToolSpec(
    name="naabu",
    executable="naabu",
    build_commands=_naabu_commands,
    parser_factory=NaabuStdoutParser,
    timeout=600,
)
SMAP_SPEC = CliToolSpec(
    name="smap",
    executable="smap",
    build_commands=_smap_commands,
    parser_factory=JSONStdoutItemsProcessEventParser,
    timeout=600,
)
TLSX_SPEC = CliToolSpec(
    name="tlsx",
    executable="tlsx",
    build_commands=_tlsx_commands,
    parser_factory=JSONStdoutProcessEventParser,
    timeout=300,
)

NETWORK_SPECS = (MAPCIDR_SPEC, NAABU_SPEC, SMAP_SPEC, TLSX_SPEC)
