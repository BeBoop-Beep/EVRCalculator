"""Versioned C2.5 evidence-readiness gates; these do not calculate appeal."""
from __future__ import annotations

QUALITY_GATE_VERSION = "collector_source_quality_gates_v1"


def limitless_gate(metrics):
    total = max(int(metrics.get("observations") or 0), 1)
    matched = int(metrics.get("matched") or 0) / total
    ambiguous = int(metrics.get("ambiguous") or 0) / total
    checks = {
        "matchedShareAtLeast95Pct": matched >= .95,
        "ambiguousShareAtMost5Pct": ambiguous <= .05,
        "atLeast10Events": int(metrics.get("eventsSelected") or 0) >= 10,
        "minimumMeanDecklistCoverage80Pct": float(metrics.get("meanDecklistCoverage") or 0) >= .8,
    }
    return {"gateVersion":QUALITY_GATE_VERSION,"source":"limitless","passed":all(checks.values()),
            "checks":checks,"matchedShare":matched,"ambiguousShare":ambiguous}


def registry_gate(metrics):
    checks = {
        "namedCharacterCoverageAtLeast85Pct": float(metrics.get("namedCharacterCoverage") or 0) >= .85,
        "premiumNamedCoverageAtLeast90Pct": float(metrics.get("premiumNamedCoverage") or 0) >= .90,
        "hitEligibleNamedCoverageAtLeast90Pct": float(metrics.get("hitEligibleNamedCoverage") or 0) >= .90,
    }
    return {"gateVersion":QUALITY_GATE_VERSION,"source":"trainer_registry","passed":all(checks.values()),"checks":checks}


def trends_gate(metrics, source):
    eligible=max(int(metrics.get("eligible") or 0),1); scaled=int(metrics.get("scaled") or 0)/eligible
    confirmed_zero=int(metrics.get("zeroConfirmed") or 0)/eligible
    unresolved=int(metrics.get("unresolved") or 0)/eligible
    retrieval=scaled+confirmed_zero
    checks={"retrievalCoverageAtLeast95Pct":retrieval >= .95,"missingOrFailedShareAtMost5Pct":unresolved <= .05,
            "anchorBridgeIntegrity":bool(metrics.get("anchorBridgeIntegrity")),
            "apparentZerosRetested":bool(metrics.get("apparentZerosRetested"))}
    return {"gateVersion":QUALITY_GATE_VERSION,"source":source,"passed":all(checks.values()),"checks":checks,
            "retrievalCoverage":retrieval,"observableSignalCoverage":scaled,"confirmedZeroShare":confirmed_zero,
            "missingOrFailedShare":unresolved}
