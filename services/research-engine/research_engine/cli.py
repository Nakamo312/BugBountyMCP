from __future__ import annotations

import argparse
import os
from dataclasses import asdict
from typing import Any

from research_engine.evidence_packs import build_observation_pack
from research_engine.gatekeeper import GatekeeperDecision, validate_generator_output
from research_engine.generators import FixtureHypothesisGenerator
from research_engine.postgres import (
    fetch_observation_rows,
    finish_producer_run,
    start_producer_run,
    upsert_research_rows,
)
from research_engine.writer import build_research_rows

PRODUCER_NAME = "semantic-research-engine"
PRODUCER_VERSION = "semantic-research-engine-v1"
RULE_VERSION = "semantic-pipeline-v1"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="research-engine")
    subparsers = parser.add_subparsers(dest="command", required=True)

    produce = subparsers.add_parser(
        "produce-semantic-hypotheses",
        help="Build evidence-bound semantic research hypotheses from sanitized observations.",
    )
    produce.add_argument("--limit", type=int, default=1000)
    produce.add_argument("--generator", choices=("fixture",), default="fixture")
    produce.add_argument("--dsn", default=None)
    produce.set_defaults(func=_run_produce_semantic_hypotheses)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


def _run_produce_semantic_hypotheses(args: argparse.Namespace) -> int:
    dsn = args.dsn or os.environ.get("POSTGRES_DSN", "")
    producer_run_id = start_producer_run(
        dsn,
        producer_name=PRODUCER_NAME,
        producer_version=PRODUCER_VERSION,
        rule_version=RULE_VERSION,
    )
    stats: dict[str, Any] = {
        "observations": 0,
        "packs": 0,
        "hypotheses": 0,
        "accepted": 0,
        "rejected": 0,
    }

    try:
        rows = fetch_observation_rows(dsn, limit=args.limit)
        stats["observations"] = len(rows)
        generator = FixtureHypothesisGenerator()

        for row in rows:
            pack = build_observation_pack(row)
            stats["packs"] += 1
            generator_output = generator.generate([pack])
            stats["hypotheses"] += len(generator_output.get("hypotheses") or [])
            available_refs = {ref.id for ref in pack.evidence_refs}
            decision = validate_generator_output(generator_output, available_evidence_ref_ids=available_refs)
            if decision.status == GatekeeperDecision.REJECT:
                stats["rejected"] += len(generator_output.get("hypotheses") or [])
                continue
            approved_output = decision.output or generator_output
            research_rows = build_research_rows(
                program_id=pack.program_id,
                producer_run_id=producer_run_id,
                pack_id=pack.pack_id,
                pack_evidence_refs=[asdict(ref) for ref in pack.evidence_refs],
                generator_output=approved_output,
            )
            upsert_research_rows(dsn, research_rows)
            stats["accepted"] += len(research_rows.hypotheses)

        finish_producer_run(dsn, producer_run_id=producer_run_id, status="completed", stats=stats)
        return 0
    except Exception as exc:
        finish_producer_run(dsn, producer_run_id=producer_run_id, status="failed", stats=stats, error=str(exc))
        raise


if __name__ == "__main__":
    raise SystemExit(main())
