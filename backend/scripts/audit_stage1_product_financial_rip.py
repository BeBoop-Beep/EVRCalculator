"""Is Financial RIP V3 still meaningful when applied to 6- and 36-pack products?

THE QUESTION
------------
V3's normalization anchors are FIXED and were calibrated on PACK-level
distributions: P(pack value >= pack cost), P50/cost, Q95/cost, the 95th-99th pack
tail, the top-1% pack tail. Stage 1 hands those same absolute anchors a 6-pack
and a 36-pack distribution. That is mechanically valid - V3 is defined for any
outcome vector and cost - but "mechanically valid" is not "meaningful".

Summing k i.i.d. draws concentrates the distribution: relative dispersion falls
roughly as 1/sqrt(k). So as pack count rises, the ratio metrics V3 scores
(P50/C, Q95/C, tail/C) all migrate toward the SAME central value, the mean/cost
ratio. If that migration pushes whole metrics past their fixed knots, products
stop being distinguished by their economics and start being ordered by their
pack count. This script measures whether that is happening.

It reads the persisted `financial_rip_v3_payload`, which already carries every
raw input, every normalization record (score, transform, clip status and
direction) and every component score/contribution. No Y vectors are needed.

    python backend/scripts/audit_stage1_product_financial_rip.py
    python backend/scripts/audit_stage1_product_financial_rip.py --source file --input tmp/rows.json
"""

from __future__ import annotations

import argparse
import json
import logging
import statistics
from typing import Any, Dict, Iterable, List, Optional, Sequence

from backend.calculations.evr.financial_rip_v3_config import (
    FINANCIAL_RIP_V3_COMPONENT_INPUTS,
    FINANCIAL_RIP_V3_COMPONENT_ORDER,
    FINANCIAL_RIP_V3_NORMALIZATION_VERSION,
    FINANCIAL_RIP_V3_VERSION,
    FINANCIAL_RIP_V3_WEIGHTS,
)
from backend.domain.pokemon.sealed_product_composition import (
    STAGE1_COMPOSITION_VERSION,
    SUPPORTED_STAGE1_FAMILIES,
)

logger = logging.getLogger(__name__)

FAMILY_ORDER = ("sleeved_booster_pack", "booster_bundle", "booster_box")

#: Raw V3 inputs, in the order a reader thinks about them.
RAW_METRICS = [
    metric
    for component in FINANCIAL_RIP_V3_COMPONENT_ORDER
    for metric in FINANCIAL_RIP_V3_COMPONENT_INPUTS[component]
]


# ---------------------------------------------------------------------------
# Small statistics helpers (no new scoring, no new formulas)
# ---------------------------------------------------------------------------

def _percentile(values: Sequence[float], q: float) -> Optional[float]:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    position = (len(ordered) - 1) * (q / 100.0)
    low = int(position)
    high = min(low + 1, len(ordered) - 1)
    weight = position - low
    return float(ordered[low] * (1.0 - weight) + ordered[high] * weight)


def _spread(values: Sequence[float]) -> Dict[str, Any]:
    clean = [float(v) for v in values if v is not None]
    if not clean:
        return {"n": 0, "min": None, "p25": None, "median": None, "p75": None, "max": None, "mean": None, "iqr": None, "range": None}
    return {
        "n": len(clean),
        "min": round(min(clean), 6),
        "p25": round(_percentile(clean, 25), 6),
        "median": round(_percentile(clean, 50), 6),
        "p75": round(_percentile(clean, 75), 6),
        "max": round(max(clean), 6),
        "mean": round(statistics.fmean(clean), 6),
        "iqr": round(_percentile(clean, 75) - _percentile(clean, 25), 6),
        "range": round(max(clean) - min(clean), 6),
    }


# ---------------------------------------------------------------------------
# Row loading
# ---------------------------------------------------------------------------

def load_rows_from_db() -> List[Dict[str, Any]]:
    """Latest persisted Stage 1 rows, one run per set."""
    from backend.db.clients.supabase_client import supabase

    response = (
        supabase.table("simulation_sealed_product_results")
        .select(
            "set_id,calculation_run_id,product_family,product_name,pack_count,"
            "product_market_cost,financial_rip_v3_score,financial_rip_v3_status,"
            "financial_rip_v3_payload,created_at"
        )
        .order("created_at", desc=True)
        .execute()
    )
    rows = list(response.data or [])
    newest_run_by_set: Dict[str, str] = {}
    for row in rows:  # already newest-first
        newest_run_by_set.setdefault(str(row["set_id"]), str(row["calculation_run_id"]))
    return [row for row in rows if str(row["calculation_run_id"]) == newest_run_by_set[str(row["set_id"])]]


def load_rows_from_file(path: str) -> List[Dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as handle:
        document = json.load(handle)
    rows: List[Dict[str, Any]] = []
    for entry in document.get("sets") or []:
        for row in entry.get("rows") or []:
            rows.append({**row, "canonical_key": entry.get("canonicalKey")})
    return rows


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------

def _payload(row: Dict[str, Any]) -> Dict[str, Any]:
    payload = row.get("financial_rip_v3_payload")
    return payload if isinstance(payload, dict) else {}


def analyze_family(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    payloads = [_payload(row) for row in rows]
    ready = [payload for payload in payloads if payload.get("status") == "ready"]

    raw_stats: Dict[str, Any] = {}
    normalized_stats: Dict[str, Any] = {}
    clipping: Dict[str, Any] = {}
    for metric in RAW_METRICS:
        records = [(payload.get("audit") or {}).get("normalizedInputs", {}).get(metric, {}) for payload in ready]
        records = [record for record in records if isinstance(record, dict)]
        raw_stats[metric] = _spread([record.get("raw") for record in records if record.get("raw") is not None])
        normalized_stats[metric] = _spread([record.get("score") for record in records if record.get("score") is not None])
        total = len(records) or 1
        lower = sum(1 for record in records if record.get("clippedAt") == "lower")
        upper = sum(1 for record in records if record.get("clippedAt") == "upper")
        clipping[metric] = {
            "n": len(records),
            "clippedLowerPct": round(100.0 * lower / total, 2),
            "clippedUpperPct": round(100.0 * upper / total, 2),
            "clippedAnyPct": round(100.0 * (lower + upper) / total, 2),
        }

    components: Dict[str, Any] = {}
    for component in FINANCIAL_RIP_V3_COMPONENT_ORDER:
        blocks = [(payload.get("components") or {}).get(component, {}) for payload in ready]
        blocks = [block for block in blocks if isinstance(block, dict)]
        components[component] = {
            "weight": FINANCIAL_RIP_V3_WEIGHTS[component],
            "score": _spread([block.get("score") for block in blocks if block.get("score") is not None]),
            "contribution": _spread([block.get("contribution") for block in blocks if block.get("contribution") is not None]),
        }

    scores = [row.get("financial_rip_v3_score") for row in rows if row.get("financial_rip_v3_score") is not None]
    return {
        "productCount": len(rows),
        "setCount": len({str(row.get("set_id") or row.get("canonical_key")) for row in rows}),
        "readyCount": len(ready),
        "packCounts": sorted({int(row["pack_count"]) for row in rows if row.get("pack_count")}),
        "financialRipScore": _spread(scores),
        "productMarketCost": _spread([row.get("product_market_cost") for row in rows]),
        "rawInputs": raw_stats,
        "normalizedInputs": normalized_stats,
        "clipping": clipping,
        "components": components,
    }


def cross_family_diagnostics(by_family: Dict[str, Any]) -> Dict[str, Any]:
    """The questions that only make sense by COMPARING 1 / 6 / 36."""
    present = [family for family in FAMILY_ORDER if by_family.get(family, {}).get("readyCount")]

    def _series(family: str, path: Sequence[str]) -> Any:
        node: Any = by_family[family]
        for key in path:
            node = (node or {}).get(key, {})
        return node

    compression = {
        family: {
            "scoreIqr": _series(family, ("financialRipScore",)).get("iqr"),
            "scoreRange": _series(family, ("financialRipScore",)).get("range"),
            "scoreMedian": _series(family, ("financialRipScore",)).get("median"),
        }
        for family in present
    }

    # Does a component stop separating products as pack count rises? A component
    # whose within-family IQR collapses to ~0 is no longer ordering anything.
    component_separation = {
        component: {
            family: _series(family, ("components", component, "score")).get("iqr")
            for family in present
        }
        for component in FINANCIAL_RIP_V3_COMPONENT_ORDER
    }

    # Which component's CONTRIBUTION varies most within each family? That is the
    # component actually driving the ordering there.
    dominant_component = {}
    for family in present:
        spreads = {
            component: (_series(family, ("components", component, "contribution")).get("iqr") or 0.0)
            for component in FINANCIAL_RIP_V3_COMPONENT_ORDER
        }
        total = sum(spreads.values()) or 1.0
        ranked = sorted(spreads.items(), key=lambda item: item[1], reverse=True)
        dominant_component[family] = {
            "ranked": [{"component": c, "contributionIqr": round(v, 4), "shareOfSpread": round(100.0 * v / total, 2)} for c, v in ranked],
            "top": ranked[0][0],
            "topShareOfSpreadPct": round(100.0 * ranked[0][1] / total, 2),
        }

    clip_pressure = {
        family: {
            metric: by_family[family]["clipping"][metric]
            for metric in RAW_METRICS
            if by_family[family]["clipping"][metric]["clippedAnyPct"] > 0
        }
        for family in present
    }

    # The mechanical prediction: relative dispersion of the OUTCOME ratios should
    # narrow as k rises. Tracked on the two tail ratios V3 scores most heavily.
    tail_convergence = {
        family: {
            "p95ThresholdRatioMedian": _series(family, ("rawInputs", "p95_threshold_ratio")).get("median"),
            "realisticTailMeanRatioMedian": _series(family, ("rawInputs", "realistic_tail_mean_ratio")).get("median"),
            "p99ThresholdRatioMedian": _series(family, ("rawInputs", "p99_threshold_ratio")).get("median"),
            "jackpotTailMeanRatioMedian": _series(family, ("rawInputs", "jackpot_tail_mean_ratio")).get("median"),
            "typicalRetentionRatioMedian": _series(family, ("rawInputs", "typical_retention_ratio")).get("median"),
            "trueWinProbabilityMedian": _series(family, ("rawInputs", "true_win_probability")).get("median"),
            "baseRtpExcludingTop1PctMedian": _series(family, ("rawInputs", "base_rtp_excluding_top_1pct")).get("median"),
        }
        for family in present
    }

    return {
        "familiesPresent": present,
        "scoreCompression": compression,
        "componentSeparationIqr": component_separation,
        "dominantComponentBySpread": dominant_component,
        "clipPressure": clip_pressure,
        "rawRatioMediansByFamily": tail_convergence,
    }


def build_report(rows: List[Dict[str, Any]], *, source: str) -> Dict[str, Any]:
    supported = [row for row in rows if str(row.get("product_family")) in SUPPORTED_STAGE1_FAMILIES]
    by_family = {
        family: analyze_family([row for row in supported if str(row.get("product_family")) == family])
        for family in FAMILY_ORDER
        if any(str(row.get("product_family")) == family for row in supported)
    }
    return {
        "source": source,
        "financialRipV3Version": FINANCIAL_RIP_V3_VERSION,
        "normalizationVersion": FINANCIAL_RIP_V3_NORMALIZATION_VERSION,
        "compositionVersion": STAGE1_COMPOSITION_VERSION,
        "rowCount": len(supported),
        "byFamily": by_family,
        "crossFamily": cross_family_diagnostics(by_family),
    }


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def _fmt(value: Any) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:,.4f}".rstrip("0").rstrip(".") if abs(value) < 1000 else f"{value:,.2f}"
    return str(value)


def _spread_row(label: str, spread: Dict[str, Any]) -> str:
    keys = ("min", "p25", "median", "p75", "max", "mean")
    return "| " + label + " | " + " | ".join(_fmt(spread.get(key)) for key in keys) + " |"


def render_markdown(report: Dict[str, Any]) -> str:
    lines: List[str] = []
    add = lines.append
    add("# Stage 1 product-scope validation of Financial RIP V3")
    add("")
    add(f"- Financial RIP version: `{report['financialRipV3Version']}`")
    add(f"- Normalization version: `{report['normalizationVersion']}`")
    add(f"- Composition contract: `{report['compositionVersion']}`")
    add(f"- Row source: `{report['source']}`")
    add(f"- Product rows analyzed: **{report['rowCount']}**")
    add("")
    add("## Question")
    add("")
    add(
        "Financial RIP V3's anchors are absolute and pack-calibrated. This report asks "
        "whether the same scale still distinguishes good from bad products WITHIN and "
        "ACROSS 1-, 6- and 36-pack opening units, or whether pack count itself has "
        "become the dominant signal."
    )
    add("")

    for family in FAMILY_ORDER:
        block = report["byFamily"].get(family)
        if not block:
            continue
        add(f"## {family} ({', '.join(str(c) for c in block['packCounts'])} pack(s))")
        add("")
        add(f"- products: **{block['productCount']}** across **{block['setCount']}** sets ({block['readyCount']} scored `ready`)")
        add("")
        add("| statistic | min | p25 | median | p75 | max | mean |")
        add("|---|---|---|---|---|---|---|")
        add(_spread_row("**Financial RIP score**", block["financialRipScore"]))
        add(_spread_row("product market cost", block["productMarketCost"]))
        add("")
        add("### Raw V3 inputs")
        add("")
        add("| raw input | min | p25 | median | p75 | max | mean |")
        add("|---|---|---|---|---|---|---|")
        for metric in RAW_METRICS:
            add(_spread_row(f"`{metric}`", block["rawInputs"][metric]))
        add("")
        add("### Normalized scores and clipping")
        add("")
        add("| input | norm min | norm p25 | norm median | norm p75 | norm max | norm mean | clipped low % | clipped high % |")
        add("|---|---|---|---|---|---|---|---|---|")
        for metric in RAW_METRICS:
            spread = block["normalizedInputs"][metric]
            clip = block["clipping"][metric]
            add(
                f"| `{metric}` | "
                + " | ".join(_fmt(spread.get(key)) for key in ("min", "p25", "median", "p75", "max", "mean"))
                + f" | {clip['clippedLowerPct']} | {clip['clippedUpperPct']} |"
            )
        add("")
        add("### Components")
        add("")
        add("| component | weight | score median | score IQR | contribution median | contribution IQR |")
        add("|---|---|---|---|---|---|")
        for component in FINANCIAL_RIP_V3_COMPONENT_ORDER:
            info = block["components"][component]
            add(
                f"| {component} | {info['weight']} | {_fmt(info['score'].get('median'))} | "
                f"{_fmt(info['score'].get('iqr'))} | {_fmt(info['contribution'].get('median'))} | "
                f"{_fmt(info['contribution'].get('iqr'))} |"
            )
        add("")

    cross = report["crossFamily"]
    add("## Cross-family comparison")
    add("")
    add("### Score compression")
    add("")
    add("| family | score median | score IQR | score range |")
    add("|---|---|---|---|")
    for family, info in cross["scoreCompression"].items():
        add(f"| {family} | {_fmt(info['scoreMedian'])} | {_fmt(info['scoreIqr'])} | {_fmt(info['scoreRange'])} |")
    add("")
    add("### Raw ratio medians by family (the mechanical concentration check)")
    add("")
    metrics = sorted({key for info in cross["rawRatioMediansByFamily"].values() for key in info})
    add("| metric | " + " | ".join(cross["familiesPresent"]) + " |")
    add("|---" * (len(cross["familiesPresent"]) + 1) + "|")
    for metric in metrics:
        add(
            f"| {metric} | "
            + " | ".join(_fmt(cross["rawRatioMediansByFamily"][family].get(metric)) for family in cross["familiesPresent"])
            + " |"
        )
    add("")
    add("### Component separation (within-family score IQR)")
    add("")
    add("A component whose IQR is ~0 inside a family is no longer distinguishing products there.")
    add("")
    add("| component | " + " | ".join(cross["familiesPresent"]) + " |")
    add("|---" * (len(cross["familiesPresent"]) + 1) + "|")
    for component, info in cross["componentSeparationIqr"].items():
        add(f"| {component} | " + " | ".join(_fmt(info.get(family)) for family in cross["familiesPresent"]) + " |")
    add("")
    add("### What actually orders products inside each family")
    add("")
    for family, info in cross["dominantComponentBySpread"].items():
        top = ", ".join(
            f"{entry['component']} ({entry['shareOfSpread']}%)" for entry in info["ranked"][:3]
        )
        add(f"- **{family}**: {top}")
    add("")
    add("### Clip pressure (inputs pinned at a transform bound)")
    add("")
    for family, metrics_map in cross["clipPressure"].items():
        if not metrics_map:
            add(f"- **{family}**: no clipped inputs")
            continue
        detail = ", ".join(
            f"`{metric}` low {info['clippedLowerPct']}% / high {info['clippedUpperPct']}%"
            for metric, info in metrics_map.items()
        )
        add(f"- **{family}**: {detail}")
    add("")
    return "\n".join(lines)


def main() -> int:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", choices=("db", "file"), default="db")
    parser.add_argument("--input", default="tmp/stage1_dry_run_rows.json", help="Row dump when --source file.")
    parser.add_argument("--markdown", default="docs/research/stage1_product_financial_rip_validation_data.md")
    parser.add_argument("--json", default="docs/research/stage1_product_financial_rip_validation.json")
    args = parser.parse_args()

    rows = load_rows_from_db() if args.source == "db" else load_rows_from_file(args.input)
    if not rows:
        print(
            "No Stage 1 product rows found. `simulation_sealed_product_results` is empty "
            "until an EVR run persists to it; use --source file with a dry-run dump."
        )
        return 1

    report = build_report(rows, source=args.source)
    with open(args.json, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)
    markdown = render_markdown(report)
    with open(args.markdown, "w", encoding="utf-8") as handle:
        handle.write(markdown)

    print(markdown)
    print(f"\nWrote {args.markdown} and {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
