"""Whitelisted pipeline component catalog for YAML node specs."""
from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from api.application.pipeline.canonical_processor import (
    CanonicalBatchProcessor,
    ServiceFindingBatchProcessor,
    UrlEvidenceBatchProcessor,
)
from api.application.pipeline.yaml_config import PipelineNodeSpec
from api.application.services.batch_processor import (
    AmassBatchProcessor,
    ASNMapBatchProcessor,
    DNSxBatchProcessor,
    HTTPXBatchProcessor,
    MantraBatchProcessor,
    MapCIDRBatchProcessor,
    PlaywrightBatchProcessor,
    SmapBatchProcessor,
    SubjackBatchProcessor,
    TLSxBatchProcessor,
)
from api.infrastructure.ingestors.amass_ingestor import AmassResultIngestor
from api.infrastructure.ingestors.asnmap_ingestor import ASNMapResultIngestor
from api.infrastructure.ingestors.dnsx_ingestor import DNSxDiscoveryResultIngestor, DNSxResultIngestor
from api.infrastructure.ingestors.canonical_router import CanonicalIngestorRouter
from api.infrastructure.ingestors.fuzz_finding_ingestor import FuzzFindingIngestor
from api.infrastructure.ingestors.host_finding_ingestor import HostFindingIngestor
from api.infrastructure.ingestors.host_ingestor import HostIngestor
from api.infrastructure.ingestors.javascript_reference_finding_ingestor import (
    JavaScriptReferenceFindingIngestor,
)
from api.infrastructure.ingestors.url_finding_ingestor import UrlFindingIngestor
from api.infrastructure.ingestors.httpx_ingestor import HTTPXResultIngestor
from api.infrastructure.ingestors.katana_ingestor import KatanaResultIngestor
from api.infrastructure.ingestors.linkfinder_ingestor import LinkFinderResultIngestor
from api.infrastructure.ingestors.mantra_ingestor import MantraResultIngestor
from api.infrastructure.ingestors.naabu_ingestor import NaabuResultIngestor
from api.infrastructure.ingestors.service_finding_ingestor import ServiceFindingIngestor
from api.infrastructure.ingestors.smap_ingestor import SmapResultIngestor
from api.infrastructure.ingestors.subjack_ingestor import SubjackResultIngestor
from api.infrastructure.ingestors.tlsx_ingestor import TLSxResultIngestor
from api.infrastructure.parsers.amass_parser import AmassGraphParser
from api.infrastructure.parsers.httpx_parser import HTTPXProcessEventParser
from api.infrastructure.parsers.line_process_event_parsers import (
    FFUFStdoutParser,
    Hakip2HostStdoutParser,
    KatanaStdoutParser,
    LinkFinderStdoutParser,
    MantraStdoutParser,
        NaabuStdoutParser,
    StdoutLineResultParser,
    SubjackStdoutParser,
    SubfinderStdoutParser,
    URLStdoutLineResultParser,
    WaymoreStdoutParser,
)
from api.infrastructure.parsers.process_event_parsers import (
    JSONStdoutItemsProcessEventParser,
    JSONStdoutProcessEventParser,
)
from api.infrastructure.runners.cli_specs.registry import CLI_TOOL_SPECS
from api.application.ports.runners import ToolRunnerRef
from api.infrastructure.runners.cli_tool import ProcessEventParser
from api.infrastructure.runners.playwright_cli import PlaywrightCliRunner
from api.infrastructure.runners.subjack_cli import SubjackCliRunner

RunnerRef = type[Any] | ToolRunnerRef | None

RUNNERS: dict[str, type[Any]] = {
    cls.__name__: cls
    for cls in (
        PlaywrightCliRunner,
        SubjackCliRunner,
    )
}

LEGACY_CLI_RUNNERS: dict[str, ToolRunnerRef] = {
    "AmassCliRunner": ToolRunnerRef("amass", label="cli_tool:amass"),
    "ASNMapCliRunner": ToolRunnerRef("asnmap", label="cli_tool:asnmap"),
    "DNSxCliRunner": ToolRunnerRef("dnsx", label="cli_tool:dnsx"),
    "DNSxDeepRunner": ToolRunnerRef("dnsx", {"mode": "deep"}, "cli_tool:dnsx:deep"),
    "DNSxPtrRunner": ToolRunnerRef("dnsx", {"mode": "ptr"}, "cli_tool:dnsx:ptr"),
    "FFUFCliRunner": ToolRunnerRef("ffuf", label="cli_tool:ffuf"),
    "Hakip2HostCliRunner": ToolRunnerRef("hakip2host", label="cli_tool:hakip2host"),
    "HTTPXCliRunner": ToolRunnerRef("httpx", label="cli_tool:httpx"),
    "KatanaCliRunner": ToolRunnerRef("katana", label="cli_tool:katana"),
    "LinkFinderCliRunner": ToolRunnerRef("linkfinder", label="cli_tool:linkfinder"),
    "MantraCliRunner": ToolRunnerRef("mantra", label="cli_tool:mantra"),
    "MapCIDRCliRunner": ToolRunnerRef("mapcidr", label="cli_tool:mapcidr"),
    "MapCIDRExpandRunner": ToolRunnerRef(
        "mapcidr",
        {"mode": "expand"},
        "cli_tool:mapcidr:expand",
    ),
    "NaabuCliRunner": ToolRunnerRef("naabu", label="cli_tool:naabu"),
    "SmapCliRunner": ToolRunnerRef("smap", label="cli_tool:smap"),
    "SubfinderCliRunner": ToolRunnerRef("subfinder", label="cli_tool:subfinder"),
    "TLSxCliRunner": ToolRunnerRef("tlsx", label="cli_tool:tlsx"),
    "TLSxDefaultRunner": ToolRunnerRef("tlsx", label="cli_tool:tlsx:default"),
    "WaymoreCliRunner": ToolRunnerRef("waymore", label="cli_tool:waymore"),
}


PROCESSORS: dict[str, type[Any]] = {
    cls.__name__: cls
    for cls in (
        ASNMapBatchProcessor,
        AmassBatchProcessor,
        CanonicalBatchProcessor,
        ServiceFindingBatchProcessor,
        UrlEvidenceBatchProcessor,
        DNSxBatchProcessor,
        HTTPXBatchProcessor,
        MantraBatchProcessor,
        MapCIDRBatchProcessor,
        PlaywrightBatchProcessor,
        SmapBatchProcessor,
        SubjackBatchProcessor,
        TLSxBatchProcessor,
    )
}
PROCESSORS["UrlFindingBatchProcessor"] = UrlEvidenceBatchProcessor

PARSERS: dict[str, type[Any]] = {
    cls.__name__: cls
    for cls in (
        AmassGraphParser,
        FFUFStdoutParser,
        Hakip2HostStdoutParser,
        HTTPXProcessEventParser,
        JSONStdoutItemsProcessEventParser,
        JSONStdoutProcessEventParser,
        KatanaStdoutParser,
        LinkFinderStdoutParser,
        MantraStdoutParser,
        NaabuStdoutParser,
        StdoutLineResultParser,
        SubjackStdoutParser,
        SubfinderStdoutParser,
        URLStdoutLineResultParser,
        WaymoreStdoutParser,
    )
}


INGESTORS: dict[str, type[Any]] = {
    cls.__name__: cls
    for cls in (
        AmassResultIngestor,
        ASNMapResultIngestor,
        DNSxDiscoveryResultIngestor,
        DNSxResultIngestor,
        CanonicalIngestorRouter,
        FuzzFindingIngestor,
        HostFindingIngestor,
        HostIngestor,
        JavaScriptReferenceFindingIngestor,
        HTTPXResultIngestor,
        KatanaResultIngestor,
        LinkFinderResultIngestor,
        MantraResultIngestor,
        NaabuResultIngestor,
        ServiceFindingIngestor,
        SmapResultIngestor,
        SubjackResultIngestor,
        TLSxResultIngestor,
        UrlFindingIngestor,
    )
}


def validate_component_refs(workers: Mapping[str, PipelineNodeSpec]) -> None:
    for node_id, spec in workers.items():
        runner_ref = resolve_runner_ref(spec.runner, node_id)
        parser_ref = resolve_parser_ref(spec.parser, runner_ref, node_id)
        if spec.runner is not None and parser_ref is None:
            raise ValueError(
                f"Pipeline node '{node_id}' with runner '{spec.runner}' must define a parser"
            )
        if spec.processor is not None:
            resolve_component(PROCESSORS, spec.processor, "processor", node_id)
        if spec.ingestor is not None:
            resolve_component(INGESTORS, spec.ingestor, "ingestor", node_id)


def resolve_runner_ref(name: str | None, node_id: str) -> RunnerRef:
    if name is None:
        return None
    if name.startswith("cli_tool:"):
        return _cli_tool_ref(name, node_id)
    if name in LEGACY_CLI_RUNNERS:
        return LEGACY_CLI_RUNNERS[name]
    return resolve_component(RUNNERS, name, "runner", node_id)


def _cli_tool_ref(name: str, node_id: str) -> ToolRunnerRef:
    parts = name.split(":")
    if len(parts) not in {2, 3} or parts[0] != "cli_tool" or not parts[1]:
        raise ValueError(
            f"Invalid runner '{name}' for pipeline node '{node_id}'. "
            "Expected 'cli_tool:<tool>' or 'cli_tool:<tool>:<variant>'."
        )
    tool_name = parts[1]
    if tool_name not in CLI_TOOL_SPECS:
        known = ", ".join(sorted(CLI_TOOL_SPECS))
        raise ValueError(
            f"Unknown CLI tool '{tool_name}' for pipeline node '{node_id}'. "
            f"Known values: {known}"
        )
    return ToolRunnerRef(
        tool_name,
        _variant_options(tool_name, parts[2] if len(parts) == 3 else None),
        name,
    )


def _variant_options(tool_name: str, variant: str | None) -> dict[str, Any]:
    try:
        return CLI_TOOL_SPECS[tool_name].variant_options(variant)
    except ValueError as exc:
        raise ValueError(str(exc)) from exc


def resolve_parser_ref(
    name: str | None,
    runner: RunnerRef,
    node_id: str,
) -> Callable[[], ProcessEventParser] | None:
    if name is not None:
        return resolve_component(PARSERS, name, "parser", node_id)
    if isinstance(runner, ToolRunnerRef):
        return CLI_TOOL_SPECS[runner.tool_name].parser_factory
    return None


def resolve_component(catalog: dict[str, type[Any]], name: str | None, field_name: str, node_id: str):
    if name is None:
        return None
    try:
        return catalog[name]
    except KeyError as exc:
        known = ", ".join(sorted(catalog))
        raise ValueError(
            f"Unknown {field_name} '{name}' for pipeline node '{node_id}'. "
            f"Known values: {known}"
        ) from exc
