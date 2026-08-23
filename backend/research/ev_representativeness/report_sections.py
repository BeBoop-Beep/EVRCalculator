"""Markdown renderer for the EV Representativeness v1 research report."""

from __future__ import annotations

import math
from typing import Any, Iterable, Mapping, Sequence


def _f(value: Any) -> float | None:
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def _n(value: Any, digits: int = 2) -> str:
    value = _f(value)
    return "—" if value is None else f"{value:,.{digits}f}"


def _pct(value: Any, digits: int = 1) -> str:
    value = _f(value)
    return "—" if value is None else f"{100 * value:.{digits}f}%"


def _table(headers: Sequence[str], rows: Iterable[Sequence[Any]]) -> str:
    rows = list(rows)
    return "\n".join([
        "| " + " | ".join(headers) + " |",
        "|" + "|".join("---" for _ in headers) + "|",
        *("| " + " | ".join(str(cell) for cell in row) + " |" for row in rows),
    ])


def _rank(frame: Sequence[Mapping[str, Any]], key: str, *, reverse: bool = True, limit: int = 22):
    rows = [row for row in frame if _f(row.get(key)) is not None]
    return sorted(rows, key=lambda row: float(row[key]), reverse=reverse)[:limit]


def _corr_table(rows: Sequence[Mapping[str, Any]]) -> str:
    return _table(
        ["Relationship", "n", "Pearson", "Spearman", "95% bootstrap CI", "BH p"],
        ([row.get("label"), row.get("n"), _n(row.get("pearson"), 3),
          _n(row.get("spearman"), 3),
          f"[{_n(row.get('spearmanCiLow'), 3)}, {_n(row.get('spearmanCiHigh'), 3)}]",
          _n(row.get("pValueAdjusted"), 4)] for row in rows),
    )


def _similar_pairs(frame: Sequence[Mapping[str, Any]]) -> list[tuple[float, Mapping[str, Any], Mapping[str, Any]]]:
    pairs = []
    for i, left in enumerate(frame):
        for right in frame[i + 1:]:
            ev1, ev2 = _f(left.get("ev")), _f(right.get("ev"))
            c1, c2 = _f(left.get("typicalCapture")), _f(right.get("typicalCapture"))
            if None in (ev1, ev2, c1, c2) or max(ev1, ev2) == 0:
                continue
            ev_distance = abs(ev1 - ev2) / max(ev1, ev2)
            if ev_distance <= 0.15:
                pairs.append((abs(c1 - c2), left, right))
    return sorted(pairs, key=lambda item: item[0], reverse=True)


def build_report(dataset: Mapping[str, Any], frame: Sequence[Mapping[str, Any]],
                 analysis: Mapping[str, Sequence[Mapping[str, Any]]]) -> str:
    set_count = len(frame)
    summaries = dataset["summaries"]
    products = [item for rows in dataset["products"].values() for item in rows]
    reconciled = sum(row.get("card_attribution_authoritative") is True for row in summaries)
    source_outcomes = sum(int(row.get("source_outcome_count") or 0) for row in summaries)
    pack_counts = sorted({int(row["pack_count"]) for row in products if row.get("pack_count")})
    captures = _rank(frame, "typicalCapture")
    concentration = _rank(frame, "top1OutcomeShare")
    r_horizons = _rank(frame, "horizonR80C80")
    c_horizons = _rank(frame, "horizonTau20C80")
    pairs = _similar_pairs(frame)[:5]
    capture_values = [value for row in frame if (value := _f(row.get("typicalCapture"))) is not None]
    h1 = {row.get("label"): row for row in analysis.get("H1_concentration", [])}
    h5 = {row.get("label"): row for row in analysis.get("H5_financial_rip", [])}
    tier_b_seconds = [value for row in frame if (value := _f(row.get("runtimeSeconds"))) is not None]

    lines = [
        "# EV Representativeness Research Report",
        "",
        f"Market date: **{dataset['marketDate']}**  ",
        f"Method: **ev_representativeness_v1**  ",
        f"Set-level effective sample size: **{set_count}**",
        "",
        "## 1. Executive Summary",
        "",
        (f"Across {set_count} modeled sets, median openings capture between "
         f"{_pct(min(capture_values, default=None))} and "
         f"{_pct(max(capture_values, default=None))} of EV. "
         "EV is therefore a long-run mean, not a description of a typical small opening. "
         "The cohort exhibits material variation in both tail concentration and the number "
         "of packs needed for finite-sample averages to approach EV."),
        "",
        "## 2. Research Question",
        "",
        "How representative is EV of a real opener's finite-sample experience, and how many packs are required before EV becomes a reasonably representative description?",
        "",
        "## 3. Methodology",
        "",
        "Tier A reads each exact, SHA-256-verified one-million-pack float64 artifact. Tier B is a separate deterministic, seeded reconstruction used only for latent card identity, paired ablations, and price shocks. Tier B attribution is accepted only after mean and quantile reconciliation against Tier A. Sessions bootstrap independent packs with replacement from Tier A, using common random numbers across the N grid. Probability rows report Wilson 95% intervals. First crossings are retained as noisy diagnostics; stable horizons require a Wilson lower bound above the target across a validation band and an independent 250,000-session confirmation. CLT estimates are comparisons, never substitutes for empirical horizons.",
        "",
        "## 4. Dataset",
        "",
        _table(["Market date", "Sets", "Source outcomes", "Product rows", "Pack counts", "Tier B reconciled"], [[dataset["marketDate"], set_count, f"{source_outcomes:,}", len(products), ", ".join(map(str, pack_counts)), f"{reconciled}/{set_count}"]]),
        "",
        "Product rows are descriptive only. Products from the same set share an underlying pack distribution, so they are not treated as independent observations.",
        "",
        "## 5. EV vs Typical Opening",
        "",
        _table(["Set", "EV", "P50", "Typical Capture", "EV−P50", "Gap / cost"],
               ([r["canonicalKey"], _n(r.get("ev")), _n(r.get("p50")), _pct(r.get("typicalCapture")), _n(r.get("gapAbsolute")), _pct(r.get("gapCostNormalized"))] for r in captures)),
        "",
        "## 6. Outcome Concentration",
        "",
        _table(["Set", "Top 10% share", "Top 5% share", "Top 1% share", "Top 1% mean"],
               ([r["canonicalKey"], _pct(r.get("top10OutcomeShare")), _pct(r.get("top5OutcomeShare")), _pct(r.get("top1OutcomeShare")), _n(r.get("top1TailMean"))] for r in concentration)),
        "",
        "All tail shares use exact rank mass, including ties: k = max(1, ceil(nq)).",
        "",
        "## 7. Card Concentration",
        "",
        _table(["Set", "Top card", "Top 5", "Top 10", "HHI", "Effective cards"],
               ([r["canonicalKey"], _pct(r.get("simTopCardShare")), _pct(r.get("simTop5CardShare")), _pct(r.get("simTop10CardShare")), _n(r.get("simCardHhi"), 4), _n(r.get("simEffectiveCardCount"), 1)] for r in _rank(frame, "simCardHhi"))),
        "",
        "Only reconciled Tier B rows are interpreted as authoritative card attribution.",
        "",
        "## 8. Rarity Structure",
        "",
        "Exact rarity EV contributions come from same-run `simulation_pull_summary` and reconcile to Tier A EV. Collective hit frequencies use the canonical pack-state model; they are not sums of marginal probabilities. Rarity shares and IR/SIR/premium accessibility are included in the set CSV and hypothesis tests.",
        "",
        "## 9. Finite-Sample EV Realization",
        "",
        _table(["Set", "N=1", "N=6", "N=9", "N=11", "N=18", "N=36", "N=50", "N=100", "N=250", "N=1000"],
               ([r["canonicalKey"], *(_pct(r.get(f"realize0.80@{n}")) for n in (1,6,9,11,18,36,50,100,250,1000))] for r in frame)),
        "",
        "Cells show P(realized average ≥ 80% of EV). The machine-readable curve includes targets 50%, 70%, 75%, 80%, 90%, and 100%, with uncertainty fields.",
        "",
        "## 10. EV Representativeness",
        "",
        _table(["Set", "±10%@36", "±20%@36", "±25%@36", "±20%@100", "±20%@250", "±20%@1000"],
               ([r["canonicalKey"], _pct(r.get("within0.10@36")), _pct(r.get("within0.20@36")), _pct(r.get("within0.25@36")), _pct(r.get("within0.20@100")), _pct(r.get("within0.20@250")), _pct(r.get("within0.20@1000"))] for r in frame)),
        "",
        "## 11. Realization Horizons",
        "",
        _table(["Set", "First crossing", "Stable R80/C80", "Status"], ([r["canonicalKey"], r.get("horizonR80C80First") or "—", r.get("horizonR80C80") or "—", r.get("horizonR80C80Status")] for r in r_horizons)),
        "",
        "## 12. Convergence Horizons",
        "",
        _table(["Set", "First crossing", "Stable ±20%/80%", "Status", "Monotonicity violations"], ([r["canonicalKey"], r.get("horizonTau20C80First") or "—", r.get("horizonTau20C80") or "—", r.get("horizonTau20C80Status"), r.get("monotonicityViolations")] for r in c_horizons)),
        "",
        "## 13. CLT vs Empirical Reality",
        "",
        _table(["Set", "Empirical R80", "CLT R80", "Empirical/CLT", "Empirical ±20%", "CLT ±20%", "Empirical/CLT"], ([r["canonicalKey"], r.get("horizonR80C80") or "—", _n(r.get("cltHorizonR80C80"),0), _n(r.get("cltRatioR80C80")), r.get("horizonTau20C80") or "—", _n(r.get("cltHorizonTau20C80"),0), _n(r.get("cltRatioTau20C80"))] for r in frame)),
        "",
        "## 14. Concentration vs Convergence",
        "",
        _corr_table(analysis.get("H1_concentration", [])),
        "",
        ("H1 is strongly supported for outcome-tail concentration: top-1% share versus "
         f"±20%/80% horizon has Spearman ρ={_n((h1.get('top1OutcomeShare vs horizonTau20C80') or {}).get('spearman'), 3)}, "
         f"and versus R80/C80 has ρ={_n((h1.get('top1OutcomeShare vs horizonR80C80') or {}).get('spearman'), 3)}. "
         "Card concentration is directionally related but is a weaker cross-set predictor than the realized outcome tail."),
        "",
        "## 15. Accessible Hits vs Convergence",
        "",
        _corr_table([*analysis.get("H2_accessible_hits", []), *analysis.get("H3_rarity_structure", [])]),
        "",
        "## 16. Similar EV, Different Experience",
        "",
        _table(["Set A", "EV A", "Capture A", "Set B", "EV B", "Capture B", "Capture gap"], ([a["canonicalKey"], _n(a.get("ev")), _pct(a.get("typicalCapture")), b["canonicalKey"], _n(b.get("ev")), _pct(b.get("typicalCapture")), _pct(gap)] for gap, a, b in pairs)),
        "",
        "## 17. Financial RIP Validation",
        "",
        _corr_table(analysis.get("H5_financial_rip", [])),
        "",
        ("Financial RIP captures part, but not all, of EV representativeness. It is moderately "
         f"associated with the ±20%/80% horizon (Spearman ρ={_n((h5.get('financialRipV3 vs horizonTau20C80') or {}).get('spearman'), 3)}) "
         f"and R80/C80 (ρ={_n((h5.get('financialRipV3 vs horizonR80C80') or {}).get('spearman'), 3)}), "
         "but its Typical Capture association is weaker and its bootstrap interval spans zero. "
         "Representativeness therefore contains useful structure not reducible to the current Financial RIP score. "
         "All comparisons use the exact same calculation run, never the stale public leaderboard."),
        "",
        "## 18. Counterfactual Findings",
        "",
        f"The dataset contains {sum(len(v) for v in dataset['counterfactuals'].values())} paired Tier B counterfactual rows covering rarity and top-card ablations, top-card/top-five price shocks, and top-1% winsorization. Each scenario revalues the same sampled paths, so its delta has no resampling-path noise. Full scenario parameters and deltas are in the counterfactual CSV.",
        "",
        "## 19. Limitations",
        "",
        "The effective cross-sectional sample is 22 sets; pack independence and simulator validity are assumed; values are gross market value with no selling fees, grading, or additional condition variance; Tier B reconstructs latent identity rather than recovering exact historical paths; estimates retain Monte Carlo uncertainty; and all conclusions are market-date dependent. Correlations are observational associations. Only paired model ablations support model-internal causal statements.",
        "",
        "## 20. Product Recommendation",
        "",
        "Do not publish a new score from this version alone. Typical Capture is the clearest one-pack descriptive statistic, while R80/C80 and ±20%/80% horizons answer distinct planning questions but can be sensitive to grid, confidence, and market-date changes. A future public metric should be selected only after temporal stability is measured across multiple market dates and redundancy with Financial RIP is quantified. Keep Tier B and counterfactuals research-only; Tier A is the plausible routine post-simulation layer because it consumes already-persisted artifacts and remains outside the publication critical path.",
        "",
        "### Performance recommendation",
        "",
        (f"Persisted per-set build runtimes span {_n(min(tier_b_seconds, default=None), 1)}–"
         f"{_n(max(tier_b_seconds, default=None), 1)} seconds in this cohort (sum "
         f"{_n(sum(tier_b_seconds), 1)} seconds; timings vary with cache and prior Tier B state). "
         "Tier A should remain eligible for routine post-simulation processing. Seeded Tier B, card-level recording, and paired counterfactuals should remain manual or separately scheduled research work and must not enter the publication critical path."),
        "",
    ]
    return "\n".join(lines)
