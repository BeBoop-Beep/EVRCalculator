"""Audit the raw Financial RIP V3 inputs across the current simulation cohort.

WHY THIS EXISTS
---------------
Financial RIP V3 is normalized against FIXED absolute anchors, not against the
current cohort. That is the property that makes a V3 score comparable across
publication runs - but it also means a badly-chosen anchor is invisible at
runtime. If, say, every real set's ``p95_threshold_ratio`` lands above the upper
knot, all of them clip to 100 and the component stops distinguishing anything
while still looking like a working score.

This script is the check. For every raw V3 input across every currently
supported opening set it reports the distribution, the configured anchors, and
how many sets would clip at each bound. A high clip count at either bound means
the anchor is wrong and should be revised in
``backend/calculations/evr/financial_rip_v3_config.py`` - with the normalization
version bumped, so scores computed under the old anchors stay identifiable.

WHAT IT DOES NOT DO
-------------------
It does not fit anchors to the data. Anchors are chosen from the FINANCIAL
MEANING of each metric and merely sanity-checked here; auto-fitting them to the
current cohort would reintroduce exactly the cohort dependence V3 exists to
remove, just once per deploy instead of once per read.

It is READ-ONLY. It writes nothing to the database.

USAGE
-----
    python -m backend.scripts.audit_financial_rip_v3_inputs
    python -m backend.scripts.audit_financial_rip_v3_inputs --json report.json
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import sys
from typing import Any, Dict, List, Mapping, Optional, Sequence

from backend.calculations.evr.financial_rip_v3_config import (
    FINANCIAL_RIP_V3_COMPONENT_INPUTS,
    FINANCIAL_RIP_V3_CONFIG_VERSION,
    FINANCIAL_RIP_V3_MIN_SIMULATION_COUNT,
    FINANCIAL_RIP_V3_NORMALIZATION_VERSION,
    FINANCIAL_RIP_V3_TRANSFORMS,
    FINANCIAL_RIP_V3_VERSION,
    PIECEWISE_LINEAR,
    SATURATING_EXP,
    normalize_metric,
)

logger = logging.getLogger(__name__)

# Where each raw input lives inside a persisted V3 payload's component blocks.
RAW_INPUT_LOCATIONS: Dict[str, tuple] = {
    "true_win_probability": ("true_win_frequency", "trueWinProbability"),
    "typical_retention_ratio": ("typical_retention", "typicalRetentionRatio"),
    "average_retention_given_loss": ("loss_resilience", "averageRetentionGivenLoss"),
    "soft_loss_share_given_loss": ("loss_resilience", "softLossShareGivenLoss"),
    "p95_threshold_ratio": ("realistic_upside", "p95ThresholdRatio"),
    "realistic_tail_mean_ratio": ("realistic_upside", "realisticTailMeanRatio"),
    "p99_threshold_ratio": ("jackpot_upside", "p99ThresholdRatio"),
    "jackpot_tail_mean_ratio": ("jackpot_upside", "jackpotTailMeanRatio"),
    "base_rtp_excluding_top_1pct": ("base_economic_efficiency", "baseRtpExcludingTop1Pct"),
}

# Above this share of the cohort clipping at one bound, the anchor is reported
# as needing revision. A third of the cohort pinned to the same score means the
# component has stopped discriminating over the range that actually occurs.
CLIP_WARNING_SHARE = 1.0 / 3.0


def _finite(value: Any) -> Optional[float]:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _quantile(sorted_values: Sequence[float], q: float) -> Optional[float]:
    """Linear-interpolated quantile without a NumPy dependency."""
    if not sorted_values:
        return None
    if len(sorted_values) == 1:
        return sorted_values[0]
    position = q * (len(sorted_values) - 1)
    low = math.floor(position)
    high = math.ceil(position)
    if low == high:
        return sorted_values[int(position)]
    weight = position - low
    return sorted_values[low] * (1.0 - weight) + sorted_values[high] * weight


def _parse_payload(raw: Any) -> Dict[str, Any]:
    if isinstance(raw, Mapping):
        return dict(raw)
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
        except (TypeError, ValueError):
            return {}
        return dict(parsed) if isinstance(parsed, dict) else {}
    return {}


def load_latest_v3_rows() -> List[Dict[str, Any]]:
    """Latest complete, non-placeholder simulation per supported opening set.

    Reads the same view the publication path reads, so the audit describes the
    rows that would actually be published rather than a parallel query with its
    own idea of what "latest" means.
    """
    from backend.db.clients.supabase_client import service_read_client

    response = (
        service_read_client.table("explore_rip_statistics_latest")
        .select("*")
        .order("run_at", desc=True)
        .limit(500)
        .execute()
    )
    rows = list(getattr(response, "data", None) or [])
    # The view is latest-per-target already; the guard is for a target that
    # somehow appears twice, where the newest run wins.
    seen: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        target_id = str(row.get("set_id") or row.get("target_id") or "")
        if not target_id or target_id in seen:
            continue
        seen[target_id] = row
    return list(seen.values())


def collect_raw_inputs(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """Pull every raw V3 input off every row, tracking what is missing and why."""
    by_metric: Dict[str, List[float]] = {metric: [] for metric in RAW_INPUT_LOCATIONS}
    missing_by_metric: Dict[str, int] = {metric: 0 for metric in RAW_INPUT_LOCATIONS}
    sets_with_payload: List[str] = []
    sets_needing_rerun: List[Dict[str, Any]] = []

    for row in rows:
        name = str(row.get("set_name") or row.get("name") or row.get("set_id") or "unknown")
        payload = _parse_payload(row.get("financial_rip_v3_payload"))
        if not payload:
            sets_needing_rerun.append(
                {
                    "set": name,
                    "setId": str(row.get("set_id") or row.get("target_id") or ""),
                    "canonicalKey": row.get("canonical_key"),
                    "runAt": row.get("run_at"),
                    # An honest reason, not a guess. The realistic-tail and
                    # top-1% conditional means need the ORIGINAL outcome vector;
                    # they cannot be recovered from stored percentiles, so this
                    # set genuinely requires a rerun.
                    "reason": "no_financial_rip_v3_payload_on_latest_run",
                    "remediation": (
                        "Re-run the simulation for this set; V3 cannot be "
                        "backfilled from stored percentiles."
                    ),
                }
            )
            continue

        sets_with_payload.append(name)
        components = payload.get("components") or {}
        for metric, (component_key, field) in RAW_INPUT_LOCATIONS.items():
            block = components.get(component_key) or {}
            raw_block = block.get("raw") or {}
            value = _finite(raw_block.get(field))
            if value is None:
                missing_by_metric[metric] += 1
            else:
                by_metric[metric].append(value)

    return {
        "byMetric": by_metric,
        "missingByMetric": missing_by_metric,
        "setsWithPayload": sets_with_payload,
        "setsNeedingRerun": sets_needing_rerun,
    }


def describe_metric(metric: str, values: Sequence[float], missing_count: int) -> Dict[str, Any]:
    """Distribution, configured anchors, and the clip counts at each bound."""
    spec = FINANCIAL_RIP_V3_TRANSFORMS[metric]
    ordered = sorted(values)
    n = len(ordered)

    if spec["family"] == PIECEWISE_LINEAR:
        lower_anchor = float(spec["knots"][0][0])
        upper_anchor = float(spec["knots"][-1][0])
        anchor_description = f"piecewise-linear over {[list(k) for k in spec['knots']]}"
    else:
        lower_anchor = 0.0
        # A saturating transform has no hard upper bound; report the value that
        # reaches 99 of 100 as the practical ceiling.
        upper_anchor = float(spec["k"]) * math.log(100.0)
        anchor_description = f"saturating 100*(1-exp(-raw/{spec['k']}))"

    clipped_low = 0
    clipped_high = 0
    for value in ordered:
        record = normalize_metric(metric, value)
        if record["clippedAt"] == "lower":
            clipped_low += 1
        elif record["clippedAt"] == "upper":
            clipped_high += 1

    saturated_high = sum(
        1 for value in ordered if (normalize_metric(metric, value)["score"] or 0.0) >= 99.0
    )
    at_zero = sum(1 for value in ordered if (normalize_metric(metric, value)["score"] or 0.0) <= 1.0)

    warnings: List[str] = []
    if n:
        if clipped_high / n > CLIP_WARNING_SHARE:
            warnings.append(
                f"{clipped_high}/{n} sets clip at the UPPER anchor ({upper_anchor}); "
                "the component cannot discriminate over the observed range."
            )
        if clipped_low / n > CLIP_WARNING_SHARE:
            warnings.append(
                f"{clipped_low}/{n} sets clip at the LOWER anchor ({lower_anchor})."
            )
        if saturated_high / n > CLIP_WARNING_SHARE:
            warnings.append(
                f"{saturated_high}/{n} sets score >= 99; raise the saturation constant."
            )

    return {
        "metric": metric,
        "component": next(
            component
            for component, inputs in FINANCIAL_RIP_V3_COMPONENT_INPUTS.items()
            if metric in inputs
        ),
        "count": n,
        "missingCount": missing_count,
        "min": ordered[0] if n else None,
        "p05": _quantile(ordered, 0.05),
        "p10": _quantile(ordered, 0.10),
        "p25": _quantile(ordered, 0.25),
        "median": _quantile(ordered, 0.50),
        "p75": _quantile(ordered, 0.75),
        "p90": _quantile(ordered, 0.90),
        "p95": _quantile(ordered, 0.95),
        "max": ordered[-1] if n else None,
        "proposedLowerAnchor": lower_anchor,
        "proposedUpperAnchor": upper_anchor,
        "anchorDescription": anchor_description,
        "anchorRationale": spec["rationale"],
        "clippedAtLowerCount": clipped_low,
        "clippedAtUpperCount": clipped_high,
        "clippedAtLowerShare": (clipped_low / n) if n else None,
        "clippedAtUpperShare": (clipped_high / n) if n else None,
        "scoresAtOrBelow1Count": at_zero,
        "scoresAtOrAbove99Count": saturated_high,
        "direction": spec["direction"],
        "transform": spec["family"],
        "warnings": warnings,
    }


def build_report(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    collected = collect_raw_inputs(rows)
    metrics = [
        describe_metric(
            metric,
            collected["byMetric"][metric],
            collected["missingByMetric"][metric],
        )
        for metric in RAW_INPUT_LOCATIONS
    ]
    warnings = [warning for metric in metrics for warning in metric["warnings"]]
    return {
        "scoreVersion": FINANCIAL_RIP_V3_VERSION,
        "normalizationVersion": FINANCIAL_RIP_V3_NORMALIZATION_VERSION,
        "configVersion": FINANCIAL_RIP_V3_CONFIG_VERSION,
        "minSimulationCount": FINANCIAL_RIP_V3_MIN_SIMULATION_COUNT,
        "setsExamined": len(rows),
        "setsWithV3Payload": len(collected["setsWithPayload"]),
        "setsNeedingRerun": collected["setsNeedingRerun"],
        "metrics": metrics,
        "anchorWarnings": warnings,
        "verdict": "anchors_need_revision" if warnings else "anchors_acceptable",
        "note": (
            "Anchors are chosen from the financial meaning of each metric and "
            "only sanity-checked here. This report never fits anchors to the "
            "cohort; doing so would restore the cohort dependence V3 removes."
        ),
    }


def _fmt(value: Optional[float]) -> str:
    return "—" if value is None else f"{value:,.4f}"


def print_report(report: Mapping[str, Any]) -> None:
    print("=" * 100)
    print("FINANCIAL RIP V3 — RAW INPUT / ANCHOR AUDIT")
    print("=" * 100)
    print(f"Score version         : {report['scoreVersion']}")
    print(f"Normalization version : {report['normalizationVersion']}")
    print(f"Sets examined         : {report['setsExamined']}")
    print(f"Sets with V3 payload  : {report['setsWithV3Payload']}")
    print()

    for metric in report["metrics"]:
        print("-" * 100)
        print(f"{metric['metric']}   (component: {metric['component']}, {metric['transform']})")
        print(f"  count={metric['count']}  missing={metric['missingCount']}")
        print(
            "  min="
            + _fmt(metric["min"])
            + "  p05=" + _fmt(metric["p05"])
            + "  p10=" + _fmt(metric["p10"])
            + "  p25=" + _fmt(metric["p25"])
        )
        print(
            "  med="
            + _fmt(metric["median"])
            + "  p75=" + _fmt(metric["p75"])
            + "  p90=" + _fmt(metric["p90"])
            + "  p95=" + _fmt(metric["p95"])
            + "  max=" + _fmt(metric["max"])
        )
        print(f"  anchors: {metric['anchorDescription']}")
        print(
            f"  clipping: lower={metric['clippedAtLowerCount']} "
            f"upper={metric['clippedAtUpperCount']} "
            f"(>=99 score: {metric['scoresAtOrAbove99Count']}, <=1 score: {metric['scoresAtOrBelow1Count']})"
        )
        print(f"  rationale: {metric['anchorRationale']}")
        for warning in metric["warnings"]:
            print(f"  !! {warning}")

    print("-" * 100)
    if report["setsNeedingRerun"]:
        print()
        print(f"SETS REQUIRING A SIMULATION RERUN ({len(report['setsNeedingRerun'])}):")
        for entry in report["setsNeedingRerun"]:
            print(f"  - {entry['set']}: {entry['reason']}")
        print()
        print("  V3 is NOT backfillable from stored percentiles: the realistic-tail")
        print("  and top-1% conditional means require the original outcome vector.")
        print("  Rerun command, per set:")
        print("      python -m backend.jobs.evr_runner --set <canonical_key> --input-source db")
    print()
    print(f"VERDICT: {report['verdict']}")
    print("=" * 100)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", dest="json_path", default=None, help="Write the report as JSON.")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    try:
        rows = load_latest_v3_rows()
    except Exception as exc:  # noqa: BLE001 - a read failure must be reported, not masked
        print(f"FAILED to read explore_rip_statistics_latest: {exc}", file=sys.stderr)
        return 2

    report = build_report(rows)
    print_report(report)

    if args.json_path:
        with open(args.json_path, "w", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2, sort_keys=True)
        print(f"\nWrote {args.json_path}")

    return 0 if report["verdict"] == "anchors_acceptable" else 1


if __name__ == "__main__":
    raise SystemExit(main())
