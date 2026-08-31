"""Stage V-C analysis over the product chase artifact.

RESEARCH ONLY. Reads ``docs/research/product_chase_stage5c.json`` and prints the
Phase 12-20 analyses. Writes nothing.

    python -m backend.scripts.report_product_chase_stage5c

Price shocks are recomputed here rather than in the build because a +x% shock to
every card price is exactly equivalent to dividing the tier threshold by (1+x),
and a -x% shock to the product price divides the threshold by (1-x). Both are
closed-form over the stored eligible price vector, so no re-simulation is needed
and the shock grid costs nothing.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics as st
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

ARTIFACT = Path("docs/research/product_chase_stage5c.json")
CORE_MULTIPLE = 3.0
EXTENDED_MULTIPLE = 1.0
SHOCKS = (0.02, 0.05, 0.10, 0.20)


def _flat(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """One row per scored product, with the fields the analyses need."""
    rows: List[Dict[str, Any]] = []
    for entry in payload["sets"]:
        cheapest = ((entry.get("setCheapestRoute") or {}).get("packEquivalentCost"))
        prices = entry["universe"].get("eligiblePrices") or []
        for product in entry["products"]:
            core, ext = product["core"], product["coreAndExtended"]
            rows.append({
                "set": entry["setName"],
                "prices": prices,
                "cheapestRoute": cheapest,
                "name": product["productName"],
                "family": product["productFamily"],
                "cost": product["productMarketCost"],
                "packs": product["randomPackCount"],
                "C": product["tierContract"]["packEquivalentCost"],
                "coreK": product["membership"]["coreCount"],
                "extK": product["membership"]["extendedCount"],
                "depth": core.get("chaseDepth"),
                "extDepth": ext.get("chaseDepth"),
                "pPack": core.get("packProbability"),
                "pProduct": ((core.get("productProbability") or {})
                             .get("probabilityAtLeastOne")),
                "evReturn": ((core.get("productChaseEv") or {}).get("chaseEvReturn")),
                "evShare": ((core.get("productChaseEv") or {})
                            .get("chaseEvShareOfFullEv")),
                "btb": ((core.get("beatTheBuyPackGranular") or {}).get("closedForm")),
                "btbWhole": ((core.get("costGapWholeProduct") or {}).get("beatTheBuy")),
                "gapMedian": ((core.get("costGapPackGranular") or {}).get("median")),
                "gapWholeMedian": ((core.get("costGapWholeProduct") or {}).get("median")),
                "spend50": (((core.get("accessibility") or {}).get("costNormalised") or {})
                            .get("50", {}).get("spendPackGranular")),
                "spend50Whole": (((core.get("accessibility") or {}).get("costNormalised") or {})
                                 .get("50", {}).get("spendWholeProduct")),
            })
    return rows


def _k(prices: Sequence[float], threshold: float) -> int:
    return sum(1 for p in prices if p >= threshold)


def _spearman(x: Sequence[float], y: Sequence[float]) -> Optional[float]:
    pairs = [(a, b) for a, b in zip(x, y) if a is not None and b is not None]
    if len(pairs) < 3:
        return None
    def rank(values):
        order = sorted(range(len(values)), key=lambda i: values[i])
        out = [0.0] * len(values)
        for position, index in enumerate(order):
            out[index] = position + 1.0
        return out
    a = rank([p[0] for p in pairs])
    b = rank([p[1] for p in pairs])
    ma, mb = st.mean(a), st.mean(b)
    num = sum((a[i] - ma) * (b[i] - mb) for i in range(len(a)))
    den = math.sqrt(sum((v - ma) ** 2 for v in a) * sum((v - mb) ** 2 for v in b))
    return num / den if den else None


def _pearson(x: Sequence[float], y: Sequence[float]) -> Optional[float]:
    pairs = [(a, b) for a, b in zip(x, y) if a is not None and b is not None]
    if len(pairs) < 3:
        return None
    a = [p[0] for p in pairs]
    b = [p[1] for p in pairs]
    ma, mb = st.mean(a), st.mean(b)
    num = sum((a[i] - ma) * (b[i] - mb) for i in range(len(a)))
    den = math.sqrt(sum((v - ma) ** 2 for v in a) * sum((v - mb) ** 2 for v in b))
    return num / den if den else None


def phase12_tournament(rows: List[Dict[str, Any]]) -> None:
    print("\n=== PHASE 12 - same-set product tournament ===")
    print("Winners by criterion, per set. They are NOT expected to agree.")
    by_set: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        by_set.setdefault(row["set"], []).append(row)
    disagreements = 0
    considered = 0
    print("%-24s %-26s %-26s %-26s" % ("set", "cheapest pack", "deepest core", "best EV return"))
    for name, group in sorted(by_set.items()):
        if len(group) < 2:
            continue
        considered += 1
        cheapest = min(group, key=lambda r: r["C"])
        deepest = max(group, key=lambda r: (r["depth"] or 0.0))
        best_ev = max(group, key=lambda r: (r["evReturn"] or 0.0))
        best_prod = max(group, key=lambda r: (r["pProduct"] or 0.0))
        winners = {cheapest["name"], deepest["name"], best_ev["name"], best_prod["name"]}
        if len(winners) > 1:
            disagreements += 1
        print("%-24s %-26s %-26s %-26s" % (
            name[:23], cheapest["name"][:25], deepest["name"][:25], best_ev["name"][:25]))
    print("\nsets with >=2 products: %d ; sets where the winners disagree: %d"
          % (considered, disagreements))


def phase13_inheritance(rows: List[Dict[str, Any]]) -> None:
    print("\n=== PHASE 13 - set-inheritance error ===")
    print("What set-level inheritance (cheapest route) would have assigned, versus native.")
    deltas_core, deltas_ext = [], []
    by_family: Dict[str, List[float]] = {}
    for row in rows:
        if not row["cheapestRoute"] or not row["prices"]:
            continue
        inherited_core = _k(row["prices"], CORE_MULTIPLE * row["cheapestRoute"])
        inherited_ext = _k(row["prices"], EXTENDED_MULTIPLE * row["cheapestRoute"])
        d_core = row["coreK"] - inherited_core
        deltas_core.append(d_core)
        deltas_ext.append(row["extK"] - inherited_ext)
        by_family.setdefault(row["family"], []).append(d_core)
    if not deltas_core:
        print("  no comparable rows")
        return
    for label, deltas in (("Core K", deltas_core), ("Extended K", deltas_ext)):
        ordered = sorted(deltas)
        p90 = ordered[int(0.10 * (len(ordered) - 1))]
        print("  %-12s mean %+6.2f  median %+5.1f  P90(worst) %+5.1f  max %+d  min %d  "
              "negative %d/%d" % (label, st.mean(deltas), st.median(deltas), p90,
                                  max(deltas), min(deltas),
                                  sum(1 for d in deltas if d < 0), len(deltas)))
    print("\n  by family (Core K delta):")
    print("  %-38s %5s %9s %9s" % ("family", "n", "meanDelta", "worst"))
    for family, deltas in sorted(by_family.items(), key=lambda kv: st.mean(kv[1])):
        print("  %-38s %5d %+9.2f %+9d" % (family, len(deltas), st.mean(deltas), min(deltas)))


def phase14_fairness(rows: List[Dict[str, Any]]) -> None:
    print("\n=== PHASE 14 - product-family fairness ===")
    packs = [r["packs"] for r in rows]
    print("  Spearman of each metric against RANDOM PACK COUNT and against PRODUCT COST.")
    print("  %-28s %14s %14s" % ("metric", "rho(packs)", "rho(cost)"))
    costs = [r["cost"] for r in rows]
    for key, label in (("pProduct", "per-product hit rate"), ("pPack", "per-pack hit rate"),
                       ("spend50", "50% spend (pack-gran)"),
                       ("spend50Whole", "50% spend (whole unit)"),
                       ("coreK", "Core K"), ("depth", "Chase Depth"),
                       ("evReturn", "Chase EV Return")):
        values = [r[key] for r in rows]
        print("  %-28s %14s %14s" % (
            label,
            "%+.3f" % _spearman(values, packs) if _spearman(values, packs) is not None else "-",
            "%+.3f" % _spearman(values, costs) if _spearman(values, costs) is not None else "-"))
    print("\n  by family (medians):")
    print("  %-38s %4s %8s %8s %8s %10s" % ("family", "n", "packs", "pProduct", "depth", "spend50"))
    by_family: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        by_family.setdefault(row["family"], []).append(row)
    for family, group in sorted(by_family.items(), key=lambda kv: -st.median([g["packs"] for g in kv[1]])):
        def med(key):
            vals = [g[key] for g in group if g[key] is not None]
            return st.median(vals) if vals else float("nan")
        print("  %-38s %4d %8.0f %8.3f %8s %10.0f" % (
            family, len(group), med("packs"), med("pProduct"),
            ("%.2f" % med("depth")) if group else "-", med("spend50")))


def phase15_shocks(rows: List[Dict[str, Any]]) -> None:
    print("\n=== PHASE 15 - price shocks (closed form over the eligible price vector) ===")
    print("  A +x%% card shock == threshold/(1+x). A +x%% product shock == threshold*(1+x).")
    print("  %-16s %10s %10s %10s %10s" % ("shock", "coreJ", "coreKmin", "coreKmax", "thinFlips"))
    for shock in SHOCKS:
        for label, card_factor, product_factor in (
                ("card +%d%%" % int(shock * 100), 1.0 + shock, 1.0),
                ("card -%d%%" % int(shock * 100), 1.0 - shock, 1.0),
                ("prod +%d%%" % int(shock * 100), 1.0, 1.0 + shock),
                ("prod -%d%%" % int(shock * 100), 1.0, 1.0 - shock)):
            jaccards, kmin, kmax, thin_flips = [], [], [], 0
            for row in rows:
                if not row["prices"]:
                    continue
                base = CORE_MULTIPLE * row["C"]
                shocked = base * product_factor / card_factor
                base_set = {i for i, p in enumerate(row["prices"]) if p >= base}
                new_set = {i for i, p in enumerate(row["prices"]) if p >= shocked}
                union = base_set | new_set
                jaccards.append(1.0 if not union else len(base_set & new_set) / len(union))
                kmin.append(len(new_set))
                kmax.append(len(new_set))
                if len(base_set) <= 2 and len(base_set) != len(new_set):
                    thin_flips += 1
            if jaccards:
                print("  %-16s %10.4f %10d %10d %10d" % (
                    label, st.mean(jaccards), min(kmin), max(kmax), thin_flips))


def phase18_redundancy(rows: List[Dict[str, Any]]) -> None:
    print("\n=== PHASE 18 - product-level metric redundancy ===")
    keys = [("coreK", "Literal Core K"), ("depth", "Chase Depth"),
            ("pPack", "Any-Chase per pack"), ("pProduct", "Any-Chase per product"),
            ("spend50", "50% Chase Spend"), ("evReturn", "Chase EV Return"),
            ("evShare", "Chase EV Share"), ("btb", "Beat-the-Buy"),
            ("gapMedian", "median Cost Gap")]
    print("  Spearman matrix (n=%d products)" % len(rows))
    header = "  %-22s" % "" + "".join("%9s" % k[0][:8] for k in keys)
    print(header)
    for key, label in keys:
        line = "  %-22s" % label
        for other, _ in keys:
            rho = _spearman([r[key] for r in rows], [r[other] for r in rows])
            line += "%9s" % ("-" if rho is None else "%+.2f" % rho)
        print(line)


def phase19_depth(rows: List[Dict[str, Any]]) -> None:
    print("\n=== PHASE 19 - product-level Chase Depth ===")
    depths = [r["depth"] for r in rows if r["depth"] is not None]
    if not depths:
        print("  no depth values")
        return
    print("  n=%d  min %.2f  median %.2f  max %.2f" % (
        len(depths), min(depths), st.median(depths), max(depths)))
    by_set: Dict[str, List[float]] = {}
    for row in rows:
        if row["depth"] is not None:
            by_set.setdefault(row["set"], []).append(row["depth"])
    spreads = [(max(v) - min(v), k) for k, v in by_set.items() if len(v) >= 2]
    spreads.sort(reverse=True)
    print("  within-set depth spread: median %.2f  max %.2f (%s)" % (
        st.median([s for s, _ in spreads]), spreads[0][0], spreads[0][1]))
    print("  sets where depth is CONSTANT across products: %d/%d"
          % (sum(1 for s, _ in spreads if s == 0), len(spreads)))
    print("  rho(depth, Core K)      %s" % _fmt(_spearman(
        [r["depth"] for r in rows], [r["coreK"] for r in rows])))
    print("  rho(depth, pack cost)   %s" % _fmt(_spearman(
        [r["depth"] for r in rows], [r["C"] for r in rows])))
    print("  rho(depth, EV Return)   %s" % _fmt(_spearman(
        [r["depth"] for r in rows], [r["evReturn"] for r in rows])))


def _fmt(value: Optional[float]) -> str:
    return "-" if value is None else "%+.3f" % value


def phase20_coverage(payload: Dict[str, Any], rows: List[Dict[str, Any]]) -> None:
    print("\n=== PHASE 20 - coverage gate ===")
    unsupported: Dict[str, int] = {}
    families_unsupported: Dict[str, int] = {}
    for entry in payload["sets"]:
        for product in entry["unsupportedProducts"]:
            unsupported[product["reason"]] = unsupported.get(product["reason"], 0) + 1
            fam = product.get("productFamily") or "unknown"
            families_unsupported[fam] = families_unsupported.get(fam, 0) + 1
    print("  sets: %d   scored products: %d   unsupported: %d"
          % (payload["setCount"], payload["scoredProductCount"],
             payload["unsupportedProductCount"]))
    for reason, count in sorted(unsupported.items(), key=lambda kv: -kv[1]):
        print("     %-34s %d" % (reason, count))
    if families_unsupported:
        print("  unsupported by family:")
        for fam, count in sorted(families_unsupported.items(), key=lambda kv: -kv[1]):
            print("     %-34s %d" % (fam, count))
    families = sorted({r["family"] for r in rows})
    print("  families covered (%d): %s" % (len(families), ", ".join(families)))
    skews = {e["setName"]: e.get("priceBasisSkewDays") for e in payload["sets"]}
    distinct = sorted({v for v in skews.values() if v is not None})
    print("  card-price vs product-cost skew (days): %s" % (distinct or "n/a"))


def main(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(description="Stage V-C analysis.")
    parser.add_argument("--artifact", default=str(ARTIFACT))
    args = parser.parse_args(list(argv))

    payload = json.loads(Path(args.artifact).read_text(encoding="utf-8"))
    rows = _flat(payload)
    print("Stage V-C artifact: %s" % payload["stage"])
    print("tier contract: %s" % payload["tierContract"])
    print("aggregation: %s" % payload["aggregationAssumption"])
    print("market date %s | packs %d | products %d"
          % (payload["marketDate"], payload["packCount"], len(rows)))

    phase20_coverage(payload, rows)
    phase12_tournament(rows)
    phase13_inheritance(rows)
    phase14_fairness(rows)
    phase15_shocks(rows)
    phase18_redundancy(rows)
    phase19_depth(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
