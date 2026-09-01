"""Read the Stage-IV artifact and score the objective Chase Tier candidates.

RESEARCH ONLY. Pure reader over ``docs/research/set_chase_tiers_stage4.json``:
no simulation, no database read, so every table is reproducible from the
artifact alone.

    python -m backend.scripts.report_chase_tier_research
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from statistics import median
from typing import Any, Dict, List, Optional, Sequence, Tuple

#: Sets called out for detailed inspection.
CASE_STUDY_SETS = ("Ascended Heroes", "Scarlet and Violet 151", "Prismatic Evolutions",
                   "Paradox Rift", "Phantasmal Flames", "White Flare")

#: Systems carried through the headline tables. Chosen to span the families,
#: not because they are expected to win.
HEADLINE_SYSTEMS = ("A_pct_only", "B_pct_floor", "C_tight", "D_wide",
                    "Z_logz", "Z_median", "Z_top")


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


def f(value: Any, spec: str = ".3f", dash: str = "-") -> str:
    if value is None:
        return dash
    if isinstance(value, str):
        return value
    return format(value, spec)


def section(title: str) -> None:
    print("=" * 112)
    print(title)
    print("=" * 112)


def rule_rows(report: Dict[str, Any], key: str) -> List[Tuple[Dict[str, Any], Dict[str, Any]]]:
    out = []
    for entry in report["sets"]:
        for rule in entry["singleRules"]:
            if rule["ruleKey"] == key:
                out.append((entry, rule))
    return out


def system_rows(report: Dict[str, Any], key: str) -> List[Tuple[Dict[str, Any], Dict[str, Any]]]:
    out = []
    for entry in report["sets"]:
        for system in entry["tierSystems"]:
            if system["systemKey"] == key:
                out.append((entry, system))
    return out


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", default="docs/research/set_chase_tiers_stage4.json")
    args = parser.parse_args(argv)
    report = json.loads(Path(args.artifact).read_text(encoding="utf-8"))
    sets = sorted(report["sets"], key=lambda e: e["setName"] or "")

    print(f"stage={report['stage']} market_date={report['marketDate']} "
          f"packs={report['packCount']} sets={report['analysedSetCount']}/{report['cohortSize']} "
          f"rules={report['candidateRuleCount']} systems={report['candidateSystemCount']} "
          f"code={report['codeVersion'][:8]}")
    print()

    # ------------------------------------------------------------------
    section("PHASE 2 - ELIGIBLE UNIVERSE")
    print(f"{'set':<28} {'draw':>6} {'elig':>6} {'excl':>5} {'distinct':>9} "
          f"{'pack$':>7} {'median$':>8} {'q75$':>7} {'top$':>9}")
    for entry in sets:
        u = entry["universe"]
        assert u["eligiblePrintings"] == u["distinctIdentities"], entry["setName"]
        print(f"{entry['setName'][:27]:<28} {u['drawablePrintings']:>6} "
              f"{u['eligiblePrintings']:>6} {u['excludedPrintings']:>5} "
              f"{u['distinctIdentities']:>9} "
              f"{f(entry['acquisitionCost']['packEquivalentCost'], '.2f'):>7} "
              f"{f(u['medianPrice'], '.2f'):>8} {f(u['upperQuartilePrice'], '.2f'):>7} "
              f"{f(u['topPrices'][0] if u['topPrices'] else None, '.2f'):>9}")
    print("\n(uniqueness invariant eligible == distinct (set_id, card_variant_id): PASS)")
    print()

    # ------------------------------------------------------------------
    section("PHASE 3 - PURE CARD-COUNT PERCENTILE: does K land below the pack price?")
    print(f"{'set':<26} " + " ".join(f"{p:>13}" for p in
          ("2.5%", "5%", "7.5%", "10%", "15%", "20%")) + "   pack$")
    below_pack = {p: 0 for p in ("2.5", "5", "7.5", "10", "15", "20")}
    for entry in sets:
        cost = entry["acquisitionCost"]["packEquivalentCost"]
        cells = []
        for percent in ("2.5", "5", "7.5", "10", "15", "20"):
            rule = next(r for r in entry["singleRules"] if r["ruleKey"] == f"top{percent}pct_ceil")
            low = rule["minimumQualifyingValue"]
            flag = ""
            if low is not None and cost and low < cost:
                below_pack[percent] += 1
                flag = "*"
            cells.append(f"{rule['selectedK']:>4}/${f(low, '.0f')}{flag:<1}".rjust(13))
        print(f"{entry['setName'][:25]:<26} " + " ".join(cells) + f"   {f(cost, '.2f')}")
    print("\n(K/minimum qualifying value; * = the tier's cheapest card is worth LESS than one pack)")
    print("sets whose percentile tier dips below one pack: " +
          ", ".join(f"{k}%={v}/{len(sets)}" for k, v in below_pack.items()))
    print()

    # ------------------------------------------------------------------
    section("PHASE 3 - ROUNDING MODE: how often does the choice change K?")
    diffs = {"floor_vs_ceil": 0, "round_vs_ceil": 0, "total": 0}
    zero_floor = 0
    for entry in sets:
        for percent in ("2.5", "5", "7.5", "10", "15", "20"):
            ks = {}
            for mode in ("floor", "round", "ceil"):
                rule = next(r for r in entry["singleRules"]
                            if r["ruleKey"] == f"top{percent}pct_{mode}")
                ks[mode] = rule["selectedK"]
            diffs["total"] += 1
            diffs["floor_vs_ceil"] += int(ks["floor"] != ks["ceil"])
            diffs["round_vs_ceil"] += int(ks["round"] != ks["ceil"])
            if ks["floor"] <= 1 and ks["ceil"] > 1:
                zero_floor += 1
    print(f"(set x percentile) combinations: {diffs['total']}")
    print(f"  floor differs from ceil: {diffs['floor_vs_ceil']} "
          f"({diffs['floor_vs_ceil'] / diffs['total']:.1%})")
    print(f"  round differs from ceil: {diffs['round_vs_ceil']} "
          f"({diffs['round_vs_ceil'] / diffs['total']:.1%})")
    print(f"  cases where floor would have clamped to the 1-card minimum: {zero_floor}")
    print()

    # ------------------------------------------------------------------
    section("PHASE 4 - PERCENTILE x ECONOMIC FLOOR MATRIX (median K across sets)")
    floors = ("", "_ge1xC", "_ge2xC", "_ge3xC", "_ge5xC", "_ge10xC")
    print(f"{'percentile':<12} " + " ".join(f"{name or 'no floor':>10}" for name in
          ("no floor", "1xC", "2xC", "3xC", "5xC", "10xC")))
    for percent in ("2.5", "5", "7.5", "10", "15", "20"):
        cells = []
        for floor in floors:
            ks, empties = [], 0
            for entry in sets:
                rule = next((r for r in entry["singleRules"]
                             if r["ruleKey"] == f"top{percent}pct_ceil{floor}"), None)
                if rule:
                    ks.append(rule["selectedK"])
                    empties += int(rule["selectedK"] == 0)
            label = f"{median(ks):g}" if ks else "-"
            if empties:
                label += f"({empties}e)"
            cells.append(label.rjust(10))
        print(f"top {percent + '%':<8} " + " ".join(cells))
    print("\n(median selected K across the 21 sets; (Ne) = N sets produced an EMPTY tier)")
    print()

    # ------------------------------------------------------------------
    section("PHASE 6/7 - NON-PERCENTILE FAMILIES: median K and where they cut")
    print(f"{'rule':<22} {'medK':>6} {'minK':>5} {'maxK':>5} {'med minValue$':>14} "
          f"{'sets below pack':>16}")
    for key in ("log_zscore_ge2", "log_zscore_ge3", "ge10x_median", "ge25x_median",
                "ge5x_q75", "ge10x_q75", "ge10pct_of_top", "ge25pct_of_top",
                "ge33pct_of_top", "ge50pct_of_top"):
        rows = rule_rows(report, key)
        if not rows:
            continue
        ks = [rule["selectedK"] for _, rule in rows]
        lows = [rule["minimumQualifyingValue"] for _, rule in rows
                if rule["minimumQualifyingValue"] is not None]
        below = sum(1 for entry, rule in rows
                    if rule["minimumQualifyingValue"] is not None
                    and entry["acquisitionCost"]["packEquivalentCost"]
                    and rule["minimumQualifyingValue"] < entry["acquisitionCost"]["packEquivalentCost"])
        print(f"{key:<22} {median(ks):>6g} {min(ks):>5} {max(ks):>5} "
              f"{f(median(lows) if lows else None, '.2f'):>14} {below:>16}")
    print()

    # ------------------------------------------------------------------
    section("PHASE 11 - SET-SIZE ROBUSTNESS: does a percentage track set size?")
    print(f"{'set':<26} {'elig':>5} {'top5%K':>7} {'top5%+2xC':>10} {'top15%K':>8} "
          f"{'top15%+2xC':>11}")
    sizes, k5, k5f = [], [], []
    for entry in sorted(sets, key=lambda e: e["universe"]["eligiblePrintings"]):
        def k(key):
            rule = next((r for r in entry["singleRules"] if r["ruleKey"] == key), None)
            return rule["selectedK"] if rule else None
        n = entry["universe"]["eligiblePrintings"]
        sizes.append(n); k5.append(k("top5pct_ceil")); k5f.append(k("top5pct_ceil_ge2xC"))
        print(f"{entry['setName'][:25]:<26} {n:>5} {f(k('top5pct_ceil'), 'd'):>7} "
              f"{f(k('top5pct_ceil_ge2xC'), 'd'):>10} {f(k('top15pct_ceil'), 'd'):>8} "
              f"{f(k('top15pct_ceil_ge2xC'), 'd'):>11}")
    print(f"\nSpearman(eligible size, top5% K)        = {f(spearman(sizes, k5), '+.3f')}")
    print(f"Spearman(eligible size, top5%+2xC K)    = {f(spearman(sizes, k5f), '+.3f')}")
    print("A pure percentage is pinned to set size by construction; the floor is what")
    print("lets K respond to the set's economics instead.")
    print()

    # ------------------------------------------------------------------
    section("PHASE 9 - PRICE-SHOCK STABILITY (mean Core Jaccard)")
    print(f"{'system':<18} " + " ".join(f"{m:>9}" for m in
          ("ind2%", "ind5%", "ind10%", "ind20%", "joint10%", "cost10%", "cost20%")))
    stability_scores: Dict[str, float] = {}
    for key in HEADLINE_SYSTEMS:
        cells, worst = [], []
        for kind, magnitude in (("independentPriceShock", "2pct"),
                                ("independentPriceShock", "5pct"),
                                ("independentPriceShock", "10pct"),
                                ("independentPriceShock", "20pct"),
                                ("jointPriceShock", "10pct"),
                                ("packCostShock", "10pct"),
                                ("packCostShock", "20pct")):
            values = [entry["priceShockStability"][kind][magnitude][key]["coreJaccardMean"]
                      for entry in sets
                      if key in entry["priceShockStability"][kind][magnitude]]
            values = [v for v in values if v is not None]
            mean = sum(values) / len(values) if values else None
            cells.append(f(mean, ".3f").rjust(9))
            if kind == "independentPriceShock" and magnitude == "10pct" and mean is not None:
                stability_scores[key] = mean
            worst.extend(values)
        print(f"{key:<18} " + " ".join(cells))
    print()

    # ------------------------------------------------------------------
    section("PHASE 10 - TEMPORAL STABILITY (weekly, consecutive Core Jaccard)")
    first = sets[0].get("temporalStability") or {}
    if first.get("status") != "SCORED":
        print(f"temporal status: {first.get('status')}")
    else:
        print(f"window {first['firstDate']} -> {first['lastDate']}, "
              f"{first['dateCount']} weekly snapshots")
        print(f"limitation: {first['limitation']}")
        print()
        print(f"{'system':<18} {'consecJacc':>11} {'endpointJacc':>13} {'coreKmin':>9} "
              f"{'coreKmax':>9} {'core->ext':>10} {'ext->non':>9}")
        for key in HEADLINE_SYSTEMS:
            rows = [entry["temporalStability"]["systems"][key] for entry in sets
                    if (entry.get("temporalStability") or {}).get("status") == "SCORED"]
            if not rows:
                continue
            print(f"{key:<18} "
                  f"{sum(r['consecutiveCoreJaccardMean'] for r in rows) / len(rows):>11.3f} "
                  f"{sum((r['endpointCoreJaccard'] or 0) for r in rows) / len(rows):>13.3f} "
                  f"{min(r['coreKMin'] for r in rows):>9} {max(r['coreKMax'] for r in rows):>9} "
                  f"{sum(r['coreToExtendedTransitions'] for r in rows):>10} "
                  f"{sum(r['extendedToNonChaseTransitions'] for r in rows):>9}")
    print()

    # ------------------------------------------------------------------
    section("PHASE 12/13/14 - TIER ECONOMICS for the headline systems")
    for key in ("B_pct_floor", "C_tight", "D_wide", "A_pct_only"):
        rows = system_rows(report, key)
        if not rows:
            continue
        print(f"--- {key}: {rows[0][1]['describe']}")
        print(f"{'set':<26} {'coreK':>6} {'extK':>5} {'corePs':>8} {'totPs':>8} "
              f"{'coreEVret':>10} {'totEVret':>9} {'coreShare':>10} {'totShare':>9} "
              f"{'BTB':>7} {'medGap$':>8} {'effEV':>6}")
        for entry, system in sorted(rows, key=lambda r: r[0]["setName"]):
            core, total = system["core"], system["coreAndExtended"]
            ce = core.get("chaseEv") or {}
            te = total.get("chaseEv") or {}
            print(f"{entry['setName'][:25]:<26} {system['coreCount']:>6} "
                  f"{system['extendedTotalCount']:>5} "
                  f"{f(core.get('anyChaseProbability'), '.5f'):>8} "
                  f"{f(total.get('anyChaseProbability'), '.5f'):>8} "
                  f"{f(ce.get('chaseEvReturn'), '.3f'):>10} "
                  f"{f(te.get('chaseEvReturn'), '.3f'):>9} "
                  f"{f(ce.get('chaseEvShareOfTotalEv'), '.3f'):>10} "
                  f"{f(te.get('chaseEvShareOfTotalEv'), '.3f'):>9} "
                  f"{f((total.get('beatTheBuy') or {}).get('closedForm'), '.4f'):>7} "
                  f"{f((total.get('chaseCostGap') or {}).get('medianGap'), '.0f'):>8} "
                  f"{f((total.get('depth') or {}).get('effectiveEvCount'), '.2f'):>6}")
        print()

    # ------------------------------------------------------------------
    section("PHASE 12 - LITERAL CHASE COUNT vs EFFECTIVE CHASE DEPTH (system B)")
    print(f"{'set':<26} {'totalK':>7} {'effEV':>7} {'ratio':>7} {'effValue':>9} {'effProb':>8}")
    ks, effs = [], []
    for entry, system in sorted(system_rows(report, "B_pct_floor"),
                                key=lambda r: r[0]["setName"]):
        depth = (system["coreAndExtended"].get("depth") or {})
        k = system["extendedTotalCount"]
        eff = depth.get("effectiveEvCount")
        if k and eff:
            ks.append(k); effs.append(eff)
        print(f"{entry['setName'][:25]:<26} {k:>7} {f(eff, '.2f'):>7} "
              f"{f(eff / k if (k and eff) else None, '.3f'):>7} "
              f"{f(depth.get('effectiveValueCount'), '.2f'):>9} "
              f"{f(depth.get('effectiveProbabilityCount'), '.2f'):>8}")
    print(f"\nSpearman(literal K, effective EV count) = {f(spearman(ks, effs), '+.3f')}")
    print()

    # ------------------------------------------------------------------
    section("PHASE 15 - REDUNDANCY: tier metrics vs EV-related measures (system B)")
    rows = system_rows(report, "B_pct_floor")
    metrics: Dict[str, List[Optional[float]]] = {
        "totEVret": [], "coreEVret": [], "totShare": [], "BTB": [],
        "medGap": [], "effEV": [], "fullEVret": [], "packCost": [], "totK": [],
    }
    for entry, system in rows:
        total = system["coreAndExtended"]
        te = total.get("chaseEv") or {}
        metrics["totEVret"].append(te.get("chaseEvReturn"))
        metrics["coreEVret"].append((system["core"].get("chaseEv") or {}).get("chaseEvReturn"))
        metrics["totShare"].append(te.get("chaseEvShareOfTotalEv"))
        metrics["BTB"].append((total.get("beatTheBuy") or {}).get("closedForm"))
        metrics["medGap"].append((total.get("chaseCostGap") or {}).get("medianGap"))
        metrics["effEV"].append((total.get("depth") or {}).get("effectiveEvCount"))
        metrics["fullEVret"].append(te.get("fullPackEvReturn"))
        metrics["packCost"].append(entry["acquisitionCost"]["packEquivalentCost"])
        metrics["totK"].append(system["extendedTotalCount"])
    names = list(metrics)
    print(f"{'':<12}" + "".join(f"{n[:10]:>11}" for n in names))
    for a in names:
        print(f"{a:<12}" + "".join(f"{f(spearman(metrics[a], metrics[b]), '+.3f'):>11}"
                                   for b in names))
    print()

    # ------------------------------------------------------------------
    section("PHASE 16 - RULE-QUALITY SCORECARD (all candidate systems)")
    print("Dimensions are reported side by side and NOT collapsed into one score:")
    print("  scaleInv  mean Core Jaccard under a JOINT (market-wide) 10% shift; 1.000 = scale-free")
    print("  shock10   mean Core Jaccard under INDEPENDENT 10% per-card noise")
    print("  costShock mean Core Jaccard under a 10% pack-cost move")
    print("  temporal  mean consecutive-week Core Jaccard")
    print("  sizeRho   |Spearman(eligible set size, Core K)|; lower = less pinned to set size")
    print("  econSig   share of sets whose Core floor is at or above one pack price")
    print("  coverage  share of sets that get a non-empty Core")
    print("  heroK     Core K on the two hero sets (Phantasmal Flames / Paldean Fates)")
    print("  weakFake  sets where the Core dips BELOW one pack price (false chases)")
    print("  depthOK   share of sets where effective EV count < literal K (depth is informative)")
    print()

    def scorecard_row(key: str) -> Optional[Dict[str, Any]]:
        rows = system_rows(report, key)
        if not rows:
            return None
        core_k, sizes, econ, fake, cover, depth_ok = [], [], 0, 0, 0, 0
        for entry, system in rows:
            cost = entry["acquisitionCost"]["packEquivalentCost"]
            k = system["coreCount"]
            core_k.append(k)
            sizes.append(entry["universe"]["eligiblePrintings"])
            low = system["boundary"]["coreMinimumValue"]
            if k > 0:
                cover += 1
                if low is not None and cost:
                    if low >= cost:
                        econ += 1
                    else:
                        fake += 1
            depth = (system["coreAndExtended"].get("depth") or {})
            eff = depth.get("effectiveEvCount")
            total_k = system["extendedTotalCount"]
            if eff is not None and total_k and eff < total_k:
                depth_ok += 1

        def shock(kind: str, magnitude: str) -> Optional[float]:
            values = [entry["priceShockStability"][kind][magnitude][key]["coreJaccardMean"]
                      for entry, _ in rows
                      if key in entry["priceShockStability"][kind][magnitude]]
            values = [v for v in values if v is not None]
            return sum(values) / len(values) if values else None

        temporal_values = [
            entry["temporalStability"]["systems"][key]["consecutiveCoreJaccardMean"]
            for entry, _ in rows
            if (entry.get("temporalStability") or {}).get("status") == "SCORED"
        ]
        hero = []
        for hero_name in ("Phantasmal Flames", "Paldean Fates"):
            match = next((s for e, s in rows if e["setName"] == hero_name), None)
            hero.append(str(match["coreCount"]) if match else "-")
        n = len(rows)
        rho = spearman(sizes, core_k)
        return {
            "key": key, "describe": rows[0][1]["describe"],
            "medianCoreK": median(core_k), "minCoreK": min(core_k), "maxCoreK": max(core_k),
            "scaleInv": shock("jointPriceShock", "10pct"),
            "shock10": shock("independentPriceShock", "10pct"),
            "costShock": shock("packCostShock", "10pct"),
            "temporal": (sum(temporal_values) / len(temporal_values)
                         if temporal_values else None),
            "sizeRho": None if rho is None else abs(rho),
            "econSig": econ / n, "coverage": cover / n, "weakFake": fake,
            "heroK": "/".join(hero), "depthOK": depth_ok / n,
        }

    all_keys = [system["systemKey"] for system in sets[0]["tierSystems"]]
    scorecards = [row for row in (scorecard_row(k) for k in all_keys) if row]
    header = (f"{'system':<20} {'medK':>5} {'Kmin':>5} {'Kmax':>5} {'scaleInv':>9} "
              f"{'shock10':>8} {'costShk':>8} {'temporal':>9} {'sizeRho':>8} "
              f"{'econSig':>8} {'cover':>7} {'weakFake':>9} {'heroK':>7} {'depthOK':>8}")
    print(header)
    print("-" * len(header))
    ordered_cards = sorted(scorecards, key=lambda r: (-(r["econSig"]), -(r["shock10"] or 0)))
    for row in ordered_cards:
        print(f"{row['key']:<20} {row['medianCoreK']:>5g} {row['minCoreK']:>5} "
              f"{row['maxCoreK']:>5} {f(row['scaleInv']):>9} {f(row['shock10']):>8} "
              f"{f(row['costShock']):>8} {f(row['temporal']):>9} {f(row['sizeRho']):>8} "
              f"{row['econSig']:>8.2f} {row['coverage']:>7.2f} {row['weakFake']:>9} "
              f"{row['heroK']:>7} {row['depthOK']:>8.2f}")
    print()

    # ------------------------------------------------------------------
    section("PHASE 19 - ASCENDED HEROES vs POKEMON 151 (system B)")
    for name in ("Ascended Heroes", "Scarlet and Violet 151"):
        entry = next((e for e in sets if e["setName"] == name), None)
        if not entry:
            continue
        system = next(s for s in entry["tierSystems"] if s["systemKey"] == "B_pct_floor")
        core, total = system["core"], system["coreAndExtended"]
        print(f"--- {name}  pack ${entry['acquisitionCost']['packEquivalentCost']:.2f}  "
              f"eligible {entry['universe']['eligiblePrintings']}")
        print(f"    Core K={system['coreCount']}  Extended total K={system['extendedTotalCount']}")
        print("    Core cards: " + ", ".join(
            f"{c['cardName'][:20]} ${c['marketPrice']:.0f}" for c in system["coreCards"][:8]))
        print(f"    Core   p={f(core.get('anyChaseProbability'), '.5f')} "
              f"EVret={f((core.get('chaseEv') or {}).get('chaseEvReturn'))} "
              f"share={f((core.get('chaseEv') or {}).get('chaseEvShareOfTotalEv'))} "
              f"BTB={f((core.get('beatTheBuy') or {}).get('closedForm'), '.4f')} "
              f"effEV={f((core.get('depth') or {}).get('effectiveEvCount'), '.2f')}")
        print(f"    Total  p={f(total.get('anyChaseProbability'), '.5f')} "
              f"EVret={f((total.get('chaseEv') or {}).get('chaseEvReturn'))} "
              f"share={f((total.get('chaseEv') or {}).get('chaseEvShareOfTotalEv'))} "
              f"BTB={f((total.get('beatTheBuy') or {}).get('closedForm'), '.4f')} "
              f"effEV={f((total.get('depth') or {}).get('effectiveEvCount'), '.2f')}")
        gap = total.get("chaseCostGap") or {}
        print(f"    Gap    median=${f(gap.get('medianGap'), '.0f')} "
              f"medSpend=${f(gap.get('medianSpendToFirstChase'), '.0f')} "
              f"medY=${f(gap.get('medianChaseValueObtained'), '.0f')} "
              f"P(gap<=0)={f(gap.get('probabilityGapAtMostZero'), '.4f')}")
        horizons = total.get("horizons") or {}
        if horizons.get("50"):
            print(f"    50% chase spend = ${f(horizons['50'].get('spendWhole'), '.0f')} "
                  f"({horizons['50'].get('packsWhole')} packs)")
        print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
