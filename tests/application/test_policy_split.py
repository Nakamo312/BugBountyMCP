from uuid import uuid4

from api.application.action_catalog import CatalogDetail
from api.application.contracts import (
    ActionKind,
    ActionRequest,
    PolicyDecisionStatus,
    SafetyLevel,
)
from api.application.services.policy import (
    ApprovalPolicy,
    CapabilityPolicy,
    PolicyService,
    RiskPolicy,
    ScopePolicyService,
)
from api.domain.enums import RuleType, ScopeAction
from api.domain.models import ScopeRuleModel


def _request(capability: str, profile: str, targets: list[str], options: dict | None = None):
    return ActionRequest(
        kind=ActionKind.SCAN,
        program_id=uuid4(),
        catalog_id=uuid4(),
        targets=targets,
        options=options or {},
    ).bind_profile(capability_id=capability, profile_id=profile)


def _detail(
    capability: str,
    profile: str,
    *,
    allowed_options: list[str] | None = None,
    safety_level: str = "safe_active",
    requires_approval: bool = False,
    scope_policy: str = "confidence",
) -> CatalogDetail:
    return CatalogDetail(
        id=uuid4(),
        snapshot_id=uuid4(),
        capability=capability,
        profile=profile,
        capability_label=capability,
        profile_label=profile,
        safety_level=safety_level,
        requires_approval=requires_approval,
        mode="routed",
        queue="analysis",
        request_event=f"{capability}_scan_requested",
        default_profile=profile,
        scope_policy=scope_policy,
        allowed_options=allowed_options or ["timeout"],
    )


def test_policy_service_is_composed_from_separate_policy_steps() -> None:
    service = PolicyService()

    assert isinstance(service.capability_policy, CapabilityPolicy)
    assert isinstance(service.scope_policy, ScopePolicyService)
    assert isinstance(service.risk_policy, RiskPolicy)
    assert isinstance(service.approval_policy, ApprovalPolicy)


def test_policy_service_uses_active_catalog_detail_not_yaml_registry() -> None:
    request = _request(
        "invented-tool",
        "safe-run",
        ["https://example.com"],
        {"depth": 2},
    )
    detail = _detail(
        "invented-tool",
        "safe-run",
        allowed_options=["depth"],
        safety_level="passive",
        scope_policy="none",
    )

    decision = PolicyService().evaluate(request, detail)

    assert decision.status == PolicyDecisionStatus.ALLOWED
    assert decision.safety_level is SafetyLevel.PASSIVE
    assert decision.metadata["capability_id"] == "invented-tool"
    assert decision.metadata["profile_id"] == "safe-run"


def test_capability_policy_blocks_unknown_options_before_scope_or_approval() -> None:
    request = _request(
        "httpx",
        "safe-web-probe",
        ["https://example.com"],
        {"timeout": 10, "shell": "echo nope"},
    )
    decision = PolicyService().evaluate(
        request,
        _detail("httpx", "safe-web-probe", allowed_options=["timeout"]),
    )

    assert decision.status == PolicyDecisionStatus.BLOCKED
    assert any("Forbidden command-like options" in reason for reason in decision.reasons)
    assert decision.blocked_targets == ["https://example.com"]


def test_policy_records_safety_level_from_profile() -> None:
    request = _request("httpx", "safe-web-probe", ["https://example.com"], {"timeout": 10})

    decision = PolicyService().evaluate(
        request,
        _detail("httpx", "safe-web-probe", safety_level="safe_active"),
    )

    assert decision.status == PolicyDecisionStatus.ALLOWED
    assert decision.safety_level is SafetyLevel.SAFE_ACTIVE
    assert decision.allowed_targets == ["https://example.com"]


def test_profile_approval_is_a_separate_policy_decision() -> None:
    request = _request("ffuf", "content-discovery-light", ["https://example.com"], {"timeout": 10})

    decision = PolicyService().evaluate(
        request,
        _detail(
            "ffuf",
            "content-discovery-light",
            safety_level="active",
            requires_approval=True,
            scope_policy="strict",
        ),
    )

    assert decision.status == PolicyDecisionStatus.REQUIRES_APPROVAL
    assert decision.safety_level is SafetyLevel.ACTIVE
    assert any("requires human approval" in reason for reason in decision.reasons)


def test_scope_policy_can_filter_strict_targets_when_rules_are_supplied() -> None:
    program_id = uuid4()
    request = _request(
        "ffuf",
        "content-discovery-light",
        ["https://api.example.com", "https://evil.test"],
        {"timeout": 10},
    )
    request = request.model_copy(update={"program_id": program_id})
    scope_rules = [
        ScopeRuleModel(
            program_id=program_id,
            action=ScopeAction.INCLUDE,
            rule_type=RuleType.DOMAIN,
            pattern="*.example.com",
        )
    ]

    decision = PolicyService().evaluate(
        request,
        _detail(
            "ffuf",
            "content-discovery-light",
            safety_level="active",
            requires_approval=True,
            scope_policy="strict",
        ),
        scope_rules=scope_rules,
    )

    assert decision.status == PolicyDecisionStatus.REQUIRES_APPROVAL
    assert decision.allowed_targets == ["https://api.example.com"]
    assert decision.blocked_targets == ["https://evil.test"]


def test_scope_policy_blocks_strict_action_when_no_target_matches() -> None:
    program_id = uuid4()
    request = _request(
        "ffuf",
        "content-discovery-light",
        ["https://evil.test"],
        {"timeout": 10},
    )
    request = request.model_copy(update={"program_id": program_id})
    scope_rules = [
        ScopeRuleModel(
            program_id=program_id,
            action=ScopeAction.INCLUDE,
            rule_type=RuleType.DOMAIN,
            pattern="*.example.com",
        )
    ]

    decision = PolicyService().evaluate(
        request,
        _detail(
            "ffuf",
            "content-discovery-light",
            safety_level="active",
            requires_approval=True,
            scope_policy="strict",
        ),
        scope_rules=scope_rules,
    )

    assert decision.status == PolicyDecisionStatus.BLOCKED
    assert decision.allowed_targets == []
    assert decision.blocked_targets == ["https://evil.test"]
    assert any("strict scope" in reason for reason in decision.reasons)
