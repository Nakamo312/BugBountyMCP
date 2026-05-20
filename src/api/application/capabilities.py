"""Declarative capability registry for scans, profiles, and future MCP tools."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from api.application.contracts import SafetyLevel
from api.application.pipeline.scope_policy import ScopePolicy


@dataclass(frozen=True)
class ProfileSpec:
    id: str
    label: str
    safety_level: SafetyLevel
    allowed_options: frozenset[str] = frozenset()
    requires_approval: bool = False


@dataclass(frozen=True)
class CapabilitySpec:
    id: str
    label: str
    request_event: str
    queue: str
    default_profile: str
    profiles: tuple[ProfileSpec, ...]
    scope_policy: ScopePolicy
    frontend: dict[str, Any] = field(default_factory=dict)

    @property
    def profile_ids(self) -> set[str]:
        return {profile.id for profile in self.profiles}


CAPABILITIES: tuple[CapabilitySpec, ...] = (
    CapabilitySpec(
        id="subfinder",
        label="Subfinder",
        request_event="subfinder_scan_requested",
        queue="discovery",
        default_profile="passive-recon",
        scope_policy=ScopePolicy.NONE,
        profiles=(
            ProfileSpec(
                id="passive-recon",
                label="Passive subdomain discovery",
                safety_level=SafetyLevel.PASSIVE,
                allowed_options=frozenset({"timeout", "probe"}),
            ),
        ),
    ),
    CapabilitySpec(
        id="httpx",
        label="HTTPX",
        request_event="httpx_scan_requested",
        queue="analysis",
        default_profile="safe-web-probe",
        scope_policy=ScopePolicy.CONFIDENCE,
        profiles=(
            ProfileSpec(
                id="safe-web-probe",
                label="Safe HTTP probing",
                safety_level=SafetyLevel.SAFE_ACTIVE,
                allowed_options=frozenset({"timeout"}),
            ),
        ),
    ),
    CapabilitySpec(
        id="katana",
        label="Katana",
        request_event="katana_scan_requested",
        queue="analysis",
        default_profile="safe-crawl",
        scope_policy=ScopePolicy.CONFIDENCE,
        profiles=(
            ProfileSpec(
                id="safe-crawl",
                label="Safe crawl",
                safety_level=SafetyLevel.SAFE_ACTIVE,
                allowed_options=frozenset({"depth", "js_crawl", "headless", "timeout"}),
            ),
        ),
    ),
    CapabilitySpec(
        id="playwright",
        label="Playwright",
        request_event="playwright_scan_requested",
        queue="analysis",
        default_profile="browser-crawl",
        scope_policy=ScopePolicy.STRICT,
        profiles=(
            ProfileSpec(
                id="browser-crawl",
                label="Browser crawl with network capture",
                safety_level=SafetyLevel.ACTIVE,
                allowed_options=frozenset({"depth", "timeout"}),
                requires_approval=True,
            ),
        ),
    ),
    CapabilitySpec(
        id="gau",
        label="GAU/Waymore",
        request_event="gau_scan_requested",
        queue="analysis",
        default_profile="archive-url-discovery",
        scope_policy=ScopePolicy.STRICT,
        profiles=(
            ProfileSpec(
                id="archive-url-discovery",
                label="Archived URL discovery",
                safety_level=SafetyLevel.PASSIVE,
                allowed_options=frozenset({"include_subs", "timeout"}),
            ),
        ),
    ),
    CapabilitySpec(
        id="linkfinder",
        label="LinkFinder",
        request_event="linkfinder_scan_requested",
        queue="analysis",
        default_profile="js-endpoint-extraction",
        scope_policy=ScopePolicy.CONFIDENCE,
        profiles=(
            ProfileSpec(
                id="js-endpoint-extraction",
                label="JavaScript endpoint extraction",
                safety_level=SafetyLevel.SAFE_ACTIVE,
                allowed_options=frozenset({"timeout"}),
            ),
        ),
    ),
    CapabilitySpec(
        id="ffuf",
        label="FFUF",
        request_event="ffuf_scan_requested",
        queue="analysis",
        default_profile="content-discovery-light",
        scope_policy=ScopePolicy.STRICT,
        profiles=(
            ProfileSpec(
                id="content-discovery-light",
                label="Light content discovery",
                safety_level=SafetyLevel.ACTIVE,
                allowed_options=frozenset({"timeout"}),
                requires_approval=True,
            ),
        ),
    ),
    CapabilitySpec(
        id="amass",
        label="Amass",
        request_event="amass_scan_requested",
        queue="discovery",
        default_profile="passive-enum",
        scope_policy=ScopePolicy.NONE,
        profiles=(
            ProfileSpec(
                id="passive-enum",
                label="Passive infrastructure enumeration",
                safety_level=SafetyLevel.PASSIVE,
                allowed_options=frozenset({"active", "timeout"}),
            ),
            ProfileSpec(
                id="active-enum",
                label="Active infrastructure enumeration",
                safety_level=SafetyLevel.ACTIVE,
                allowed_options=frozenset({"active", "timeout"}),
                requires_approval=True,
            ),
        ),
    ),
    CapabilitySpec(
        id="dnsx",
        label="DNSx",
        request_event="dnsx_scan_requested",
        queue="validation",
        default_profile="dns-validate",
        scope_policy=ScopePolicy.NONE,
        profiles=(
            ProfileSpec(
                id="dns-validate",
                label="DNS validation",
                safety_level=SafetyLevel.SAFE_ACTIVE,
                allowed_options=frozenset({"mode", "timeout"}),
            ),
        ),
    ),
    CapabilitySpec(
        id="dnsx-ptr",
        label="DNSx PTR",
        request_event="dnsx_ptr_scan_requested",
        queue="validation",
        default_profile="reverse-dns",
        scope_policy=ScopePolicy.NONE,
        profiles=(
            ProfileSpec(
                id="reverse-dns",
                label="Reverse DNS lookup",
                safety_level=SafetyLevel.SAFE_ACTIVE,
                allowed_options=frozenset({"mode", "timeout"}),
            ),
        ),
    ),
    CapabilitySpec(
        id="subjack",
        label="Subjack",
        request_event="subjack_scan_requested",
        queue="analysis",
        default_profile="takeover-check",
        scope_policy=ScopePolicy.CONFIDENCE,
        profiles=(
            ProfileSpec(
                id="takeover-check",
                label="Subdomain takeover check",
                safety_level=SafetyLevel.SAFE_ACTIVE,
                allowed_options=frozenset({"timeout"}),
            ),
        ),
    ),
    CapabilitySpec(
        id="asnmap",
        label="ASNMap",
        request_event="asnmap_scan_requested",
        queue="discovery",
        default_profile="asn-discovery",
        scope_policy=ScopePolicy.NONE,
        profiles=(
            ProfileSpec(
                id="asn-discovery",
                label="ASN and CIDR discovery",
                safety_level=SafetyLevel.PASSIVE,
                allowed_options=frozenset({"mode", "timeout"}),
            ),
        ),
    ),
    CapabilitySpec(
        id="mapcidr",
        label="MapCIDR",
        request_event="mapcidr_scan_requested",
        queue="enumeration",
        default_profile="cidr-expand",
        scope_policy=ScopePolicy.NONE,
        profiles=(
            ProfileSpec(
                id="cidr-expand",
                label="CIDR expansion",
                safety_level=SafetyLevel.PASSIVE,
                allowed_options=frozenset({"skip_base", "skip_broadcast", "shuffle", "timeout"}),
            ),
        ),
    ),
    CapabilitySpec(
        id="naabu",
        label="Naabu",
        request_event="naabu_scan_requested",
        queue="analysis",
        default_profile="passive-ports",
        scope_policy=ScopePolicy.STRICT,
        profiles=(
            ProfileSpec(
                id="passive-ports",
                label="Passive port discovery",
                safety_level=SafetyLevel.PASSIVE,
                allowed_options=frozenset({"ports", "top_ports", "rate", "scan_mode", "scan_type", "exclude_cdn", "timeout"}),
            ),
            ProfileSpec(
                id="connect-top-100",
                label="Top 100 TCP connect scan",
                safety_level=SafetyLevel.ACTIVE,
                allowed_options=frozenset({"ports", "top_ports", "rate", "scan_mode", "scan_type", "exclude_cdn", "timeout"}),
                requires_approval=True,
            ),
        ),
    ),
    CapabilitySpec(
        id="mantra",
        label="Mantra",
        request_event="mantra_scan_requested",
        queue="analysis",
        default_profile="js-secret-analysis",
        scope_policy=ScopePolicy.CONFIDENCE,
        profiles=(
            ProfileSpec(
                id="js-secret-analysis",
                label="JavaScript secret analysis",
                safety_level=SafetyLevel.SAFE_ACTIVE,
                allowed_options=frozenset({"timeout"}),
            ),
        ),
    ),
)

CAPABILITY_BY_ID = {capability.id: capability for capability in CAPABILITIES}
CAPABILITY_BY_EVENT = {capability.request_event: capability for capability in CAPABILITIES}


def get_capability(capability_id: str) -> CapabilitySpec:
    return CAPABILITY_BY_ID[capability_id]
