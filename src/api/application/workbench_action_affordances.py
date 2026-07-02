"""Workbench action affordances derived from catalog target contracts.

This module is the boundary between graph browsing and action submission. It
never lets the frontend decide which tool applies to which node. The frontend
selects a graph entity; backend code converts it into a normalized target and
matches it against the active catalog contracts materialized from the pipeline
manifest.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from api.application.action_catalog import CatalogDetail, CatalogItemNotFound, CatalogNotReady
from api.application.contracts import ActionRequest, ActionSubmission
from api.application.services.action import ActionService
from api.application.services.action_catalog import ActionCatalogService
from api.application.workbench import (
    WorkbenchActionAffordance,
    WorkbenchActionAffordanceList,
    WorkbenchEntityProfile,
    WorkbenchNotFound,
    WorkbenchReadService,
)


class WorkbenchActionEntity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str | None = None
    label: str | None = None
    entity_key: str | None = None
    properties: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class WorkbenchAvailableActionsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    program_id: UUID
    entity_key: str | None = None
    entity: WorkbenchActionEntity | None = None
    context: dict[str, Any] = Field(default_factory=dict)
    include_rejected: bool = True
    limit: int = Field(default=20, ge=1, le=100)


class WorkbenchSubmitActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    program_id: UUID
    entity_key: str
    catalog_id: UUID
    targets: list[str] | None = None
    options: dict[str, Any] = Field(default_factory=dict)
    requested_by: str = "workbench"
    context: dict[str, Any] = Field(default_factory=dict)


class WorkbenchSubmitActionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    program_id: UUID
    entity_key: str
    action: WorkbenchActionAffordance
    submission: ActionSubmission
    boundary: dict[str, Any] = Field(default_factory=dict)


class NormalizedActionTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entity_key: str
    display: str
    labels: list[str] = Field(default_factory=list)
    node_type: str | None = None
    source: str | None = None
    properties: dict[str, Any] = Field(default_factory=dict)
    values: dict[str, str] = Field(default_factory=dict)


class MatchedTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_value: str
    reason: str
    contract: dict[str, Any] = Field(default_factory=dict)


class ActionAffordanceUnavailable(ValueError):
    """Raised when a submitted action is not available for the selected entity."""


class WorkbenchActionAffordanceService:
    """Compute and submit Workbench actions through the existing action lifecycle."""

    def __init__(
        self,
        *,
        workbench: WorkbenchReadService,
        catalog: ActionCatalogService,
        actions: ActionService,
    ) -> None:
        self._workbench = workbench
        self._catalog = catalog
        self._actions = actions

    async def available(self, request: WorkbenchAvailableActionsRequest) -> WorkbenchActionAffordanceList:
        target = await self._target_from_request(request)
        details = await self._catalog_details()
        enabled: list[WorkbenchActionAffordance] = []
        rejected: list[WorkbenchActionAffordance] = []

        for detail in details:
            affordance = _affordance_for_catalog_detail(detail, target)
            if affordance.enabled:
                enabled.append(affordance)
            elif request.include_rejected and _has_workbench_target_contracts(detail):
                rejected.append(affordance)

        ranked = sorted(enabled, key=_affordance_sort_key)[: request.limit]
        rejected = sorted(rejected, key=lambda item: (item.tool or item.catalog_id, item.profile))[: request.limit]
        return WorkbenchActionAffordanceList(
            program_id=request.program_id,
            entity_key=target.entity_key,
            target={
                "label": target.labels[0] if target.labels else target.node_type,
                "display": target.display,
                "source": target.source,
                "values": target.values,
            },
            actions=ranked,
            rejected=rejected,
            boundary={
                "surface": "workbench_action_affordances",
                "raw_frontend_tool_rules": "forbidden",
                "matching_source": "active_action_catalog.frontend.workbench.target_contracts",
                "tool_execution": "forbidden",
                "action_submission": "available_via_submit_endpoint",
            },
        )

    async def submit(self, request: WorkbenchSubmitActionRequest) -> WorkbenchSubmitActionResponse:
        available = await self.available(
            WorkbenchAvailableActionsRequest(
                program_id=request.program_id,
                entity_key=request.entity_key,
                context=request.context,
                include_rejected=False,
                limit=100,
            )
        )
        selected = next((item for item in available.actions if item.catalog_id == str(request.catalog_id)), None)
        if selected is None or not selected.enabled:
            raise ActionAffordanceUnavailable(
                "Selected catalog action is not available for this Workbench entity"
            )

        targets = request.targets or list(selected.inputs.get("targets") or [])
        if not targets:
            raise ActionAffordanceUnavailable("Selected Workbench action has no normalized target")
        options = {**selected.prefilled_options, **request.options}
        submission = await self._actions.request_action(
            ActionRequest(
                program_id=request.program_id,
                catalog_id=request.catalog_id,
                targets=targets,
                options=options,
                requested_by=request.requested_by,
                metadata={
                    "source": "workbench",
                    "entity_key": request.entity_key,
                    "target_display": available.target.get("display"),
                    "context": request.context,
                },
            )
        )
        return WorkbenchSubmitActionResponse(
            program_id=request.program_id,
            entity_key=request.entity_key,
            action=selected,
            submission=submission,
            boundary={
                "surface": "workbench_action_submit",
                "raw_frontend_tool_rules": "forbidden",
                "tool_execution": "deferred_to_action_lifecycle",
                "policy_check": "ActionService",
                "approval": "ActionService",
            },
        )

    async def _target_from_request(self, request: WorkbenchAvailableActionsRequest) -> NormalizedActionTarget:
        entity_key = request.entity_key or (request.entity.entity_key if request.entity is not None else None)
        if not entity_key:
            raise WorkbenchNotFound("Workbench action target requires entity_key")
        profile: WorkbenchEntityProfile | None = None
        try:
            profile = await self._workbench.entity_profile(program_id=request.program_id, entity_key=entity_key)
        except WorkbenchNotFound:
            if request.entity is None:
                raise
        return _normalized_target(entity_key=entity_key, entity=request.entity, profile=profile)

    async def _catalog_details(self) -> list[CatalogDetail]:
        items = await self._catalog.list_items()
        details: list[CatalogDetail] = []
        for item in items:
            try:
                details.append(await self._catalog.get_detail(item.id))
            except (CatalogItemNotFound, CatalogNotReady):
                raise
        return details


def _normalized_target(
    *,
    entity_key: str,
    entity: WorkbenchActionEntity | None,
    profile: WorkbenchEntityProfile | None,
) -> NormalizedActionTarget:
    profile_payload = profile.profile if profile is not None else {}
    properties = {
        **(entity.properties if entity is not None else {}),
        **(profile.properties if profile is not None else {}),
    }
    labels = _normalized_labels(entity_key=entity_key, entity=entity, profile=profile_payload, properties=properties)
    node_type = _text(profile_payload.get("node_type") or profile_payload.get("type") or (entity.label if entity else None))
    display = _display_value(entity=entity, profile=profile_payload, properties=properties, fallback=entity_key)
    values = _target_values(labels=labels, node_type=node_type, properties=properties, display=display)
    return NormalizedActionTarget(
        entity_key=entity_key,
        display=display,
        labels=labels,
        node_type=node_type,
        source=_text((entity.source if entity else None) or profile_payload.get("projection_source")),
        properties={str(key): value for key, value in properties.items()},
        values=values,
    )


def _normalized_labels(
    *,
    entity_key: str,
    entity: WorkbenchActionEntity | None,
    profile: Mapping[str, Any],
    properties: Mapping[str, Any],
) -> list[str]:
    raw_values: list[Any] = []
    raw_values.extend(profile.get("labels") or []) if isinstance(profile.get("labels"), list) else None
    raw_values.extend(properties.get("labels") or []) if isinstance(properties.get("labels"), list) else None
    raw_values.append(profile.get("type"))
    raw_values.append(profile.get("node_type"))
    raw_values.append(entity.label if entity else None)
    if entity_key.startswith("neo4j:"):
        parts = entity_key.split(":", 2)
        if len(parts) >= 2:
            raw_values.append(parts[1])
    if entity_key.startswith("surface:"):
        parts = entity_key.split(":", 2)
        if len(parts) >= 2:
            raw_values.append(parts[1])
    labels = []
    seen = set()
    for raw in raw_values:
        value = _canonical_label(raw)
        if not value or value in seen:
            continue
        seen.add(value)
        labels.append(value)
    return labels


def _canonical_label(value: Any) -> str | None:
    text = _text(value)
    if not text:
        return None
    aliases = {
        "host": "Host",
        "neo4j_host": "Host",
        "domain": "Host",
        "scope": "Scope",
        "ip": "IP",
        "neo4j_ip": "IP",
        "cidr": "CIDR",
        "neo4j_cidr": "CIDR",
        "asn": "ASN",
        "neo4j_asn": "ASN",
        "service": "Service",
        "endpoint": "Endpoint",
        "route_template": "Endpoint",
        "jsfile": "JSFile",
        "js_file": "JSFile",
        "neo4j_js_file": "JSFile",
        "surfacenode": "SurfaceNode",
        "surface_node": "SurfaceNode",
        "surface_component": "SurfaceComponent",
    }
    key = text.replace("-", "_").replace(" ", "_").lower()
    return aliases.get(key, text[:1].upper() + text[1:])


def _target_values(*, labels: list[str], node_type: str | None, properties: Mapping[str, Any], display: str) -> dict[str, str]:
    values = {
        "identity": _first_text(properties, "identity_key", "node_fingerprint", "feature_fingerprint") or display,
        "hostname": _first_text(properties, "hostname", "host", "domain", "name"),
        "address": _first_text(properties, "address", "ip", "ip_address"),
        "cidr": _first_text(properties, "cidr", "cidr_block", "network"),
        "asn": _first_text(properties, "asn", "asn_number", "number"),
        "url": _first_text(properties, "url", "normalized_url"),
        "base_url": _first_text(properties, "base_url", "origin"),
        "path": _first_text(properties, "route_template", "normalized_path", "path"),
        "port": _first_text(properties, "port"),
        "method": _first_text(properties, "method"),
        "js_url": _first_text(properties, "js_url", "url", "source_url"),
    }
    if not values["address"] and "IP" in labels:
        values["address"] = _hostlike(display)
    if not values["hostname"] and any(label in labels for label in ("Host", "Scope")):
        values["hostname"] = _hostlike(display)
    if not values["cidr"] and "CIDR" in labels:
        values["cidr"] = _hostlike(display)
    if not values["asn"] and "ASN" in labels:
        values["asn"] = _hostlike(display)
    if not values["url"]:
        values["url"] = _compose_url(values)
    if not values["base_url"]:
        values["base_url"] = _compose_base_url(values)
    if not values["js_url"] and "JSFile" in labels:
        values["js_url"] = values.get("url")
    return {key: value for key, value in values.items() if value}


def _compose_url(values: Mapping[str, str | None]) -> str | None:
    host = values.get("hostname") or values.get("address")
    path = values.get("path")
    if not host:
        return None
    if str(host).startswith(("http://", "https://")):
        base = str(host).rstrip("/")
    else:
        base = f"https://{host}"
    if path:
        suffix = str(path) if str(path).startswith("/") else f"/{path}"
        return f"{base}{suffix}"
    return base


def _compose_base_url(values: Mapping[str, str | None]) -> str | None:
    host = values.get("hostname") or values.get("address")
    if not host:
        return None
    if str(host).startswith(("http://", "https://")):
        return str(host).rstrip("/")
    port = values.get("port")
    if port:
        return f"https://{host}:{port}"
    return f"https://{host}"


def _affordance_for_catalog_detail(detail: CatalogDetail, target: NormalizedActionTarget) -> WorkbenchActionAffordance:
    match = _match_detail(detail, target)
    enabled = match is not None
    target_value = match.target_value if match is not None else None
    disabled_reasons = [] if enabled else [_not_applicable_reason(detail, target)]
    options = _default_options(detail)
    return WorkbenchActionAffordance(
        catalog_id=str(detail.id),
        label=f"{detail.capability_label} / {detail.profile_label}",
        profile=detail.profile,
        required_inputs=[_input_contract(match.contract if match else {})],
        prefilled_options=options,
        enabled=enabled,
        disabled_reasons=disabled_reasons,
        tool=detail.capability,
        state="available" if enabled else "not_applicable",
        approval_required=detail.requires_approval,
        risk_class=detail.safety_level,
        reason=match.reason if match is not None else disabled_reasons[0],
        inputs={"targets": [target_value], "target": target_value} if target_value else {},
        submit_payload={
            "catalog_id": str(detail.id),
            "targets": [target_value] if target_value else [],
            "options": options,
            "requested_by": "workbench",
        },
        policy_preview={
            "scope_policy": detail.scope_policy,
            "requires_approval": detail.requires_approval,
            "safety_level": detail.safety_level,
            "queue": detail.queue,
            "request_event": detail.request_event,
        },
        budget_preview=detail.execution_budget.model_dump(mode="json"),
        expected_delta=_expected_delta(detail),
        prior_outcomes=[],
    )


def _match_detail(detail: CatalogDetail, target: NormalizedActionTarget) -> MatchedTarget | None:
    for contract in _target_contracts(detail):
        if not _labels_match(contract, target):
            continue
        target_property = str(contract.get("target_property") or "identity")
        required = [str(item) for item in contract.get("required_properties") or []]
        required_any = [str(item) for item in contract.get("required_any_properties") or []]
        if required and not all(name in target.values for name in required):
            continue
        if required_any and not any(name in target.values for name in required_any):
            continue
        target_value = target.values.get(target_property)
        if not target_value and required_any:
            target_value = next((target.values[name] for name in required_any if name in target.values), None)
        if not target_value:
            continue
        return MatchedTarget(
            target_value=target_value,
            reason=str(contract.get("reason") or "Catalog target contract matches this graph entity."),
            contract=dict(contract),
        )
    return None


def _target_contracts(detail: CatalogDetail) -> list[dict[str, Any]]:
    frontend = detail.frontend or {}
    workbench = frontend.get("workbench") if isinstance(frontend, Mapping) else None
    contracts = workbench.get("target_contracts") if isinstance(workbench, Mapping) else None
    if not isinstance(contracts, list):
        return []
    return [dict(item) for item in contracts if isinstance(item, Mapping)]


def _has_workbench_target_contracts(detail: CatalogDetail) -> bool:
    return bool(_target_contracts(detail))


def _labels_match(contract: Mapping[str, Any], target: NormalizedActionTarget) -> bool:
    contract_labels = {_canonical_label(label) for label in contract.get("labels") or []}
    contract_labels.discard(None)
    if not contract_labels:
        return True
    target_labels = {_canonical_label(label) for label in target.labels}
    return bool(contract_labels & target_labels)


def _input_contract(contract: Mapping[str, Any]) -> dict[str, Any]:
    if not contract:
        return {}
    return {
        "kind": contract.get("kind"),
        "labels": list(contract.get("labels") or []),
        "target_property": contract.get("target_property"),
        "required_properties": list(contract.get("required_properties") or []),
        "required_any_properties": list(contract.get("required_any_properties") or []),
    }


def _not_applicable_reason(detail: CatalogDetail, target: NormalizedActionTarget) -> str:
    labels = ", ".join(target.labels) or target.node_type or "unknown"
    return f"No {detail.capability}/{detail.profile} target contract matched labels/properties: {labels}."


def _default_options(detail: CatalogDetail) -> dict[str, Any]:
    options: dict[str, Any] = {}
    for name, spec in detail.option_schema.items():
        if spec.default is not None:
            options[name] = spec.default
    return options


def _expected_delta(detail: CatalogDetail) -> list[dict[str, Any]]:
    produced = []
    frontend = detail.frontend or {}
    workbench = frontend.get("workbench") if isinstance(frontend, Mapping) else None
    if isinstance(workbench, Mapping) and isinstance(workbench.get("produces"), list):
        produced = [str(item) for item in workbench["produces"]]
    return [{"kind": "catalog_declared_outputs", "produces": produced}] if produced else []


def _affordance_sort_key(item: WorkbenchActionAffordance) -> tuple[int, int, str]:
    safety_rank = {"passive": 0, "safe_active": 1, "active": 2, "sensitive": 3}.get(item.risk_class or "", 9)
    approval_rank = 1 if item.approval_required else 0
    return (safety_rank, approval_rank, item.tool or item.catalog_id)


def _display_value(
    *,
    entity: WorkbenchActionEntity | None,
    profile: Mapping[str, Any],
    properties: Mapping[str, Any],
    fallback: str,
) -> str:
    values = [
        entity.label if entity else None,
        profile.get("label"),
        properties.get("url"),
        properties.get("hostname"),
        properties.get("host"),
        properties.get("address"),
        properties.get("cidr"),
        properties.get("identity_key"),
    ]
    return next((_text(value) for value in values if _text(value)), fallback)


def _first_text(values: Mapping[str, Any], *keys: str) -> str | None:
    for key in keys:
        text = _text(values.get(key))
        if text:
            return text
    return None


def _hostlike(value: Any) -> str | None:
    text = _text(value)
    if not text:
        return None
    text = text.removeprefix("http://").removeprefix("https://")
    text = text.split("/", 1)[0]
    return text or None


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
