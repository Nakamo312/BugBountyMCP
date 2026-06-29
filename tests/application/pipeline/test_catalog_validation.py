from __future__ import annotations

import pytest

from api.application.pipeline.catalog import (
    resolve_parser_ref,
    resolve_runner_ref,
    validate_component_refs,
)
from api.application.pipeline.yaml_config import PipelineNodeSpec, load_pipeline_config
from api.infrastructure.parsers.httpx_parser import HTTPXProcessEventParser
from api.infrastructure.runners.cli_tool import CliToolRunnerRef


def test_resolve_cli_tool_runner_ref_from_pipeline_name() -> None:
    ref = resolve_runner_ref("cli_tool:dnsx:ptr", "dnsx_ptr")

    assert isinstance(ref, CliToolRunnerRef)
    assert ref.tool_name == "dnsx"
    assert dict(ref.default_options) == {"mode": "ptr"}
    assert str(ref) == "cli_tool:dnsx:ptr"


def test_legacy_runner_name_resolves_to_cli_tool_ref() -> None:
    ref = resolve_runner_ref("HTTPXCliRunner", "httpx")

    assert isinstance(ref, CliToolRunnerRef)
    assert ref.tool_name == "httpx"


def test_cli_tool_parser_can_default_to_spec_parser() -> None:
    ref = resolve_runner_ref("cli_tool:httpx", "httpx")

    assert resolve_parser_ref(None, ref, "httpx") is HTTPXProcessEventParser


def test_validate_component_refs_accepts_cli_tool_parser_from_spec() -> None:
    validate_component_refs(
        {
            "httpx": PipelineNodeSpec(
                type="scan",
                runner="cli_tool:httpx",
            )
        }
    )


def test_validate_component_refs_requires_parser_for_custom_runner() -> None:
    with pytest.raises(
        ValueError,
        match="Pipeline node 'subjack' with runner 'SubjackCliRunner' must define a parser",
    ):
        validate_component_refs(
            {
                "subjack": PipelineNodeSpec(
                    type="scan",
                    runner="SubjackCliRunner",
                )
            }
        )


def test_cli_tool_variants_live_on_specs() -> None:
    ref = resolve_runner_ref("cli_tool:mapcidr:aggregate", "mapcidr_aggregate")

    assert isinstance(ref, CliToolRunnerRef)
    assert ref.tool_name == "mapcidr"
    assert dict(ref.default_options) == {"mode": "aggregate"}


def test_active_katana_pipeline_uses_canonical_url_evidence_route() -> None:
    config = load_pipeline_config()
    katana = config.workers["katana"]

    assert katana.runner == "cli_tool:katana"
    assert katana.parser is None
    assert katana.processor == "UrlEvidenceBatchProcessor"
    assert katana.ingestor == "CanonicalIngestorRouter"


def test_active_ffuf_pipeline_uses_canonical_url_evidence_route() -> None:
    config = load_pipeline_config()
    ffuf = config.workers["ffuf"]

    assert ffuf.runner == "cli_tool:ffuf"
    assert ffuf.parser is None
    assert ffuf.processor == "UrlEvidenceBatchProcessor"
    assert ffuf.ingestor == "CanonicalIngestorRouter"
