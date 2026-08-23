"""Generate the preliminary temporal-stability study from V1 history CSV."""

from __future__ import annotations

import argparse
import math
from pathlib import Path
from typing import Optional, Sequence

import pandas as pd

METRICS = [
    "typical_capture", "top1_outcome_ev_share", "horizon_r80_c80_stable",
    "horizon_tau20_c80_stable", "coefficient_of_variation",
]


def _pct(value) -> str:
    return "—" if pd.isna(value) else f"{100 * float(value):.2f}%"


def _num(value, digits=3) -> str:
    return "—" if pd.isna(value) else f"{float(value):.{digits}f}"


def _table(headers, rows) -> str:
    return "\n".join(["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|",
                      *("| " + " | ".join(map(str, row)) + " |" for row in rows)])


def build_report(frame: pd.DataFrame) -> str:
    frame = frame.copy(); frame["market_date"] = pd.to_datetime(frame["market_date"])
    # Retained candidates from a failed independent confirmation are audit
    # evidence, not stable horizons. Exclude them from temporal rankings/deltas.
    frame.loc[frame["horizon_r80_c80_status"] != "resolved", "horizon_r80_c80_stable"] = math.nan
    frame.loc[frame["horizon_tau20_c80_status"] != "resolved", "horizon_tau20_c80_stable"] = math.nan
    dates = sorted(frame.market_date.dropna().unique())
    complete = frame.groupby("market_date").set_canonical_key.nunique()
    baseline = dates[0] if dates else None
    rank_rows = []
    for metric in METRICS:
        pivot = frame.pivot(index="set_canonical_key", columns="market_date", values=metric)
        base = pivot[baseline].rank() if baseline in pivot else None
        for previous, current in zip(dates, dates[1:]):
            pair = pivot[[previous, current]].dropna()
            rho = pair[previous].rank().corr(pair[current].rank(), method="pearson") if len(pair) >= 4 else math.nan
            base_pair = pd.concat([base, pivot[current].rank()], axis=1).dropna() if base is not None else pd.DataFrame()
            base_rho = base_pair.iloc[:, 0].corr(base_pair.iloc[:, 1]) if len(base_pair) >= 4 else math.nan
            displacement = (pair[previous].rank() - pair[current].rank()).abs()
            rank_rows.append([metric, str(previous)[:10] + "→" + str(current)[:10], len(pair), _num(rho), _num(base_rho), _num(displacement.median(), 1), _num(displacement.max(), 1)])

    stability_rows = []
    for set_key, group in frame.groupby("set_canonical_key"):
        ordered = group.sort_values("market_date")
        for metric in ("typical_capture", "top1_outcome_ev_share", "horizon_r80_c80_stable", "horizon_tau20_c80_stable"):
            values = ordered[metric].dropna()
            changes = ordered[metric].diff().abs().dropna()
            stability_rows.append({"set": set_key, "metric": metric, "min": values.min(), "max": values.max(),
                                   "mean": values.mean(), "median": values.median(), "std": values.std(ddof=1),
                                   "cv": values.std(ddof=1) / abs(values.mean()) if len(values) > 1 and values.mean() else math.nan,
                                   "median_change": changes.median(), "p95_change": changes.quantile(.95) if len(changes) else math.nan})
    stability = pd.DataFrame(stability_rows)
    top_stability = stability[stability.metric == "typical_capture"].sort_values("cv")

    deltas = []
    for _, group in frame.groupby("set_canonical_key"):
        ordered = group.sort_values("market_date").copy()
        for column in ["ev", "pack_cost", "typical_capture", "top1_outcome_ev_share", "horizon_r80_c80_stable", "horizon_tau20_c80_stable"]:
            ordered["d_" + column] = ordered[column].diff()
        deltas.append(ordered.iloc[1:])
    delta = pd.concat(deltas, ignore_index=True) if deltas else pd.DataFrame()
    relationship_rows = []
    for x in ("d_ev", "d_pack_cost", "d_top1_outcome_ev_share"):
        for y in ("d_typical_capture", "d_top1_outcome_ev_share", "d_horizon_r80_c80_stable", "d_horizon_tau20_c80_stable"):
            if x == y: continue
            pair = delta[[x, y]].dropna()
            relationship_rows.append([x, y, len(pair), _num(pair[x].corr(pair[y], method="pearson")), _num(pair[x].corr(pair[y], method="spearman"))])

    distributed = delta[(delta.d_ev > 0) & (delta.d_top1_outcome_ev_share <= 0.01) &
                        (delta.d_typical_capture > 0) & (delta.d_horizon_tau20_c80_stable < 0)] if len(delta) else delta
    lines = [
        "# Temporal Stability of EV Representativeness", "",
        f"Method version: **ev_representativeness_v1**  ",
        f"Coverage: **{len(dates)} complete market dates**, **{len(frame)} observations**, **{frame.set_canonical_key.nunique()} sets**  ",
        f"Dates: **{str(dates[0])[:10]} through {str(dates[-1])[:10]}**" if dates else "Dates: none", "",
        "## Scope and interpretation", "",
        "This is a preliminary longitudinal baseline built only from exact historical one-million-pack artifacts and their frozen same-run prices. Four dates provide useful first evidence but not enough duration to establish long-term stability or seasonality. No V1/V2 series are spliced.", "",
        "The persisted headline `firstCrossingN` is a **coarse-grid first crossing**. The stable headline is independently refined and confirmed. Public projections use only a refined stable horizon whose status is `resolved`; an audit candidate retained after `confirmation_did_not_ratify` is not public.", "",
        "## Coverage", "",
        _table(["Date", "Sets"], [[str(day)[:10], int(count)] for day, count in complete.items()]), "",
        "## T1 — Rank stability", "",
        _table(["Metric", "Interval", "n", "Day/day Spearman", "Vs baseline", "Median rank move", "Max move"], rank_rows), "",
        "## T2 — Absolute metric stability", "",
        "Typical Capture stability extremes (coefficient of variation across available dates):", "",
        _table(["Set", "Min", "Max", "CV", "Median daily |Δ|", "P95 daily |Δ|"],
               [[row.set, _pct(row["min"]), _pct(row["max"]), _num(row.cv), _pct(row.median_change), _pct(row.p95_change)] for _, row in pd.concat([top_stability.head(5), top_stability.tail(5)]).iterrows()]), "",
        "The complete per-set descriptive statistics remain reproducible from `ev_representativeness_history.csv`.", "",
        "## T3–T5 — Market changes and representativeness", "",
        _table(["Δ predictor", "Δ outcome", "n transitions", "Pearson", "Spearman"], relationship_rows), "",
        "Pack-cost changes are analyzed separately from EV/card-distribution changes. Tier A top-1% outcome share is used for chase concentration; no historical card identity is inferred.", "",
        "## T6 — Distributed appreciation candidates", "",
        (_table(["Set", "Date", "ΔEV", "Δ Typical Capture", "Δ Top-1%", "Δ convergence"],
                [[row.set_canonical_key, str(row.market_date)[:10], _num(row.d_ev), _pct(row.d_typical_capture), _pct(row.d_top1_outcome_ev_share), _num(row.d_horizon_tau20_c80_stable, 0)] for _, row in distributed.iterrows()])
         if len(distributed) else "No interval met all strict distributed-appreciation criteria in this four-date baseline."), "",
        "## T7 — Threshold stability", "",
        "V1 preserves realization targets 75%, 80%, and 90%, opener confidence levels 75%, 80%, and 90%, and convergence tolerances ±20% and ±25% in the research curves/horizon JSON. A larger temporal window is required before threshold-induced rank changes can justify a public score. The 80/80 and ±20%/80% choices remain descriptive parameters, not optimized weights.", "",
        "## Forward baseline", "",
        f"Continuous automatic Tier A collection begins with the deployment following {str(dates[-1])[:10] if dates else 'this report'}. Historical backfill covers all exact artifacts currently present. Missing calendar dates reflect absent artifacts and are not reconstructed from current prices.", "",
        "Recommendation: display current-run metrics descriptively in the Full Simulation Report, keep them below Overall RIP, and collect at least 60–90 daily observations spanning multiple market regimes before considering a headline horizon, Financial RIP change, or new score.", "",
    ]
    return "\n".join(lines)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("--history", required=True); parser.add_argument("--out", required=True)
    args = parser.parse_args(argv); frame = pd.read_csv(args.history)
    path = Path(args.out); path.parent.mkdir(parents=True, exist_ok=True); path.write_text(build_report(frame), encoding="utf-8")
    print(f"wrote {path}"); return 0


if __name__ == "__main__":
    raise SystemExit(main())
