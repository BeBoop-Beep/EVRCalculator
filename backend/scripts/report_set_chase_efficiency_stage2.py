"""Read the Stage-II artifact and answer the study's questions.

RESEARCH ONLY. Pure reader over
``docs/research/set_chase_efficiency_stage2.json`` - no simulation, no database
read, so every table is reproducible from the artifact alone.

    python -m backend.scripts.report_set_chase_efficiency_stage2
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

#: The universe keys carried through every cross-set table.
HEADLINE_UNIVERSES = (
    "top_3", "top_5", "top_10",
    "gte_2x_cost", "gte_5x_cost", "gte_10x_cost", "gte_20x_cost",
    "largest_log_gap", "robust_zscore", "log_price_2means",
    "value_hhi_top_20", "ev_hhi_top_20", "value_hhi_top_25", "ev_hhi_top_25",
    "value_hhi_gte_1x_cost", "ev_hhi_gte_1x_cost",
    "value_hhi_gte_2x_cost", "ev_hhi_gte_2x_cost",
)

#: The universe the cross-set rankings are reported at. Chosen because it is the
#: only economically-interpretable rule that is supported by every set in the
#: cohort; the rankings section states this explicitly rather than implying the
#: choice is settled.
RANKING_UNIVERSE = "gte_2x_cost"


def spearman(a: Sequence[Optional[float]], b: Sequence[Optional[float]]) -> Optional[float]:
    pairs = [(x, y) for x, y in zip(a, b) if x is not None and y is not None]
    n = len(pairs)
    if n < 3:
        return None

    def ranks(values: Sequence[float]) -> List[float]:
        order = sorted(range(len(values)), key=lambda i: values[i])
        out = [0.0] * len(values)
        index = 0
        while index < len(order):
            stop = index
            while stop + 1 < len(order) and values[order[stop + 1]] == values[order[index]]:
                stop += 1
            average = (index + stop) / 2.0 + 1.0
            for position in range(index, stop + 1):
                out[order[position]] = average
            index = stop + 1
        return out

    ra, rb = ranks([p[0] for p in pairs]), ranks([p[1] for p in pairs])
    ma, mb = sum(ra) / n, sum(rb) / n
    cov = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    va = math.sqrt(sum((x - ma) ** 2 for x in ra))
    vb = math.sqrt(sum((y - mb) ** 2 for y in rb))
    return cov / (va * vb) if va and vb else None


def universe(entry: Dict[str, Any], key: str) -> Optional[Dict[str, Any]]:
    for row in entry["universes"]:
        if row["key"] == key:
            return row if row.get("supported") else None
    return None


def f(value: Any, spec: str = ".4f", dash: str = "-") -> str:
    if value is None:
        return dash
    if isinstance(value, str):
        return value
    return format(value, spec)


def _name(entry: Dict[str, Any], width: int = 27) -> str:
    return (entry["setName"] or "")[:width]


def section(title: str) -> None:
    print("=" * 108)
    print(title)
    print("=" * 108)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", default="docs/research/set_chase_efficiency_stage2.json")
    args = parser.parse_args(argv)
    report = json.loads(Path(args.artifact).read_text(encoding="utf-8"))
    sets = sorted(report["sets"], key=lambda e: e["setName"] or "")

    print(f"market_date={report['marketDate']} packs={report['packCount']} "
          f"sets={report['analysedSetCount']}/{report['cohortSize']} "
          f"code={report['codeVersion'][:8]} stage={report['stage']}")
    print()

    # ------------------------------------------------------------------
    section("ANTI-DEGENERATION SWEEP — where does Beat-the-Buy peak, and does it fall?")
    print(f"{'set':<28} {'argmaxK':>8} {'BTB@peak':>9} {'BTB@K=3':>8} {'BTB@full':>9} "
          f"{'decline':>8} {'EVshare@peak':>13} {'EVshare@full':>13} {'shape':<18}")
    peak_rows: Dict[str, Dict[str, Any]] = {}
    for entry in sets:
        sweep = entry["degenerationSweep"]
        values = [(row["k"], row["beatTheBuyBest"]["closedForm"], row) for row in sweep
                  if row["beatTheBuyBest"]["closedForm"] is not None]
        if not values:
            continue
        peak_k, peak_btb, peak_row = max(values, key=lambda item: item[1])
        last_k, last_btb, last_row = values[-1]
        first = next((v for v in values if v[0] == 3), values[0])
        decline = None if not peak_btb else (peak_btb - last_btb) / peak_btb
        interior = peak_k != values[0][0] and peak_k != last_k
        shape = "interior_peak" if interior else (
            "rising_to_full_set" if peak_k == last_k else "peak_at_k1")
        peak_rows[entry["setName"]] = {
            "peakK": peak_k, "peakBtb": peak_btb, "fullBtb": last_btb,
            "decline": decline, "shape": shape, "peakRow": peak_row,
            "peakLowestValue": peak_row["lowestSelectedValue"],
        }
        print(f"{_name(entry):<28} {peak_k:>8} {f(peak_btb):>9} {f(first[1]):>8} "
              f"{f(last_btb):>9} {f(decline, '.1%'):>8} "
              f"{f(peak_row['chaseEvBlock']['chaseEvShareOfTotalEv'], '.3f'):>13} "
              f"{f(last_row['chaseEvBlock']['chaseEvShareOfTotalEv'], '.3f'):>13} {shape:<18}")
    shapes: Dict[str, int] = {}
    for row in peak_rows.values():
        shapes[row["shape"]] = shapes.get(row["shape"], 0) + 1
    print(f"\nshape counts: {shapes}")
    print(f"peak K range: {min(r['peakK'] for r in peak_rows.values())} - "
          f"{max(r['peakK'] for r in peak_rows.values())}; "
          f"lowest-selected-value at peak: "
          f"${min(r['peakLowestValue'] for r in peak_rows.values()):.2f} - "
          f"${max(r['peakLowestValue'] for r in peak_rows.values()):.2f}")
    print()

    # ------------------------------------------------------------------
    section(f"CROSS-SET RANKINGS — chase universe = {RANKING_UNIVERSE}")
    rows: List[Tuple[float, List[str]]] = []
    for entry in sets:
        block = universe(entry, RANKING_UNIVERSE)
        if not block:
            continue
        ev = block["chaseEvBlock"]
        btb = block["beatTheBuyBest"]
        gap = block["chaseCostGapBest"]
        rows.append((btb["closedForm"] or 0.0, [
            _name(entry, 26),
            f(entry["acquisitionCost"]["packEquivalentCost"], ".2f"),
            str(block["k"]),
            f(block["anyChaseProbability"], ".5f"),
            f(ev["chaseEv"], ".3f"),
            f(ev["chaseEvReturn"], ".3f"),
            f(ev["chaseEvShareOfTotalEv"], ".3f"),
            f(btb["closedForm"], ".4f"),
            f(btb["direct"], ".4f"),
            f(gap["medianGap"], ".0f"),
            f(gap["medianChaseValueObtained"], ".0f"),
            f(block["depth"]["effectiveEvCount"], ".2f"),
        ]))
    rows.sort(key=lambda item: -item[0])
    header = ["set", "pack$", "K", "p_S", "chaseEV", "EVret", "EVshare",
              "BTB", "BTBdir", "medGap$", "medY$", "effEV"]
    widths = [max(len(header[i]), max((len(r[1][i]) for r in rows), default=0))
              for i in range(len(header))]
    print("  " + "  ".join(h.ljust(widths[i]) for i, h in enumerate(header)))
    print("  " + "  ".join("-" * w for w in widths))
    for rank, (_, cells) in enumerate(rows, 1):
        print(f"{rank:>2} " + " ".join(cells[i].ljust(widths[i]) for i in range(len(cells))))
    print()

    # ------------------------------------------------------------------
    section("BEAT-THE-BUY: definition A (best chase) vs B (total chase haul)")
    print(f"{'set':<28} {'BTB_best':>9} {'BTB_total':>10} {'delta':>8} {'P(2+)':>9} {'maxInPack':>10}")
    deltas = []
    for entry in sets:
        block = universe(entry, RANKING_UNIVERSE)
        if not block:
            continue
        a = block["beatTheBuyBest"]["closedForm"]
        b = block["beatTheBuyTotal"]["closedForm"]
        dist = block["hitCountDistribution"]
        deltas.append((abs((b or 0) - (a or 0)), entry["setName"], a, b))
        print(f"{_name(entry):<28} {f(a):>9} {f(b):>10} {f((b or 0) - (a or 0), '+.5f'):>8} "
              f"{f(dist['pTwoOrMore'], '.6f'):>9} {dist['maxQualifyingInOnePack']:>10}")
    a_vals = [universe(e, RANKING_UNIVERSE)["beatTheBuyBest"]["closedForm"]
              for e in sets if universe(e, RANKING_UNIVERSE)]
    b_vals = [universe(e, RANKING_UNIVERSE)["beatTheBuyTotal"]["closedForm"]
              for e in sets if universe(e, RANKING_UNIVERSE)]
    print(f"\nSpearman(A, B) = {f(spearman(a_vals, b_vals), '.4f')}")
    deltas.sort(reverse=True)
    print("largest A/B divergence: " +
          ", ".join(f"{n} ({f(a)}->{f(b)})" for _, n, a, b in deltas[:3]))
    print()

    # ------------------------------------------------------------------
    section("CLOSED-FORM vs DIRECT BEAT-THE-BUY (validates T independent of Y)")
    worst = []
    for entry in sets:
        for key in HEADLINE_UNIVERSES:
            block = universe(entry, key)
            if not block:
                continue
            btb = block["beatTheBuyBest"]
            if btb["closedForm"] is None or btb["direct"] is None:
                continue
            se = btb["directStandardError"] or 0.0
            sigmas = (btb["agreementAbsolute"] / se) if se > 0 else None
            worst.append((btb["agreementAbsolute"], sigmas, entry["setName"], key,
                          btb["closedForm"], btb["direct"], btb["journeys"]))
    worst.sort(reverse=True)
    print(f"comparisons: {len(worst)}")
    print(f"max |closed - direct| = {f(worst[0][0], '.5f')}   "
          f"median = {f(sorted(w[0] for w in worst)[len(worst)//2], '.5f')}")
    over = [w for w in worst if w[1] is not None and w[1] > 4.0]
    print(f"comparisons exceeding 4 standard errors: {len(over)}")
    print(f"\n{'set':<24} {'universe':<24} {'closed':>8} {'direct':>8} {'|d|':>8} "
          f"{'sigmas':>7} {'journeys':>9}")
    for delta, sigmas, name, key, closed, direct, journeys in worst[:8]:
        print(f"{name[:23]:<24} {key:<24} {f(closed):>8} {f(direct):>8} {f(delta, '.5f'):>8} "
              f"{f(sigmas, '.1f'):>7} {journeys:>9}")
    print()

    # ------------------------------------------------------------------
    section("ADAPTIVE-K STUDY — does effective chase count determine K?")
    print(f"{'set':<28} " + " ".join(f"{k:>10}" for k in
          ("val@20", "ev@20", "val@25", "ev@25", "val@1xC", "ev@1xC", "val@2xC", "ev@2xC")) +
          "   spread")
    spreads = []
    for entry in sets:
        cells, ks = [], []
        for key in ("value_hhi_top_20", "ev_hhi_top_20", "value_hhi_top_25", "ev_hhi_top_25",
                    "value_hhi_gte_1x_cost", "ev_hhi_gte_1x_cost",
                    "value_hhi_gte_2x_cost", "ev_hhi_gte_2x_cost"):
            block = universe(entry, key)
            if block:
                ks.append(block["k"])
                cells.append(f"{block['k']:>10}")
            else:
                cells.append(f"{'-':>10}")
        spread = (max(ks) - min(ks)) if ks else None
        if spread is not None:
            spreads.append(spread)
        print(f"{_name(entry):<28} " + " ".join(cells) + f"   {f(spread, 'd')}")
    if spreads:
        print(f"\nK spread across reference pools: min={min(spreads)} max={max(spreads)} "
              f"mean={sum(spreads)/len(spreads):.1f}")
    print()

    # ------------------------------------------------------------------
    section("PRICE-BOUNDARY STUDY — is there a real elbow?")
    print(f"{'set':<28} {'gapK':>6} {'ratio':>7} {'zK':>4} {'2meansK':>8} {'2meansPrice':>12} "
          f"{'top5 prices'}")
    for entry in sets:
        diag = entry["priceBoundaryDiagnostics"]
        prices = entry["coverage"]["topPrices"][:5]
        print(f"{_name(entry):<28} {f(diag['largestLogGap']['k'], 'd'):>6} "
              f"{f(diag['largestLogGap'].get('boundaryRatio'), '.2f'):>7} "
              f"{f(diag['robustZscore']['k'], 'd'):>4} "
              f"{f(diag['logPrice2Means']['k'], 'd'):>8} "
              f"{f(diag['logPrice2Means'].get('clusterBoundaryPrice'), '.2f'):>12}  "
              + " ".join(f"{p:.0f}" for p in prices))
    print()

    # ------------------------------------------------------------------
    section("BASKET ROBUSTNESS — mean Jaccard under +/-10% price shocks")
    keys = ("top_5", "gte_2x_cost", "gte_5x_cost", "largest_log_gap", "robust_zscore",
            "log_price_2means", "value_hhi_top_20", "ev_hhi_top_20")
    print(f"{'set':<28} " + " ".join(f"{k[:11]:>12}" for k in keys))
    aggregate: Dict[str, List[float]] = {k: [] for k in keys}
    krange: Dict[str, List[int]] = {k: [] for k in keys}
    for entry in sets:
        stability = entry["selectionStability"].get("10pct", {})
        cells = []
        for key in keys:
            block = stability.get(key) or {}
            value = block.get("meanJaccard")
            if value is not None:
                aggregate[key].append(value)
                if block.get("kMin") is not None:
                    krange[key].append(block["kMax"] - block["kMin"])
            cells.append(f"{f(value, '.3f'):>12}")
        print(f"{_name(entry):<28} " + " ".join(cells))
    print(f"\n{'rule':<24} {'meanJaccard':>12} {'minJaccard':>11} {'meanKswing':>11}")
    for key in keys:
        values = aggregate[key]
        swing = krange[key]
        print(f"{key:<24} {f(sum(values)/len(values) if values else None, '.3f'):>12} "
              f"{f(min(values) if values else None, '.3f'):>11} "
              f"{f(sum(swing)/len(swing) if swing else None, '.2f'):>11}")
    print()

    # ------------------------------------------------------------------
    section("CORE + EXTENDED CHASE MODEL")
    print(f"{'set':<28} {'voters':>7} {'core':>5} {'ext':>5} {'coreValue$':>11} {'core cards'}")
    for entry in sets:
        block = entry["coreExtended"]
        core_value = sum(c["marketPrice"] for c in block["core"])
        names = ", ".join(f"{c['cardName'][:16]}" for c in block["core"][:4])
        print(f"{_name(entry):<28} {block['voters']:>7} {block['coreCount']:>5} "
              f"{block['extendedCount']:>5} {core_value:>11.0f}  {names}")
    print()

    # ------------------------------------------------------------------
    section("METRIC CORRELATION MATRIX (Spearman, across sets)")
    metrics: Dict[str, List[Optional[float]]] = {
        "chaseEV": [], "chaseEVreturn": [], "EVshare": [], "BTB": [],
        "medianGap": [], "p_S": [], "medianY": [], "effEV": [],
        "packCost": [], "fullEVreturn": [],
    }
    for entry in sets:
        block = universe(entry, RANKING_UNIVERSE)
        if not block:
            continue
        ev, btb, gap = block["chaseEvBlock"], block["beatTheBuyBest"], block["chaseCostGapBest"]
        metrics["chaseEV"].append(ev["chaseEv"])
        metrics["chaseEVreturn"].append(ev["chaseEvReturn"])
        metrics["EVshare"].append(ev["chaseEvShareOfTotalEv"])
        metrics["BTB"].append(btb["closedForm"])
        metrics["medianGap"].append(gap["medianGap"])
        metrics["p_S"].append(block["anyChaseProbability"])
        metrics["medianY"].append(gap["medianChaseValueObtained"])
        metrics["effEV"].append(block["depth"]["effectiveEvCount"])
        metrics["packCost"].append(entry["acquisitionCost"]["packEquivalentCost"])
        metrics["fullEVreturn"].append(ev["fullPackEvReturn"])
    names = list(metrics)
    print(f"{'':<15}" + "".join(f"{n[:12]:>13}" for n in names))
    for a in names:
        print(f"{a:<15}" + "".join(f"{f(spearman(metrics[a], metrics[b]), '+.3f'):>13}"
                                   for b in names))
    print()

    # ------------------------------------------------------------------
    section("CHASE-UNIVERSE COMPARISON — K and BTB by method")
    print(f"{'set':<24} " + " ".join(f"{k[:10]:>11}" for k in HEADLINE_UNIVERSES[:10]))
    for entry in sets:
        cells = []
        for key in HEADLINE_UNIVERSES[:10]:
            block = universe(entry, key)
            cells.append(f"{block['k']:>4}/{f(block['beatTheBuyBest']['closedForm'], '.3f')}"
                         if block else f"{'-':>11}")
        print(f"{_name(entry, 23):<24} " + " ".join(f"{c:>11}" for c in cells))
    print("\n(cells are K/BTB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
