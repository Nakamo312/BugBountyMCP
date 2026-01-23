"""
Confidence scoring system with weighted signals.

confidence = Σ(weight_i × signal_i), bounded [0, 1]

Signals and weights:
- Domain rule match: +1.0 (explicit scope match)
- SAN cert contains in-scope domain: +0.6
- PTR points to in-scope domain: +0.5
- IP in company ASN: +0.4
- CNAME chain to in-scope: +0.3
- CDN edge with hostname match: +0.2
"""
import logging
from dataclasses import dataclass, field
from typing import List, Optional, Set
from enum import Enum

logger = logging.getLogger(__name__)


class SignalType(str, Enum):
    DOMAIN_RULE = "domain_rule"
    SAN_CERT = "san_cert"
    PTR_RECORD = "ptr_record"
    ASN_MATCH = "asn_match"
    CNAME_CHAIN = "cname_chain"
    CDN_EDGE = "cdn_edge"
    REVERSE_WHOIS = "reverse_whois"


SIGNAL_WEIGHTS = {
    SignalType.DOMAIN_RULE: 1.0,
    SignalType.SAN_CERT: 0.6,
    SignalType.PTR_RECORD: 0.5,
    SignalType.ASN_MATCH: 0.4,
    SignalType.REVERSE_WHOIS: 0.3,
    SignalType.CNAME_CHAIN: 0.3,
    SignalType.CDN_EDGE: 0.2,
}


@dataclass
class Signal:
    signal_type: SignalType
    value: bool = True
    source: Optional[str] = None
    details: Optional[str] = None

    @property
    def weight(self) -> float:
        return SIGNAL_WEIGHTS.get(self.signal_type, 0.0) if self.value else 0.0


@dataclass
class ConfidenceResult:
    target: str
    score: float
    signals: List[Signal] = field(default_factory=list)
    is_in_scope: bool = False

    def add_signal(self, signal: Signal):
        self.signals.append(signal)
        self._recalculate()

    def _recalculate(self):
        total = sum(s.weight for s in self.signals)
        self.score = min(1.0, total)
        self.is_in_scope = any(
            s.signal_type == SignalType.DOMAIN_RULE and s.value
            for s in self.signals
        )


class ConfidenceScorer:
    """
    Calculates confidence scores for targets based on multiple weighted signals.
    """

    def __init__(self, threshold: float = 0.6):
        self.threshold = threshold

    def score_target(
        self,
        target: str,
        domain_match: bool = False,
        san_match: bool = False,
        ptr_match: bool = False,
        asn_match: bool = False,
        cname_match: bool = False,
        cdn_match: bool = False,
        whois_match: bool = False,
    ) -> ConfidenceResult:
        result = ConfidenceResult(target=target, score=0.0)

        if domain_match:
            result.add_signal(Signal(SignalType.DOMAIN_RULE, True))
        if san_match:
            result.add_signal(Signal(SignalType.SAN_CERT, True))
        if ptr_match:
            result.add_signal(Signal(SignalType.PTR_RECORD, True))
        if asn_match:
            result.add_signal(Signal(SignalType.ASN_MATCH, True))
        if cname_match:
            result.add_signal(Signal(SignalType.CNAME_CHAIN, True))
        if cdn_match:
            result.add_signal(Signal(SignalType.CDN_EDGE, True))
        if whois_match:
            result.add_signal(Signal(SignalType.REVERSE_WHOIS, True))

        return result

    def is_confident(self, result: ConfidenceResult) -> bool:
        return result.score >= self.threshold

    def filter_by_confidence(
        self,
        results: List[ConfidenceResult]
    ) -> tuple[List[ConfidenceResult], List[ConfidenceResult]]:
        confident = []
        uncertain = []

        for r in results:
            if self.is_confident(r):
                confident.append(r)
            else:
                uncertain.append(r)

        return confident, uncertain
