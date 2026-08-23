"""Parts 20-21 and 30-33: cross-sectional analysis and the research report.

    python -m backend.scripts.report_ev_representativeness_research \
        --market-date 2026-08-22 --out backend/docs/research/ev_representativeness

Reads only what the builder persisted. Produces:

  * a Markdown research report (Part 30's ranked tables, Part 31's outliers,
    Parts 20/21's hypothesis tests, Part 33's archetype check)
  * a CSV of the set-level dataset (Part 38-D)
  * a JSON dump of the full correlation matrix and hypothesis verdicts

STATISTICAL POSTURE
-------------------
n = 22 sets. Every correlation is reported with BOTH Pearson and Spearman - the
relationships here are expected to be nonlinear and driven by extreme values, so
a single linear r would be the wrong summary and a disagreement between the two
is itself informative. Each carries a percentile bootstrap CI over resampled
PAIRS and a two-sided permutation p-value, and Benjamini-Hochberg adjustment is
applied WITHIN each hypothesis family, because screening ~30 correlations at
alpha = 0.05 would otherwise be expected to manufacture a false positive or two.

Product-level rows are NOT treated as independent observations. The SKUs in the
cohort are 22 underlying pack distributions re-expressed at a handful of pack
counts; the effective sample size for inference stays 22, and the report says so
wherever product data appears.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.db.clients.supabase_client import create_service_role_client
from backend.research.ev_representativeness.version import (
    CONVERGENCE_TOLERANCES,
    EV_REPRESENTATIVENESS_VERSION,
    REALIZATION_TARGETS,
)
from backend.research.validation_stats import (
    benjamini_hochberg,
    bootstrap_correlation_ci,
    paired,
    pearson,
    permutation_p_value,
    spearman,
)

BOOTSTRAP_DRAWS = 4000
PERMUTATION_DRAWS = 10000
SEED = 20260823


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def _rows(response: Any) -> List[Dict[str, Any]]:
    return list((response.data if response else []) or [])


def _f(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return numeric if math.isfinite(numeric) else None


def load_dataset(client: Any, *, market_date: str) -> Dict[str, Any]:
    summaries = _rows(
        client.table("ev_representativeness_run_summary")
        .select("*")
        .eq("market_date", market_date)
        .eq("research_method_version", EV_REPRESENTATIVENESS_VERSION)
        .execute()
    )
    if not summaries:
        raise RuntimeError(f"no research summaries for {market_date}")

    run_ids = [str(row["calculation_run_id"]) for row in summaries]

    # Financial RIP from simulation_derived_metrics on the SAME runs. Not from
    # the published leaderboard: it can lag the simulation cohort by days, and
    # joining across dates would put cross-run contamination into every H5 cell.
    derived: Dict[str, Dict[str, Any]] = {}
    products: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    curves: Dict[Tuple[str, str, int], Dict[str, Any]] = {}
    for start in range(0, len(run_ids), 20):
        chunk = run_ids[start : start + 20]
        for row in _rows(
            client.table("simulation_derived_metrics")
            .select("calculation_run_id,financial_rip_v3_score,financial_rip_v3_status,"
                    "financial_rip_v3_typical_retention_ratio,financial_rip_v3_total_rtp_ratio,"
                    "financial_rip_v3_jackpot_value_share,financial_rip_v3_base_rtp_excluding_top_1pct,"
                    "financial_rip_v3_true_win_probability,financial_rip_v3_p95_threshold_ratio,"
                    "hhi_ev_concentration,top1_ev_share,top5_ev_share")
            .in_("calculation_run_id", chunk)
            .execute()
        ):
            derived[str(row["calculation_run_id"])] = row
        for row in _rows(
            client.table("simulation_sealed_product_results")
            .select("calculation_run_id,sealed_product_id,product_name,product_family,pack_count,"
                    "product_market_cost,financial_rip_v4_score,financial_rip_v4_status")
            .in_("calculation_run_id", chunk)
            .execute()
        ):
            products[str(row["calculation_run_id"])].append(row)

    # Curve rows: paged, filtered to the metrics the report actually uses.
    wanted_metrics = (
        [f"realization_ge_{t:.2f}" for t in REALIZATION_TARGETS]
        + [f"within_tau_{t:.2f}" for t in CONVERGENCE_TOLERANCES]
        + ["session_recovers_cost", "session_p50_per_pack", "session_mean_per_pack"]
    )
    curve_rows: List[Dict[str, Any]] = []
    for start in range(0, len(run_ids), 5):
        chunk = run_ids[start : start + 5]
        offset = 0
        while True:
            page = _rows(
                client.table("ev_representativeness_curve")
                .select("calculation_run_id,scope_kind,sealed_product_key,pack_count,metric_key,"
                        "estimate,ci_lower,ci_upper,session_count,stage")
                .eq("research_method_version", EV_REPRESENTATIVENESS_VERSION)
                .in_("calculation_run_id", chunk)
                .in_("metric_key", wanted_metrics)
                .range(offset, offset + 999)
                .execute()
            )
            curve_rows.extend(page)
            if len(page) < 1000:
                break
            offset += 1000

    cards: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for start in range(0, len(run_ids), 5):
        chunk = run_ids[start : start + 5]
        for row in _rows(
            client.table("ev_representativeness_card_contribution")
            .select("calculation_run_id,card_name,card_number,rarity_key,price_used,"
                    "expected_copies_per_pack,ev_contribution_per_pack,ev_share,ev_rank")
            .eq("research_method_version", EV_REPRESENTATIVENESS_VERSION)
            .in_("calculation_run_id", chunk)
            .lte("ev_rank", 10)
            .execute()
        ):
            cards[str(row["calculation_run_id"])].append(row)

    counterfactuals: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for start in range(0, len(run_ids), 5):
        chunk = run_ids[start : start + 5]
        for row in _rows(
            client.table("ev_representativeness_counterfactual")
            .select("calculation_run_id,scenario_key,scenario_family,ev,p50,typical_capture,"
                    "top1_outcome_ev_share,delta_vs_baseline")
            .eq("research_method_version", EV_REPRESENTATIVENESS_VERSION)
            .in_("calculation_run_id", chunk)
            .execute()
        ):
            counterfactuals[str(row["calculation_run_id"])].append(row)

    return {
        "summaries": sorted(summaries, key=lambda r: str(r.get("set_canonical_key"))),
        "derived": derived,
        "products": products,
        "curves": curve_rows,
        "cards": cards,
        "counterfactuals": counterfactuals,
        "marketDate": market_date,
    }


# ---------------------------------------------------------------------------
# Flatten to the analysis frame
# ---------------------------------------------------------------------------

CURVE_POINTS_OF_INTEREST = (1, 6, 9, 11, 18, 36, 72, 144)


def build_frame(dataset: Mapping[str, Any]) -> List[Dict[str, Any]]:
    curve_index: Dict[Tuple[str, str, int], Dict[str, Any]] = {}
    for row in dataset["curves"]:
        if row["scope_kind"] != "pack_grid":
            continue
        key = (str(row["calculation_run_id"]), str(row["metric_key"]), int(row["pack_count"]))
        # Prefer the sharpest stage available for a given point.
        rank = {"coarse": 0, "refine": 1, "confirm": 2}[str(row["stage"])]
        existing = curve_index.get(key)
        if existing is None or rank >= {"coarse": 0, "refine": 1, "confirm": 2}[str(existing["stage"])]:
            curve_index[key] = row

    frame: List[Dict[str, Any]] = []
    for summary in dataset["summaries"]:
        run_id = str(summary["calculation_run_id"])
        derived = dataset["derived"].get(run_id, {})
        record: Dict[str, Any] = {
            "canonicalKey": summary.get("set_canonical_key"),
            "calculationRunId": run_id,
            "packCost": _f(summary.get("pack_cost")),
            "ev": _f(summary.get("ev")),
            "p50": _f(summary.get("p50")),
            "p95": _f(summary.get("p95")),
            "p99": _f(summary.get("p99")),
            "stdDev": _f(summary.get("std_dev")),
            "cv": _f(summary.get("coefficient_of_variation")),
            "gapAbsolute": _f(summary.get("ev_typical_gap_absolute")),
            "gapCostNormalized": _f(summary.get("ev_typical_gap_cost_normalized")),
            "typicalCapture": _f(summary.get("typical_capture")),
            "relativeGap": _f(summary.get("relative_gap")),
            "pearsonSkew2": _f(summary.get("pearson_skew_2")),
            "gmSkew": _f(summary.get("groeneveld_meeden_skew")),
            "top1OutcomeShare": _f(summary.get("top1_outcome_ev_share")),
            "top5OutcomeShare": _f(summary.get("top5_outcome_ev_share")),
            "top10OutcomeShare": _f(summary.get("top10_outcome_ev_share")),
            "top1TailMean": _f(summary.get("top1_conditional_tail_mean")),
            "simTopCardShare": _f(summary.get("sim_top_card_ev_share")),
            "simTop5CardShare": _f(summary.get("sim_top5_card_ev_share")),
            "simTop10CardShare": _f(summary.get("sim_top10_card_ev_share")),
            "simCardHhi": _f(summary.get("sim_card_hhi")),
            "simEffectiveCardCount": _f(summary.get("sim_effective_card_count")),
            "simCardCount": summary.get("sim_card_count"),
            "horizonR80C80": summary.get("horizon_r80_c80_stable"),
            "horizonR80C80First": summary.get("horizon_r80_c80_first_crossing"),
            "horizonR80C80Status": summary.get("horizon_r80_c80_status"),
            "horizonTau20C80": summary.get("horizon_tau20_c80_stable"),
            "horizonTau20C80First": summary.get("horizon_tau20_c80_first_crossing"),
            "horizonTau20C80Status": summary.get("horizon_tau20_c80_status"),
            "monotonicityViolations": summary.get("monotonicity_violation_count"),
            "monotonicityMaxDecrease": _f(summary.get("monotonicity_max_decrease")),
            "reconciliationStatus": summary.get("reconciliation_status"),
            "reconciliationZ": _f(summary.get("reconciliation_z")),
            "reconciliationRelative": _f(summary.get("reconciliation_relative_diff")),
            "reconciliationP50Relative": _f(summary.get("reconciliation_p50_relative_diff")),
            "reconciliationP95Relative": _f(summary.get("reconciliation_p95_relative_diff")),
            "cardAttributionAuthoritative": summary.get("card_attribution_authoritative"),
            "financialRipV3": _f(derived.get("financial_rip_v3_score")),
            "ripTypicalRetentionRatio": _f(derived.get("financial_rip_v3_typical_retention_ratio")),
            "ripTotalRtpRatio": _f(derived.get("financial_rip_v3_total_rtp_ratio")),
            "ripJackpotValueShare": _f(derived.get("financial_rip_v3_jackpot_value_share")),
            "ripBaseRtpExTop1": _f(derived.get("financial_rip_v3_base_rtp_excluding_top_1pct")),
            "ripTrueWinProbability": _f(derived.get("financial_rip_v3_true_win_probability")),
            "ripP95ThresholdRatio": _f(derived.get("financial_rip_v3_p95_threshold_ratio")),
            "analyticHhi": _f(derived.get("hhi_ev_concentration")),
            "analyticTop1Share": _f(derived.get("top1_ev_share")),
            "runtimeSeconds": _f(summary.get("runtime_seconds")),
        }

        # Rarity structure (Part 8) and hit frequencies (Parts 9/10) off the JSON.
        rarity = summary.get("rarity_contributions_json") or {}
        for bucket in rarity.get("buckets", []):
            key = str(bucket.get("rarityKey", "")).replace(" ", "_")
            record[f"rarityShare__{key}"] = _f(bucket.get("evShare"))
            record[f"rarityCopies__{key}"] = _f(bucket.get("expectedCopiesPerPack"))
        record["rarityReconciliation"] = _f(rarity.get("reconciliationAbsolute"))

        hits = (summary.get("collective_hit_frequencies_json") or {}).get("groups", {})
        for label, payload in hits.items():
            record[f"hitProb__{label}"] = _f(payload.get("probabilityAtLeastOne"))

        economic = (summary.get("economic_hit_frequencies_json") or {}).get("thresholds", [])
        for entry in economic:
            multiple = _f(entry.get("costMultiple"))
            if multiple is not None:
                record[f"econHit__{multiple:.2f}x"] = _f(entry.get("probability"))

        for target in REALIZATION_TARGETS:
            for packs in CURVE_POINTS_OF_INTEREST:
                row = curve_index.get((run_id, f"realization_ge_{target:.2f}", packs))
                if row:
                    record[f"realize{target:.2f}@{packs}"] = _f(row.get("estimate"))
        for tolerance in CONVERGENCE_TOLERANCES:
            for packs in CURVE_POINTS_OF_INTEREST:
                row = curve_index.get((run_id, f"within_tau_{tolerance:.2f}", packs))
                if row:
                    record[f"within{tolerance:.2f}@{packs}"] = _f(row.get("estimate"))

        clt = summary.get("clt_comparison_json") or {}
        ratios = clt.get("empiricalOverCltRatio", {})
        record["cltRatioR80C80"] = _f(ratios.get("realization_ge_0.80|0.80"))
        record["cltRatioTau20C80"] = _f(ratios.get("within_tau_0.20|0.80"))
        horizons = clt.get("horizons", {})
        record["cltHorizonR80C80"] = _f(
            (horizons.get("realization", {}).get("0.80", {}).get("0.80", {}) or {}).get("requiredN")
        )
        record["cltHorizonTau20C80"] = _f(
            (horizons.get("convergence", {}).get("0.20", {}).get("0.80", {}) or {}).get("requiredN")
        )

        frame.append(record)
    return frame


# ---------------------------------------------------------------------------
# Correlations
# ---------------------------------------------------------------------------

def correlate(
    frame: Sequence[Mapping[str, Any]], x_key: str, y_key: str, *, label: str
) -> Dict[str, Any]:
    xs, ys = paired(frame, x_key, y_key)
    n = len(xs)
    if n < 4:
        return {"label": label, "x": x_key, "y": y_key, "n": n, "insufficient": True}
    result: Dict[str, Any] = {
        "label": label,
        "x": x_key,
        "y": y_key,
        "n": n,
        "pearson": pearson(xs, ys),
        "spearman": spearman(xs, ys),
    }
    ci = bootstrap_correlation_ci(xs, ys, draws=BOOTSTRAP_DRAWS, seed=SEED, method="spearman")
    result["spearmanCiLow"] = ci.get("ciLow")
    result["spearmanCiHigh"] = ci.get("ciHigh")
    result["spearmanCiIncludesZero"] = ci.get("includesZero")
    perm = permutation_p_value(xs, ys, draws=PERMUTATION_DRAWS, seed=SEED, method="spearman")
    result["pValue"] = perm.get("pValue")
    return result


def apply_bh(results: List[Dict[str, Any]]) -> None:
    """BH-adjust p-values IN PLACE, within one hypothesis family.

    Within-family rather than across the whole report: the families ask
    different questions, and pooling them would penalise a well-powered
    two-comparison family for the size of an exploratory thirty-comparison one.
    """
    usable = [item for item in results if not item.get("insufficient")]
    adjusted = benjamini_hochberg([item.get("pValue") for item in usable])
    for item, value in zip(usable, adjusted):
        item["pValueAdjusted"] = value


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def fmt(value: Any, spec: str = ".3f", *, dash: str = "-") -> str:
    if value is None:
        return dash
    if isinstance(value, bool):
        return "yes" if value else "no"
    try:
        return format(float(value), spec)
    except (TypeError, ValueError):
        return str(value)


def pct(value: Any, spec: str = ".1f") -> str:
    return "-" if value is None else f"{float(value) * 100:{spec}}%"


def table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    out = ["| " + " | ".join(headers) + " |",
           "|" + "|".join("---" for _ in headers) + "|"]
    out.extend("| " + " | ".join(str(cell) for cell in row) + " |" for row in rows)
    return "\n".join(out)


def correlation_table(results: Sequence[Mapping[str, Any]]) -> str:
    rows = []
    for item in results:
        if item.get("insufficient"):
            rows.append([item["label"], str(item["n"]), "-", "-", "-", "-", "insufficient n"])
            continue
        ci = f"[{fmt(item.get('spearmanCiLow'))}, {fmt(item.get('spearmanCiHigh'))}]"
        verdict = _verdict(item)
        rows.append([
            item["label"], str(item["n"]), fmt(item.get("pearson")), fmt(item.get("spearman")),
            ci, fmt(item.get("pValueAdjusted"), ".4f"), verdict,
        ])
    return table(
        ["Relationship", "n", "Pearson", "Spearman", "Spearman 95% CI", "BH p", "Verdict"], rows
    )


def _verdict(item: Mapping[str, Any]) -> str:
    p = item.get("pValueAdjusted")
    includes_zero = item.get("spearmanCiIncludesZero")
    rho = item.get("spearman")
    if p is None or rho is None:
        return "undetermined"
    if p < 0.05 and not includes_zero:
        strength = "strong" if abs(rho) >= 0.7 else ("moderate" if abs(rho) >= 0.4 else "weak")
        return f"supported ({strength})"
    if includes_zero:
        return "not supported (CI spans 0)"
    return "not significant after BH"


def _sorted_by(frame: Sequence[Mapping[str, Any]], key: str, *, reverse: bool = True,
               require: bool = True) -> List[Mapping[str, Any]]:
    rows = [r for r in frame if r.get(key) is not None] if require else list(frame)
    return sorted(rows, key=lambda r: (r.get(key) is None, r.get(key)), reverse=reverse)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--market-date", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    client = create_service_role_client()
    dataset = load_dataset(client, market_date=args.market_date)
    frame = build_frame(dataset)

    # ---- CSV export (Part 38-D) ------------------------------------------
    columns: List[str] = []
    for record in frame:
        for key in record:
            if key not in columns:
                columns.append(key)
    csv_path = out_dir / f"ev_representativeness_set_level_{args.market_date}.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for record in frame:
            writer.writerow(record)

    analysis = run_hypotheses(frame)
    json_path = out_dir / f"ev_representativeness_analysis_{args.market_date}.json"
    json_path.write_text(
        json.dumps(
            {
                "marketDate": args.market_date,
                "researchMethodVersion": EV_REPRESENTATIVENESS_VERSION,
                "generatedAt": datetime.now(timezone.utc).isoformat(),
                "setCount": len(frame),
                "frame": frame,
                "analysis": analysis,
            },
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )

    report = render_report(dataset, frame, analysis)
    md_path = out_dir / f"EV_REPRESENTATIVENESS_RESEARCH_REPORT_{args.market_date}.md"
    md_path.write_text(report, encoding="utf-8")

    print(f"wrote {csv_path}")
    print(f"wrote {json_path}")
    print(f"wrote {md_path}")
    return 0


# ---------------------------------------------------------------------------
# Hypotheses (Part 20)
# ---------------------------------------------------------------------------

def run_hypotheses(frame: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    families: Dict[str, List[Dict[str, Any]]] = {}

    families["H1_concentration"] = [
        correlate(frame, x, y, label=f"{x} vs {y}")
        for x in ("top1OutcomeShare", "top5OutcomeShare", "top10OutcomeShare",
                  "simCardHhi", "simTopCardShare", "simTop5CardShare", "simTop10CardShare")
        for y in ("typicalCapture", "gapCostNormalized", "horizonTau20C80", "horizonR80C80")
    ]
    families["H2_accessible_hits"] = [
        correlate(frame, x, y, label=f"{x} vs {y}")
        for x in ("hitProb__illustration_rare", "hitProb__special_illustration_rare",
                  "hitProb__any_premium", "econHit__1.00x", "econHit__0.50x", "econHit__2.00x")
        for y in ("typicalCapture", "horizonTau20C80")
    ]
    families["H3_rarity_structure"] = [
        correlate(frame, x, y, label=f"{x} vs {y}")
        for x in ("rarityShare__special_illustration_rare", "rarityShare__illustration_rare",
                  "rarityShare__hyper_rare", "rarityShare__double_rare")
        for y in ("typicalCapture", "horizonTau20C80")
    ]
    families["H5_financial_rip"] = [
        correlate(frame, "financialRipV3", y, label=f"financialRipV3 vs {y}")
        for y in ("typicalCapture", "gapCostNormalized", "horizonTau20C80", "horizonR80C80",
                  "top1OutcomeShare", "simCardHhi", "realize0.80@36", "within0.20@36", "cv")
    ]
    families["predictor_ranking"] = [
        correlate(frame, x, "horizonTau20C80", label=f"{x} vs convergence horizon")
        for x in ("cv", "top1OutcomeShare", "top5OutcomeShare", "top10OutcomeShare",
                  "simCardHhi", "gmSkew", "pearsonSkew2", "typicalCapture",
                  "hitProb__any_premium", "econHit__1.00x", "simEffectiveCardCount")
    ]
    for results in families.values():
        apply_bh(results)
    return families


def render_report(
    dataset: Mapping[str, Any], frame: Sequence[Mapping[str, Any]], analysis: Mapping[str, Any]
) -> str:
    from backend.research.ev_representativeness.report_sections import build_report

    return build_report(dataset, frame, analysis)


if __name__ == "__main__":
    sys.exit(main())
