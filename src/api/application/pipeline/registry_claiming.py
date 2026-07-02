"""Event claim helpers for :mod:`api.application.pipeline.registry`."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any, Dict

from api.application.action_invocation_payload import action_invocation_mapping
from uuid import UUID

from api.application.contracts import ExecutionMode, NodeRunClaimRequest
from api.application.pipeline.fingerprints import (
    build_node_claim_key,
    build_node_input_fingerprint,
    build_node_work_key,
    build_target_fingerprint,
)
from api.application.pipeline.node import Node

logger = logging.getLogger(__name__)


class NodeRegistryClaimingMixin:
    async def _claim_event_for_node(
        self,
        node_id: str,
        event_name: str,
        event: Dict[str, Any],
    ) -> Dict[str, Any] | None:
        node = self._nodes[node_id]
        if self._uses_preallocated_action_run(node, event):
            return dict(event)

        store = await self._get_node_run_claims()
        if store is None:
            return dict(event)

        trigger_event_id = UUID(str(event["event_id"]))
        claim_events = self._claim_events_for_node(node, event)
        last_claim = None
        for claim_event in claim_events:
            input_fingerprint = build_node_input_fingerprint(node_id, claim_event)
            target_fingerprint = build_target_fingerprint(claim_event.get("targets", []))
            claim_key = build_node_claim_key(
                trigger_event_id=trigger_event_id,
                node_id=node_id,
                input_fingerprint=input_fingerprint,
            )
            request = NodeRunClaimRequest(
                claim_key=claim_key,
                job_id=UUID(str(event["job_id"])),
                program_id=UUID(str(event["program_id"])),
                node_id=node_id,
                event_name=event_name,
                trigger_event_id=trigger_event_id,
                input_fingerprint=input_fingerprint,
                target_fingerprint=target_fingerprint,
                execution_mode=node.execution_mode,
                next_run_at=self._scheduled_next_run_at(node_id),
                target_count=self._target_count(claim_event),
                run_payload=self._run_payload_for_event(claim_event),
                work_key=self._work_key_for_event(node, event_name, claim_event),
                coalesced_trigger=(
                    self._coalesced_trigger_for_event(claim_event)
                    if node.execution_mode == ExecutionMode.SCHEDULED
                    else None
                ),
                retry_policy=(
                    dict(node.retry_policy)
                    if node.execution_mode == ExecutionMode.SCHEDULED
                    else None
                ),
                campaign_id=(
                    UUID(str(claim_event["campaign_id"]))
                    if claim_event.get("campaign_id")
                    else None
                ),
                expansion_depth=int(claim_event.get("expansion_depth", 0) or 0),
                max_expansion_depth=node.max_expansion_depth,
                cooldown_seconds=node.cooldown_seconds,
                token_cost=node.token_cost,
            )
            last_claim = await store.claim_node_run(request)
            if last_claim.is_blocked:
                logger.warning(
                    "Scheduled node run blocked: node=%s event=%s reason=%s",
                    node_id,
                    event_name,
                    last_claim.blocked_reason,
                )
            if last_claim.is_terminal and node.execution_mode != ExecutionMode.SCHEDULED:
                return None

        if node.execution_mode == ExecutionMode.SCHEDULED:
            return None

        if last_claim is None or last_claim.is_terminal:
            return None

        claimed_event = dict(claim_events[0])
        claimed_event["run_id"] = str(last_claim.run_id)
        return claimed_event

    @staticmethod
    def _uses_preallocated_action_run(node: Node, event: Dict[str, Any]) -> bool:
        """Use the already-created action run for initial ActionService events.

        ActionService records a job/run/event-store row before the event is
        published. The registry must execute that run instead of creating a
        second claimed run; otherwise the dashboard follows the preallocated
        run forever while the worker state is written elsewhere.

        The event path has two currently-supported shapes:

        * canonical envelope payload: ``payload.action_invocation``;
        * legacy RabbitMQ dict: top-level ``action_invocation`` after
          ``EventEnvelope.to_legacy_dict()`` flattens payload values.

        The previous check accepted only the first shape. When the dispatcher
        replayed a flattened stored event, the registry treated the action as a
        normal trigger, claimed a second run, and left the dashboard-visible
        preallocated run stuck in ``queued`` forever.
        """
        if node.execution_mode != ExecutionMode.INLINE:
            return False
        if not event.get("run_id") or not event.get("job_id"):
            return False

        invocation = NodeRegistryClaimingMixin._action_invocation_for_event(event)
        return bool(
            invocation.get("action_id")
            and invocation.get("capability_id")
            and invocation.get("profile_id")
        )

    @staticmethod
    def _action_invocation_for_event(event: Mapping[str, Any]) -> Mapping[str, Any]:
        payload = event.get("payload")
        if isinstance(payload, Mapping):
            invocation = action_invocation_mapping(payload)
            if invocation:
                return invocation

        flattened = event.get("action_invocation")
        if isinstance(flattened, Mapping):
            return flattened

        if all(event.get(key) for key in ("action_id", "capability_id", "profile_id")):
            return event

        return {}

    def _claim_events_for_node(self, node: Node, event: Dict[str, Any]) -> list[Dict[str, Any]]:
        if node.execution_mode != ExecutionMode.SCHEDULED:
            return [dict(event)]

        max_targets = node.max_targets_per_run
        targets = list(event.get("targets") or [])
        if max_targets is None or max_targets <= 0 or len(targets) <= max_targets:
            return [dict(event)]

        chunks = []
        for offset in range(0, len(targets), max_targets):
            chunk_targets = targets[offset : offset + max_targets]
            chunk_event = dict(event)
            chunk_event["targets"] = chunk_targets
            if chunk_targets:
                chunk_event["target"] = chunk_targets[0]
            chunks.append(chunk_event)
        max_fanout = node.max_fanout_per_event
        if max_fanout is not None and len(chunks) > max_fanout:
            logger.warning(
                "Scheduled fanout limited: node=%s requested=%s allowed=%s",
                node.node_id,
                len(chunks),
                max_fanout,
            )
            return chunks[:max_fanout]
        return chunks

    @staticmethod
    def _target_count(event: Dict[str, Any]) -> int | None:
        targets = event.get("targets")
        if isinstance(targets, list):
            return len(targets)
        return None

    @staticmethod
    def _run_payload_for_event(event: Dict[str, Any]) -> Dict[str, Any]:
        return {
            key: value
            for key, value in event.items()
            if key not in {"event_id", "created_at"}
        }

    def _work_key_for_event(
        self,
        node: Node,
        event_name: str,
        event: Dict[str, Any],
    ) -> str | None:
        if node.execution_mode != ExecutionMode.SCHEDULED:
            return None
        return build_node_work_key(
            program_id=event["program_id"],
            campaign_id=event.get("campaign_id"),
            node_id=node.node_id,
            event_name=event_name,
            targets=event.get("targets", []),
            profile=event.get("profile"),
            options=event.get("options") or event.get("payload") or {},
            scan_mode=event.get("scan_mode") or event.get("mode"),
            node_work_identity=self._node_work_identity(node),
        )

    @staticmethod
    def _coalesced_trigger_for_event(event: Dict[str, Any]) -> Dict[str, Any] | None:
        if not event.get("event_id"):
            return None
        metadata = {
            "trigger_event_id": str(event["event_id"]),
            "job_id": str(event["job_id"]) if event.get("job_id") else None,
            "run_id": str(event["run_id"]) if event.get("run_id") else None,
            "correlation_id": (
                str(event["correlation_id"]) if event.get("correlation_id") else None
            ),
            "reason": "scheduled_active_exact_dedup",
        }
        return {key: value for key, value in metadata.items() if value is not None}

    @staticmethod
    def _node_work_identity(node: Node) -> Dict[str, Any]:
        def component_name(value) -> str | None:
            if value is None:
                return None
            return getattr(value, "__name__", str(value))

        identity = {
            "node_class": type(node).__name__,
            "runner": component_name(
                getattr(node, "runner_type", None) or getattr(node, "runner_key", None)
            ),
            "parser": component_name(
                getattr(node, "parser_type", None) or getattr(node, "parser_key", None)
            ),
            "processor": component_name(
                getattr(node, "processor_type", None) or getattr(node, "processor_key", None)
            ),
            "ingestor": component_name(
                getattr(node, "ingestor_type", None)
                or getattr(node, "ingestor_key", None)
                or getattr(node, "host_ingestor_key", None)
            ),
            "target_extractor": component_name(getattr(node, "target_extractor", None)),
            "scope_policy": str(getattr(node, "scope_policy", "")),
            "max_targets_per_run": node.max_targets_per_run,
            "cooldown_seconds": node.cooldown_seconds,
            "max_fanout_per_event": node.max_fanout_per_event,
            "max_expansion_depth": node.max_expansion_depth,
            "token_cost": node.token_cost,
            "event_out": sorted(
                event.value if hasattr(event, "value") else str(event)
                for event in node.event_out
            ),
        }
        return {key: value for key, value in identity.items() if value not in (None, "")}

