"""Scope validation utility with confidence scoring"""
import re
import logging
from typing import List, Tuple, Optional
from urllib.parse import urlparse

from api.domain.enums import RuleType, ScopeAction
from api.domain.models import ScopeRuleModel
from api.application.utils.confidence_scorer import (
    ConfidenceResult,
    Signal,
    SignalType,
)

logger = logging.getLogger(__name__)


class ScopeChecker:
    """Utility for checking if targets match program scope rules"""

    @staticmethod
    def filter_in_scope(targets: List[str], scope_rules: List[ScopeRuleModel]) -> Tuple[List[str], List[str]]:
        in_scope = []
        out_of_scope = []

        for target in targets:
            if ScopeChecker.is_in_scope(target, scope_rules):
                in_scope.append(target)
            else:
                out_of_scope.append(target)

        return in_scope, out_of_scope

    @staticmethod
    def is_in_scope(target: str, scope_rules: List[ScopeRuleModel]) -> bool:
        if not scope_rules:
            return True

        parsed = urlparse(target if target.startswith(('http://', 'https://')) else f'http://{target}')
        domain = parsed.hostname

        if not domain:
            return False

        for rule in scope_rules:
            if rule.action == ScopeAction.EXCLUDE:
                if ScopeChecker._matches_rule(target, domain, rule):
                    return False

        has_include_rules = any(r.action == ScopeAction.INCLUDE for r in scope_rules)
        if not has_include_rules:
            return True

        for rule in scope_rules:
            if rule.action == ScopeAction.INCLUDE:
                if ScopeChecker._matches_rule(target, domain, rule):
                    return True

        return False

    @staticmethod
    def score_target(
        target: str,
        scope_rules: List[ScopeRuleModel],
        san_domains: Optional[List[str]] = None,
        ptr_hostname: Optional[str] = None,
        asn_numbers: Optional[List[int]] = None,
        program_asns: Optional[List[int]] = None,
        cname_chain: Optional[List[str]] = None,
        cdn_hostname: Optional[str] = None,
    ) -> ConfidenceResult:
        """
        Score target confidence based on multiple signals.

        Args:
            target: Domain or URL to check
            scope_rules: Program scope rules
            san_domains: SAN domains from TLS certificate
            ptr_hostname: PTR record hostname
            asn_numbers: ASN numbers for target IP
            program_asns: Known ASNs for the program
            cname_chain: CNAME chain hostnames
            cdn_hostname: CDN edge hostname

        Returns:
            ConfidenceResult with calculated score
        """
        result = ConfidenceResult(target=target, score=0.0)

        domain_match = ScopeChecker.is_in_scope(target, scope_rules)
        if domain_match:
            result.add_signal(Signal(
                SignalType.DOMAIN_RULE,
                True,
                source="scope_rules",
                details=f"Matches scope rule"
            ))

        if san_domains:
            for san in san_domains:
                if ScopeChecker.is_in_scope(san, scope_rules):
                    result.add_signal(Signal(
                        SignalType.SAN_CERT,
                        True,
                        source="tls_san",
                        details=f"SAN {san} matches scope"
                    ))
                    break

        if ptr_hostname and ScopeChecker.is_in_scope(ptr_hostname, scope_rules):
            result.add_signal(Signal(
                SignalType.PTR_RECORD,
                True,
                source="dns_ptr",
                details=f"PTR {ptr_hostname} matches scope"
            ))

        if asn_numbers and program_asns:
            matching_asn = set(asn_numbers) & set(program_asns)
            if matching_asn:
                result.add_signal(Signal(
                    SignalType.ASN_MATCH,
                    True,
                    source="asn",
                    details=f"ASN {matching_asn} belongs to program"
                ))

        if cname_chain:
            for cname in cname_chain:
                if ScopeChecker.is_in_scope(cname, scope_rules):
                    result.add_signal(Signal(
                        SignalType.CNAME_CHAIN,
                        True,
                        source="dns_cname",
                        details=f"CNAME {cname} matches scope"
                    ))
                    break

        if cdn_hostname and ScopeChecker.is_in_scope(cdn_hostname, scope_rules):
            result.add_signal(Signal(
                SignalType.CDN_EDGE,
                True,
                source="cdn",
                details=f"CDN {cdn_hostname} matches scope"
            ))

        return result

    @staticmethod
    def filter_by_confidence(
        targets: List[str],
        scope_rules: List[ScopeRuleModel],
        threshold: float = 0.6,
        enrichment_data: Optional[dict] = None,
    ) -> Tuple[List[str], List[str], List[ConfidenceResult]]:
        """
        Filter targets by confidence score.

        Args:
            targets: List of domains or URLs
            scope_rules: Program scope rules
            threshold: Minimum confidence score
            enrichment_data: Optional dict mapping target -> enrichment signals

        Returns:
            Tuple of (high_confidence, low_confidence, all_results)
        """
        enrichment = enrichment_data or {}
        high_confidence = []
        low_confidence = []
        results = []

        for target in targets:
            target_enrichment = enrichment.get(target, {})
            result = ScopeChecker.score_target(
                target,
                scope_rules,
                san_domains=target_enrichment.get("san_domains"),
                ptr_hostname=target_enrichment.get("ptr_hostname"),
                asn_numbers=target_enrichment.get("asn_numbers"),
                program_asns=target_enrichment.get("program_asns"),
                cname_chain=target_enrichment.get("cname_chain"),
                cdn_hostname=target_enrichment.get("cdn_hostname"),
            )
            results.append(result)

            if result.score >= threshold:
                high_confidence.append(target)
                logger.debug(f"High confidence: {target} score={result.score:.2f}")
            else:
                low_confidence.append(target)
                logger.debug(f"Low confidence: {target} score={result.score:.2f}")

        return high_confidence, low_confidence, results

    @staticmethod
    def _matches_rule(target: str, domain: str, rule: ScopeRuleModel) -> bool:
        if rule.rule_type == RuleType.DOMAIN:
            pattern = rule.pattern
            if pattern.startswith('*.'):
                base_domain = pattern[2:]
                if domain == base_domain:
                    return True
                if domain.endswith('.' + base_domain):
                    return True
            return domain == pattern

        if rule.rule_type == RuleType.WILDCARD:
            pattern = rule.pattern.replace('.', r'\.')
            pattern = pattern.replace('*', '.*')
            return re.match(f'^{pattern}$', domain) is not None

        if rule.rule_type == RuleType.REGEX:
            try:
                return re.search(rule.pattern, target) is not None
            except re.error:
                return False

        if rule.rule_type == RuleType.CIDR:
            return False

        return False
