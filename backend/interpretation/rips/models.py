"""Typed models for layered RIP interpretation outputs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional, TypedDict

SignalLevel = Literal["high", "medium", "low"]
TypicalOutcome = Literal["above_cost", "near_cost", "below_cost"]
DistributionQuality = Literal["broad", "moderate", "narrow"]

# Severity and confidence for structured section outputs
InterpretationSeverity = Literal["positive", "neutral", "caution", "negative", "data_limited"]
InterpretationConfidence = Literal["high", "medium", "low"]


class ProfitSignals(TypedDict):
    upside_strength: SignalLevel
    profit_frequency: SignalLevel
    typical_outcome: TypicalOutcome


class SafetySignals(TypedDict):
    # downside_pressure: high means more downside pressure (bad)
    # loss_depth: high means losses are deeper (bad)
    # safety_score: high means safer (good) — opposite direction from these signals
    downside_pressure: SignalLevel
    loss_depth: SignalLevel


class StabilitySignals(TypedDict):
    volatility: SignalLevel
    concentration: SignalLevel
    distribution_quality: DistributionQuality


@dataclass
class EvidenceItem:
    """A single evidence bullet with a readable label and value."""
    label: str
    value: Any  # str | int | float | None
    detail: Optional[str] = None


@dataclass
class SectionInterpretation:
    """Structured interpretation output for a single section or pillar."""
    summary: str
    label: str
    reason_code: str
    severity: InterpretationSeverity
    confidence: InterpretationConfidence
    evidence: List[EvidenceItem] = field(default_factory=list)
    signals: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ProfitInterpretation:
    summary: str
    signals: ProfitSignals
    score: Optional[float] = None
    meta: Optional[SectionInterpretation] = None


@dataclass(frozen=True)
class SafetyInterpretation:
    summary: str
    signals: SafetySignals
    score: Optional[float] = None
    meta: Optional[SectionInterpretation] = None


@dataclass(frozen=True)
class StabilityInterpretation:
    summary: str
    signals: StabilitySignals
    score: Optional[float] = None
    meta: Optional[SectionInterpretation] = None


@dataclass(frozen=True)
class PackScoreInterpretation:
    summary: str
    strongest_pillar: str
    weakest_pillar: str
    alignment: str
    imbalance: bool
    pillar_strengths: Dict[str, SignalLevel]
    meta: Optional[SectionInterpretation] = None


def as_float(value: Any) -> Optional[float]:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed
