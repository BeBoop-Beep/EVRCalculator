"""Read the Stage-I Set Chase Efficiency artifact and answer the study's questions.

RESEARCH ONLY. Pure reader: it opens the JSON produced by
``build_set_chase_efficiency_research`` and prints the tables the Stage-I brief
asks for. It performs no simulation and no database read, so every table here
is reproducible from the artifact alone.

    python -m backend.scripts.report_set_chase_efficiency_research \
        --artifact docs/research/set_chase_efficiency_stage1.json
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

FRONTIER_K = (1, 3, 5, 10, 15, 20)

#: The V_S candidates whose ranking impact the study has to measure.
VALUE_STATISTICS = (
    ("meanTotal", "conditional mean of total qualifying value"),
    ("medianTotal", "conditional median of total qualifying value"),
    ("winsorizedMeanTotal", "5% winsorized conditional mean of total"),
    ("trimmedMeanTotal", "10% trimmed conditional mean of total"),
    ("meanBest", "conditional mean of the single best qualifying card"),
    ("medianBest", "conditional median of the single best qualifying card"),
)


def spearman(a: Sequence[float], b: Sequence[float]) -> Optional[float]:
    """Rank correlation with average ranks for ties.

    Implemented here rather than pulled from scipy so the reader has no
    dependency the research environment might not carry.
    """
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
    mean_a, mean_b = sum(ra) / n, sum(rb) / n
    cov = sum((x - mean_a) * (y - mean_b) for x, y in zip(ra, rb))
    var_a = math.sqrt(sum((x - mean_a) ** 2 for x in ra))
    var_b = math.sqrt(sum((y - mean_b) ** 2 for y in rb))
    if var_a == 0 or var_b == 0:
        return None
    return cov / (var_a * var_b)


def basket_of(entry: Dict[str, Any], key: str) -> Optional[Dict[str, Any]]:
    for basket in entry["baskets"]:
        if basket["definitionKey"] == key:
            return basket if not basket.get("excludedFromScoring") else None
    return None


def _fmt(value: Any, spec: str = ".4f") -> str:
    if value is None:
        return "-"
    if isinstance(value, str):
        return value
    return format(value, spec)


def ranking_table(report: Dict[str, Any], key: str, statistic: str = "meanTotal") -> str:
    rows: List[Tuple[float, List[str]]] = []
    for entry in report["sets"]:
        basket = basket_of(entry, key)
        if not basket:
            continue
        ce = basket["chaseEfficiency"].get(statistic)
        if ce is None:
            continue
        horizons = basket["horizons"]
        rows.append((ce, [
            (entry["setName"] or "")[:26],
            _fmt(ce),
            _fmt(entry["acquisitionCost"]["packEquivalentCost"], ".2f"),
            _fmt(basket["probabilityAtLeastOne"], ".5f"),
            _fmt(basket["conditionalValueTotal"]["mean"], ".2f"),
            _fmt(basket["conditionalValueTotal"]["median"], ".2f"),
            _fmt(basket["expectedPacksPerQualifyingChase"], ".1f"),
            _fmt(horizons["50"]["packsWhole"], "d") if horizons["50"]["packsWhole"] else "-",
            _fmt(horizons["50"]["spendWhole"], ".0f"),
            str(basket["chaseCount"]),
            _fmt(basket["concentration"]["top1Share"], ".3f"),
        ]))
    rows.sort(key=lambda item: -item[0])
    header = ["set", "CE", "pack$", "p_S", "V_mean", "V_med", "packs/hit",
              "n50%", "spend50%", "n", "top1sh"]
    widths = [max(len(header[i]), max((len(r[1][i]) for r in rows), default=0))
              for i in range(len(header))]
    lines = ["  ".join(h.ljust(widths[i]) for i, h in enumerate(header)),
             "  ".join("-" * w for w in widths)]
    for rank, (_, cells) in enumerate(rows, 1):
        lines.append("  ".join(cells[i].ljust(widths[i]) for i in range(len(cells))))
    return "\n".join(f"{index:>2}  {line}" if index else f"    {line}"
                     for index, line in
                     [(0, lines[0]), (0, lines[1])] + list(enumerate(lines[2:], 1)))


def frontier_shape(entry: Dict[str, Any], statistic: str) -> Dict[str, Any]:
    """Classify CE(K) for one set: rising, plateau, peaked or inconsistent."""
    curve: List[Tuple[int, float]] = []
    for k in FRONTIER_K:
        basket = basket_of(entry, f"top_{k}")
        if not basket:
            continue
        ce = basket["chaseEfficiency"].get(statistic)
        if ce is not None:
            curve.append((k, ce))
    if len(curve) < 3:
        return {"shape": "insufficient_k", "curve": curve, "argmax": None}
    values = [value for _, value in curve]
    argmax = curve[values.index(max(values))][0]
    rising = all(b >= a for a, b in zip(values, values[1:]))
    falling_after_peak = (
        argmax not in (curve[0][0], curve[-1][0])
        and all(b >= a for a, b in zip(values[:values.index(max(values)) + 1],
                                       values[1:values.index(max(values)) + 1]))
        and all(b <= a for a, b in zip(values[values.index(max(values)):],
                                       values[values.index(max(values)) + 1:]))
    )
    last_gain = (values[-1] - values[-2]) / values[-2] if values[-2] else None
    if rising:
        shape = "monotone_rising_plateau" if (last_gain is not None and last_gain < 0.05) \
            else "monotone_rising"
    elif falling_after_peak:
        shape = "interior_peak"
    else:
        shape = "inconsistent"
    return {"shape": shape, "curve": curve, "argmax": argmax,
            "finalMarginalGain": last_gain}


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", default="docs/research/set_chase_efficiency_stage1.json")
    parser.add_argument("--out", default=None, help="optional JSON summary path")
    args = parser.parse_args(argv)

    report = json.loads(Path(args.artifact).read_text(encoding="utf-8"))
    print(f"market_date={report['marketDate']} packs={report['packCount']} "
          f"sets={report['analysedSetCount']} code={report['codeVersion'][:8]}")
    print(f"research={report['researchVersion']} calc={report['calculationVersion']}")
    print()

    # -- coverage ----------------------------------------------------------
    print("=" * 100)
    print("DATA COVERAGE")
    print("=" * 100)
    print(f"{'set':<28} {'drawable':>9} {'eligible':>9} {'excluded':>9} {'>=$20':>7} "
          f"{'>=$50':>7} {'max$':>9} {'pack$':>7} {'priceDates'}")
    total_excluded: Dict[str, int] = {}
    for entry in sorted(report["sets"], key=lambda e: e["setName"] or ""):
        coverage = entry["coverage"]
        for reason, count in coverage["excludedByReason"].items():
            total_excluded[reason] = total_excluded.get(reason, 0) + count
        print(f"{(entry['setName'] or '')[:27]:<28} {coverage['drawableEntities']:>9} "
              f"{coverage['eligibleChaseUniverse']:>9} {coverage['excludedEntities']:>9} "
              f"{coverage['eligibleAtOrAbove']['20']:>7} {coverage['eligibleAtOrAbove']['50']:>7} "
              f"{_fmt(coverage['eligiblePriceMax'], '.2f'):>9} "
              f"{_fmt(entry['acquisitionCost']['packEquivalentCost'], '.2f'):>7} "
              f"{','.join(sorted(str(d) for d in coverage['priceCaptureDates']))}")
    print(f"\nexclusions across cohort: {total_excluded or 'none'}")
    print()

    # -- rankings ----------------------------------------------------------
    for key in ("top_1", "top_3", "top_5", "top_10"):
        print("=" * 100)
        print(f"SET CHASE EFFICIENCY - {key.upper()} basket (V_S = conditional mean of total)")
        print("=" * 100)
        print(ranking_table(report, key))
        print()

    # -- frontier shape ----------------------------------------------------
    print("=" * 100)
    print("CHASE FRONTIER: does CE(K) plateau, peak, or keep rising?")
    print("=" * 100)
    shapes: Dict[str, Dict[str, int]] = {}
    for statistic, _label in VALUE_STATISTICS:
        counts: Dict[str, int] = {}
        for entry in report["sets"]:
            shape = frontier_shape(entry, statistic)["shape"]
            counts[shape] = counts.get(shape, 0) + 1
        shapes[statistic] = counts
        print(f"{statistic:<22} {counts}")
    print()
    print(f"{'set':<28} " + " ".join(f"K={k:<8}" for k in FRONTIER_K) + " shape")
    for entry in sorted(report["sets"], key=lambda e: e["setName"] or ""):
        shape = frontier_shape(entry, "meanTotal")
        cells = []
        for k in FRONTIER_K:
            basket = basket_of(entry, f"top_{k}")
            ce = basket["chaseEfficiency"]["meanTotal"] if basket else None
            cells.append(f"{_fmt(ce, '.4f'):<10}")
        print(f"{(entry['setName'] or '')[:27]:<28} " + " ".join(cells) + f" {shape['shape']}")
    print()

    # -- V_S sensitivity ---------------------------------------------------
    print("=" * 100)
    print("V_S SENSITIVITY: Spearman rank correlation against the conditional mean")
    print("=" * 100)
    sensitivity: Dict[str, Dict[str, Any]] = {}
    for key in ("top_1", "top_3", "top_5", "top_10"):
        baseline = []
        others: Dict[str, List[Optional[float]]] = {s: [] for s, _ in VALUE_STATISTICS}
        names = []
        for entry in report["sets"]:
            basket = basket_of(entry, key)
            if not basket:
                continue
            names.append(entry["setName"])
            baseline.append(basket["chaseEfficiency"].get("meanTotal"))
            for statistic, _ in VALUE_STATISTICS:
                others[statistic].append(basket["chaseEfficiency"].get(statistic))
        row = {statistic: spearman(baseline, values) for statistic, values in others.items()}
        sensitivity[key] = row
        print(f"{key:<8} " + "  ".join(
            f"{statistic}={_fmt(value, '.3f')}" for statistic, value in row.items()))
    print()

    # -- K sensitivity of the ranking itself -------------------------------
    print("=" * 100)
    print("IS THE RANKING K-STABLE? Spearman between Top-K rankings (meanTotal)")
    print("=" * 100)
    per_k: Dict[int, Dict[str, float]] = {}
    for k in FRONTIER_K:
        per_k[k] = {}
        for entry in report["sets"]:
            basket = basket_of(entry, f"top_{k}")
            if basket and basket["chaseEfficiency"].get("meanTotal") is not None:
                per_k[k][entry["setName"]] = basket["chaseEfficiency"]["meanTotal"]
    for a in FRONTIER_K:
        cells = []
        for b in FRONTIER_K:
            shared = sorted(set(per_k[a]) & set(per_k[b]))
            cells.append(_fmt(spearman([per_k[a][s] for s in shared],
                                       [per_k[b][s] for s in shared]), ".3f"))
        print(f"K={a:<3} " + "  ".join(c.rjust(6) for c in cells))
    print("      " + "  ".join(f"K={k}".rjust(6) for k in FRONTIER_K))
    print()

    # -- largest movers ----------------------------------------------------
    print("=" * 100)
    print("LARGEST RANK MOVERS between Top-1 and Top-10")
    print("=" * 100)

    def rank_map(k: int) -> Dict[str, int]:
        ordered = sorted(per_k[k].items(), key=lambda item: -item[1])
        return {name: index for index, (name, _) in enumerate(ordered, 1)}

    r1, r10 = rank_map(1), rank_map(10)
    movers = sorted(
        ((name, r1[name], r10[name], r1[name] - r10[name]) for name in r1 if name in r10),
        key=lambda item: -abs(item[3]),
    )
    for name, a, b, delta in movers[:8]:
        print(f"{name[:30]:<32} Top-1 rank {a:>2} -> Top-10 rank {b:>2}  (moved {delta:+d})")
    print()

    # -- threshold basket stability ---------------------------------------
    print("=" * 100)
    print("THRESHOLD AND COST-MULTIPLE BASKETS: does a stable chase universe emerge?")
    print("=" * 100)
    print(f"{'set':<28} " + " ".join(f"{k:>10}" for k in
          ("$10", "$20", "$30", "$50", "$100", "2xC", "5xC", "10xC", "25xC")))
    for entry in sorted(report["sets"], key=lambda e: e["setName"] or ""):
        cells = []
        for key in ("value_gte_10", "value_gte_20", "value_gte_30", "value_gte_50",
                    "value_gte_100", "value_gte_2x_pack", "value_gte_5x_pack",
                    "value_gte_10x_pack", "value_gte_25x_pack"):
            basket = basket_of(entry, key)
            cells.append(f"{basket['chaseCount']:>10}" if basket else f"{'-':>10}")
        print(f"{(entry['setName'] or '')[:27]:<28} " + " ".join(cells))
    print()

    # -- concentration -----------------------------------------------------
    print("=" * 100)
    print("CHASE CONCENTRATION (Top-10 basket)")
    print("=" * 100)
    print(f"{'set':<28} {'top1':>7} {'top3':>7} {'top5':>7} {'rest':>7} {'HHI':>7} {'effN':>7}")
    for entry in sorted(report["sets"], key=lambda e: e["setName"] or ""):
        basket = basket_of(entry, "top_10")
        if not basket:
            continue
        block = basket["concentration"]
        print(f"{(entry['setName'] or '')[:27]:<28} "
              f"{_fmt(block['top1Share'], '.3f'):>7} {_fmt(block['top3Share'], '.3f'):>7} "
              f"{_fmt(block['top5Share'], '.3f'):>7} {_fmt(block['remainderShare'], '.3f'):>7} "
              f"{_fmt(block['herfindahl'], '.3f'):>7} "
              f"{_fmt(block['effectiveChaseCount'], '.2f'):>7}")
    print()

    # -- multi-hit openings ------------------------------------------------
    print("=" * 100)
    print("MULTI-CHASE OPENINGS (Top-10 basket): P(0) / P(1) / P(>=2), identity check")
    print("=" * 100)
    identity_failures = []
    for entry in sorted(report["sets"], key=lambda e: e["setName"] or ""):
        basket = basket_of(entry, "top_10")
        if not basket:
            continue
        block = basket["hitCountDistribution"]
        if not block["identityHolds"]:
            identity_failures.append(entry["setName"])
        print(f"{(entry['setName'] or '')[:27]:<28} "
              f"P0={block['pZero']:.5f}  P1={block['pExactlyOne']:.5f}  "
              f"P2+={block['pTwoOrMore']:.6f}  maxInPack={block['maxQualifyingInOnePack']}  "
              f"SE(p)={_fmt(basket['probabilityStandardError'], '.6f')}")
    print(f"\nP(>=1) == 1 - P(0) identity failures: {identity_failures or 'none'}")

    if args.out:
        Path(args.out).write_text(json.dumps({
            "marketDate": report["marketDate"],
            "packCount": report["packCount"],
            "frontierShapeCounts": shapes,
            "valueStatisticSensitivity": sensitivity,
            "topKRankCorrelation": {
                f"{a}_vs_{b}": spearman(
                    [per_k[a][s] for s in sorted(set(per_k[a]) & set(per_k[b]))],
                    [per_k[b][s] for s in sorted(set(per_k[a]) & set(per_k[b]))])
                for a in FRONTIER_K for b in FRONTIER_K if a < b
            },
        }, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
