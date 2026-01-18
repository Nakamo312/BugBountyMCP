"""Scope validation utility"""
import re
from typing import List, Tuple
from urllib.parse import urlparse

from api.domain.enums import RuleType, ScopeAction
from api.domain.models import ScopeRuleModel


class ScopeChecker:
    """Utility for checking if targets match program scope rules"""

    @staticmethod
    def filter_in_scope(targets: List[str], scope_rules: List[ScopeRuleModel]) -> Tuple[List[str], List[str]]:
        """
        Filter targets by scope rules.

        Args:
            targets: List of domains or URLs
            scope_rules: List of program scope rules

        Returns:
            Tuple of (in_scope_targets, out_of_scope_targets)
        """
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
        """
        Check if target matches program scope rules with include/exclude logic.

        Logic:
        1. If no rules exist - everything is in scope
        2. Check exclude rules first - if matches, out of scope
        3. Check include rules - if matches, in scope
        4. If no include rules matched - out of scope

        Args:
            target: Domain or URL to check
            scope_rules: List of program scope rules

        Returns:
            True if target is in scope
        """
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
    def _matches_rule(target: str, domain: str, rule: ScopeRuleModel) -> bool:
        """
        Check if target matches a specific scope rule.

        Args:
            target: Full URL or domain to check
            domain: Extracted hostname from target
            rule: Scope rule to match against

        Returns:
            True if target matches rule
        """
        if rule.rule_type == RuleType.DOMAIN:
            return domain == rule.value

        if rule.rule_type == RuleType.WILDCARD:
            pattern = rule.value.replace('.', r'\.')
            pattern = pattern.replace('*', '.*')
            return re.match(f'^{pattern}$', domain) is not None

        if rule.rule_type == RuleType.REGEX:
            try:
                return re.search(rule.value, target) is not None
            except re.error:
                return False

        if rule.rule_type == RuleType.CIDR:
            return False

        return False
