from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
import sys
from collections.abc import Mapping
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from api.application.workbench_projection_control import (
    WorkbenchProjectionOperation,
    WorkbenchProjectionRunRequest,
    WorkbenchProjectionRunResult,
    WorkbenchProjectionStepResult,
    workbench_projection_control_boundary,
)
from api.config import Settings
from api.infrastructure.adapters.orm_tables.surface_map import surface_snapshots


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
