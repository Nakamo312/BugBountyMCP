from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import subprocess
import sys
from collections.abc import Mapping
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from api.application.workbench_projection_control import (
    WorkbenchProjectionOperation,
    WorkbenchProjectionRunRequest,
    WorkbenchProjectionRunResult,
    WorkbenchProjectionStepResult,
    workbench_projection_control_boundary,
)
from api.config import Settings
from api.infrastructure.adapters.orm_tables.surface_map import (
    surface_component_analysis_items,
    surface_component_analysis_runs,
    surface_nodes,
    surface_snapshots,
)


class WorkbenchProjectionControlStore:
    """Run a small set of safe projection refresh operations for Workbench UX.

    The UI must not force operators to copy UUIDs into docker-compose commands.
    This store owns the controlled backend execution path. It never accepts raw
    command text from the frontend.
    """

    def __init__(self, session_factory: async_sessionmaker, settings: Settings) -> None:
        self._session_factory = session_factory
        self._settings = settings

    async def run_projection_operation(
        self,
        request: WorkbenchProjectionRunRequest,
    ) -> WorkbenchProjectionRunResult:
        snapshot_id = request.snapshot_id
        steps: list[WorkbenchProjectionStepResult] = []

        if request.operation in {
            WorkbenchProjectionOperation.BUILD_SURFACE,
            WorkbenchProjectionOperation.REFRESH_WORKBENCH,
        }:
            surface_step = await asyncio.to_thread(self._build_surface_snapshot, request)
            steps.append(surface_step)
            if surface_step.snapshot_id is not None:
                snapshot_id = surface_step.snapshot_id
            if surface_step.status != "completed":
                return self._result(request, steps, status="failed", message=surface_step.message)

        if request.operation in {
            WorkbenchProjectionOperation.MATERIALIZE_COMPONENTS,
            WorkbenchProjectionOperation.REFRESH_WORKBENCH,
        }:
            if snapshot_id is None:
                snapshot_id = await self._latest_surface_snapshot_id(request.program_id)
            if snapshot_id is None:
                steps.append(
                    WorkbenchProjectionStepResult(
                        step_id="materialize-components",
                        status="skipped",
                        message="No surface snapshot exists yet; build surface first.",
                    )
                )
            else:
                component_step = await asyncio.to_thread(
                    self._materialize_surface_components,
                    request,
                    snapshot_id,
                )
                if component_step.status == "failed":
                    component_step = await self._materialize_surface_components_from_surface_snapshot(
                        request,
                        snapshot_id,
                        fallback_reason=component_step.message,
                    )
                steps.append(component_step)

        status = "completed"
        if any(step.status == "failed" for step in steps):
            status = "partial" if any(step.status == "completed" for step in steps) else "failed"
        elif any(step.status == "skipped" for step in steps):
            status = "partial"
        message = _status_message(status)
        return self._result(request, steps, status=status, message=message)

    def _build_surface_snapshot(
        self,
        request: WorkbenchProjectionRunRequest,
    ) -> WorkbenchProjectionStepResult:
        command = [
            sys.executable,
            "-m",
            "surface_engine",
            "build-snapshot",
            "--dsn",
            _postgres_dsn(self._settings),
            "--program-id",
            str(request.program_id),
            "--limit",
            str(request.limit),
        ]
        completed = self._run(command, timeout_seconds=180)
        if completed.returncode != 0:
            return WorkbenchProjectionStepResult(
                step_id="build-surface",
                status="failed",
                message=_stderr_or_stdout(completed) or "Surface snapshot build failed.",
                details={"returncode": completed.returncode},
            )
        payload = _json_stdout(completed)
        snapshot = payload.get("snapshot") if isinstance(payload.get("snapshot"), dict) else {}
        counts = {
            "nodes": int((payload.get("nodes") or {}).get("written") or (payload.get("nodes") or {}).get("count") or 0),
            "edges": int((payload.get("edges") or {}).get("written") or (payload.get("edges") or {}).get("count") or 0),
            "deltas": int((payload.get("deltas") or {}).get("written") or (payload.get("deltas") or {}).get("count") or 0),
        }
        return WorkbenchProjectionStepResult(
            step_id="build-surface",
            status="completed",
            message="Surface snapshot built from stored observations.",
            snapshot_id=_uuid_or_none(snapshot.get("id")),
            counts=counts,
            details={
                "algorithm": snapshot.get("algorithm"),
                "algorithm_version": snapshot.get("algorithm_version"),
                "previous_snapshot_id": snapshot.get("previous_snapshot_id"),
            },
        )

    def _materialize_surface_components(
        self,
        request: WorkbenchProjectionRunRequest,
        snapshot_id: UUID,
    ) -> WorkbenchProjectionStepResult:
        command = [
            sys.executable,
            "-m",
            "graph_projector",
            "surface-components-materialize",
            "--program-id",
            str(request.program_id),
            "--snapshot-id",
            str(snapshot_id),
            "--component-limit",
            str(request.component_limit),
            "--candidate-limit",
            str(request.candidate_limit),
            "--similarity-cutoff",
            str(request.similarity_cutoff),
            "--json",
        ]
        completed = self._run(command, timeout_seconds=240)
        if completed.returncode != 0:
            return WorkbenchProjectionStepResult(
                step_id="materialize-components",
                status="failed",
                message=_stderr_or_stdout(completed) or "Surface component materialization failed. Check graph projector / Neo4j availability.",
                snapshot_id=snapshot_id,
                details={"returncode": completed.returncode},
            )
        payload = _json_stdout(completed)
        counts = {
            "items": int(payload.get("item_count") or 0),
            "action_candidates": int(payload.get("action_candidate_count") or 0),
        }
        return WorkbenchProjectionStepResult(
            step_id="materialize-components",
            status="completed",
            message="Surface component analysis materialized for latest snapshot.",
            snapshot_id=snapshot_id,
            analysis_run_id=_uuid_or_none(payload.get("analysis_run_id")),
            counts=counts,
            details={
                "report_fingerprint": payload.get("report_fingerprint"),
                "previous_snapshot_id": payload.get("previous_snapshot_id"),
            },
        )

    async def _materialize_surface_components_from_surface_snapshot(
        self,
        request: WorkbenchProjectionRunRequest,
        snapshot_id: UUID,
        *,
        fallback_reason: str,
    ) -> WorkbenchProjectionStepResult:
        """Materialize a bounded component read model without Neo4j/GDS.

        This is not a replacement for GDS component analytics. It is the UI-safe
        fallback that prevents the dashboard from becoming unusable when the
        graph profile is not running. Components are deterministic route-family
        groups derived from the already persisted Surface Map snapshot.
        """
        async with self._session_factory() as session:
            rows = await self._surface_nodes_for_snapshot(session, request.program_id, snapshot_id)
        if not rows:
            return WorkbenchProjectionStepResult(
                step_id="materialize-components",
                status="skipped",
                message="Surface snapshot has no nodes to group into components.",
                snapshot_id=snapshot_id,
                details={"fallback_reason": fallback_reason},
            )
        grouped = _local_component_groups(rows, limit=request.component_limit)
        run_id = uuid4()
        fingerprint = _local_component_fingerprint(
            program_id=request.program_id,
            snapshot_id=snapshot_id,
            grouped=grouped,
            run_id=run_id,
        )
        async with self._session_factory() as session:
            async with session.begin():
                await session.execute(
                    insert(surface_component_analysis_runs).values(
                        id=run_id,
                        program_id=request.program_id,
                        snapshot_id=snapshot_id,
                        previous_snapshot_id=None,
                        algorithm="surface-local-route-family-components",
                        algorithm_version="surface-local-route-family-components-v1",
                        report_fingerprint=fingerprint,
                        settings_json={
                            "source": "workbench_projection_control",
                            "fallback": "neo4j_unavailable",
                            "component_limit": request.component_limit,
                            "candidate_limit": request.candidate_limit,
                        },
                        stats_json={
                            "component_count": len(grouped),
                            "source_node_count": len(rows),
                            "neo4j_fallback": True,
                        },
                    )
                )
                for component_id, group in enumerate(grouped):
                    await session.execute(
                        insert(surface_component_analysis_items).values(
                            id=uuid4(),
                            analysis_run_id=run_id,
                            program_id=request.program_id,
                            snapshot_id=snapshot_id,
                            component_id=component_id,
                            node_count=group["node_count"],
                            changed_node_count=0,
                            structural_pressure_score=group["structural_pressure_score"],
                            drift_score=None,
                            bridge_pressure_score=None,
                            outlier_score=None,
                            coverage_score=group["coverage_score"],
                            exploration_priority_score=group["exploration_priority_score"],
                            action_candidate_count=0,
                            metrics_json={
                                "source": "surface_snapshot_route_family_grouping",
                                "host": group["host"],
                                "route_family": group["route_family"],
                                "examples": group["examples"],
                                "note": "Deterministic UI fallback; not Neo4j/GDS analytics.",
                            },
                            action_candidates_json=[],
                        )
                    )
        return WorkbenchProjectionStepResult(
            step_id="materialize-components",
            status="completed",
            message="Neo4j/GDS component analytics were unavailable; materialized deterministic Surface Map route-family components so the dashboard remains usable.",
            snapshot_id=snapshot_id,
            analysis_run_id=run_id,
            counts={"items": len(grouped), "action_candidates": 0},
            details={
                "fallback": "surface_snapshot_route_family_grouping",
                "fallback_reason": _friendly_projection_error(fallback_reason),
                "gds_execution": "not_performed",
            },
        )

    async def _surface_nodes_for_snapshot(self, session: Any, program_id: UUID, snapshot_id: UUID) -> list[Mapping[str, Any]]:
        result = await session.execute(
            select(
                surface_nodes.c.id,
                surface_nodes.c.node_type,
                surface_nodes.c.host,
                surface_nodes.c.path,
                surface_nodes.c.route_template,
                surface_nodes.c.method,
                surface_nodes.c.status_code,
                surface_nodes.c.content_type,
            )
            .where(surface_nodes.c.program_id == program_id)
            .where(surface_nodes.c.snapshot_id == snapshot_id)
            .order_by(surface_nodes.c.host.asc().nulls_last(), surface_nodes.c.route_template.asc().nulls_last())
            .limit(5000)
        )
        return list(result.mappings().all())

    def _run(self, command: list[str], *, timeout_seconds: int) -> subprocess.CompletedProcess[str]:
        env = dict(os.environ)
        env.update(
            {
                "POSTGRES_HOST": self._settings.POSTGRES_HOST,
                "POSTGRES_PORT": str(self._settings.POSTGRES_PORT),
                "POSTGRES_DB": self._settings.POSTGRES_DB,
                "POSTGRES_USER": self._settings.POSTGRES_USER,
                "POSTGRES_PASSWORD": self._settings.POSTGRES_PASSWORD,
                "NEO4J_URI": self._settings.NEO4J_URI,
                "NEO4J_USER": self._settings.NEO4J_USER,
                "NEO4J_PASSWORD": self._settings.NEO4J_PASSWORD,
                "NEO4J_DATABASE": self._settings.NEO4J_DATABASE,
                "NEO4J_ENABLED": "true",
            }
        )
        return subprocess.run(
            command,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            timeout=timeout_seconds,
        )

    async def _latest_surface_snapshot_id(self, program_id: UUID) -> UUID | None:
        async with self._session_factory() as session:
            result = await session.execute(
                select(surface_snapshots.c.id)
                .where(surface_snapshots.c.program_id == program_id)
                .order_by(surface_snapshots.c.created_at.desc(), surface_snapshots.c.id.desc())
                .limit(1)
            )
            row = result.first()
            return row[0] if row else None

    def _result(
        self,
        request: WorkbenchProjectionRunRequest,
        steps: list[WorkbenchProjectionStepResult],
        *,
        status: str,
        message: str,
    ) -> WorkbenchProjectionRunResult:
        counts: dict[str, int] = {}
        for step in steps:
            for key, value in step.counts.items():
                counts[key] = counts.get(key, 0) + int(value)
        snapshot_id = next((step.snapshot_id for step in reversed(steps) if step.snapshot_id is not None), None)
        analysis_run_id = next((step.analysis_run_id for step in reversed(steps) if step.analysis_run_id is not None), None)
        return WorkbenchProjectionRunResult(
            program_id=request.program_id,
            operation=request.operation,
            status=status,
            message=message,
            snapshot_id=snapshot_id,
            analysis_run_id=analysis_run_id,
            steps=steps,
            counts=counts,
            boundary=workbench_projection_control_boundary(),
        )



def _local_component_groups(rows: list[Mapping[str, Any]], *, limit: int) -> list[dict[str, Any]]:
    buckets: dict[tuple[str, str], list[Mapping[str, Any]]] = {}
    for row in rows:
        host = str(row.get("host") or "unknown-host")
        route = _route_family(row.get("route_template") or row.get("path") or "/")
        buckets.setdefault((host, route), []).append(row)
    groups: list[dict[str, Any]] = []
    for (host, route), members in buckets.items():
        node_count = len(members)
        status_kinds = {str(item.get("status_code")) for item in members if item.get("status_code") is not None}
        structural = max(1, min(100, 20 + node_count * 3 + len(status_kinds) * 4))
        coverage = max(1, min(100, 35 + min(node_count, 20) * 2))
        exploration = max(1, min(100, round(structural * 0.65 + coverage * 0.35)))
        examples = [
            _example_label(item)
            for item in sorted(members, key=lambda value: str(value.get("route_template") or value.get("path") or ""))[:6]
        ]
        groups.append({
            "host": host,
            "route_family": route,
            "node_count": node_count,
            "structural_pressure_score": structural,
            "coverage_score": coverage,
            "exploration_priority_score": exploration,
            "examples": examples,
        })
    return sorted(groups, key=lambda item: (-item["exploration_priority_score"], -item["node_count"], item["host"], item["route_family"]))[: max(1, limit)]


def _route_family(path: Any) -> str:
    parts = str(path or "/").split("?")[0].strip("/").split("/")
    first = next((part for part in parts if part), "root")
    return f"/{first}"


def _example_label(row: Mapping[str, Any]) -> str:
    method = str(row.get("method") or "GET")
    path = str(row.get("route_template") or row.get("path") or "/")
    status = row.get("status_code")
    suffix = f" · {status}" if status is not None else ""
    return f"{method} {path}{suffix}"


def _local_component_fingerprint(*, program_id: UUID, snapshot_id: UUID, grouped: list[dict[str, Any]], run_id: UUID) -> str:
    payload = {
        "algorithm": "surface-local-route-family-components-v1",
        "program_id": str(program_id),
        "snapshot_id": str(snapshot_id),
        "run_id": str(run_id),
        "groups": grouped,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def _friendly_projection_error(message: str) -> str:
    cleaned = _redact_runtime_text(str(message or ""))
    if "Name or service not known" in cleaned or "getaddrinfo" in cleaned or "Failed to resolve" in cleaned:
        return "Neo4j is not reachable from the API container. The dashboard used the local Surface Map fallback."
    return cleaned[:600]

def _postgres_dsn(settings: Settings) -> str:
    return (
        f"postgresql://{settings.POSTGRES_USER}:{settings.POSTGRES_PASSWORD}"
        f"@{settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}/{settings.POSTGRES_DB}"
    )


def _json_stdout(completed: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    try:
        parsed = json.loads(completed.stdout or "{}")
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _stderr_or_stdout(completed: subprocess.CompletedProcess[str]) -> str:
    text = completed.stderr.strip() or completed.stdout.strip()
    return _redact_runtime_text(text)[:1200]


def _redact_runtime_text(text: str) -> str:
    if not text:
        return ""
    patterns = [
        (r"postgresql://([^:\s/]+):([^@\s]+)@", r"postgresql://\1:***@"),
        (r"(password|token|api[_-]?key|authorization)\s*[=:]\s*[^\s,;]+", r"\1=***"),
        (r"Bearer\s+[A-Za-z0-9._~+/=-]+", "Bearer ***"),
    ]
    redacted = text
    for pattern, replacement in patterns:
        redacted = re.sub(pattern, replacement, redacted, flags=re.IGNORECASE)
    return redacted


def _uuid_or_none(value: object) -> UUID | None:
    if value in (None, ""):
        return None
    return UUID(str(value))


def _status_message(status: str) -> str:
    if status == "completed":
        return "Workbench projections refreshed."
    if status == "partial":
        return "Workbench projection refresh partially completed; inspect step results."
    return "Workbench projection refresh failed."
