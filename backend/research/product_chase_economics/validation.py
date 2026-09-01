"""Stage V-C falsification apparatus: Phases 16, 17 and the central proof.

RESEARCH ONLY. Nothing here is read by production.

This module exists because the rest of Stage V-C can only show that the
framework PRODUCES numbers. These functions are the attempts to break it:

* :func:`temporal_replay` - does product-native tier membership survive the
  real observed movement in ``product_market_cost``?
* :data:`PATHOLOGICAL_CASES` - a data-driven catalogue of constructed products
  whose correct answer is known in advance, including the ones a naive
  implementation gets wrong (the 1-pack-vs-36-pack pair, the legitimately empty
  Core, the guaranteed-promo denominator).
* :func:`differentiation_report` / :func:`equivalence_classes` - the two halves
  of the central claim, measured over the real cohort rather than asserted.

THE CENTRAL CLAIM, STATED SO IT CAN FAIL
----------------------------------------
    Products from the same set produce DIFFERENT chase profiles for legitimate
    economic reasons, while economically EQUIVALENT products behave
    equivalently.

Both halves are needed and they pull against each other. A framework that
inherited a set constant would pass the second half trivially and fail the
first. A framework that re-simulated every SKU would pass the first half for an
illegitimate reason - Monte Carlo noise - and fail the second. Holding one
recorded pack sequence per set is what makes both halves testable at once, and
:func:`equivalence_classes` is the check a per-SKU-noise implementation cannot
pass.

WHAT "ECONOMICALLY EQUIVALENT" MEANS HERE
-----------------------------------------
Two products of the same set are equivalent when they share a pack-equivalent
cost ``C``, regardless of how many packs they contain. That is the exact
equivalence the contract implies, because every per-pack statistic and the
Chase EV Return depend on the product ONLY through ``C``:

    chaseEvReturn = (ev_pack * n) / (C * n) = ev_pack / C

Per-UNIT probability is deliberately NOT part of the equivalence: a 36-pack box
and a single pack at the same ``C`` must differ there, and
:func:`equivalence_classes` asserts that they do.
"""

from __future__ import annotations

import math
import statistics as st
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence

from backend.research.product_chase_economics import contract as tier_contract

#: ``C`` values within this many dollars are one equivalence class. Product
#: costs are recorded in cents, so this is a float-representation tolerance and
#: not an economic judgement.
COST_EPSILON = 1e-6


# --------------------------------------------------------------------------
# Shared primitives
# --------------------------------------------------------------------------

def membership(prices: Sequence[float], pack_cost: float,
               multiple: float = tier_contract.CORE_MULTIPLE) -> frozenset:
    """Indices of the price vector that qualify at ``multiple * pack_cost``.

    Indices, not identities, because the caller holds ONE price vector per set
    for the whole replay - the same card is the same index on every date, which
    is what makes a Jaccard between dates meaningful.
    """
    threshold = multiple * pack_cost
    return frozenset(i for i, price in enumerate(prices)
                     if tier_contract.finite_positive(price) is not None
                     and float(price) >= threshold)


def jaccard(left: Iterable, right: Iterable) -> float:
    """1.0 for two empty sets - two products with no Core agree completely."""
    a, b = set(left), set(right)
    union = a | b
    return 1.0 if not union else len(a & b) / len(union)


def spearman(x: Sequence[Any], y: Sequence[Any]) -> Optional[float]:
    """Rank correlation with AVERAGE ranks for ties.

    Tier counts tie constantly at product level; competition ranking would
    fabricate agreement between two vectors that are mostly ties.
    """
    pairs = [(a, b) for a, b in zip(x, y) if a is not None and b is not None]
    if len(pairs) < 3:
        return None

    def ranked(values: Sequence[float]) -> List[float]:
        order = sorted(range(len(values)), key=lambda i: values[i])
        out = [0.0] * len(values)
        position = 0
        while position < len(order):
            end = position
            while (end + 1 < len(order)
                   and values[order[end + 1]] == values[order[position]]):
                end += 1
            average = (position + end) / 2.0 + 1.0
            for index in order[position:end + 1]:
                out[index] = average
            position = end + 1
        return out

    a = ranked([p[0] for p in pairs])
    b = ranked([p[1] for p in pairs])
    ma, mb = st.mean(a), st.mean(b)
    num = sum((a[i] - ma) * (b[i] - mb) for i in range(len(a)))
    den = math.sqrt(sum((v - ma) ** 2 for v in a) * sum((v - mb) ** 2 for v in b))
    return num / den if den else None


# --------------------------------------------------------------------------
# Phase 16 - temporal validation
# --------------------------------------------------------------------------

def temporal_replay(*, price_vectors: Mapping[str, Sequence[float]],
                    observations: Sequence[Mapping[str, Any]],
                    baseline_date: Optional[str] = None) -> Dict[str, Any]:
    """Replay the tier contract against every observed product-cost date.

    ``price_vectors`` maps a set key to that set's eligible card prices, HELD
    FIXED across dates. ``observations`` are dated product costs, one row per
    (date, product), each carrying ``setKey``, ``productKey``, ``date``,
    ``productMarketCost`` and ``randomPackCount``.

    WHAT THIS DOES AND DOES NOT MEASURE
    -----------------------------------
    It measures the stability of the thing Stage V-C actually introduces: the
    product-native denominator. Card prices are deliberately frozen, so a flip
    reported here is attributable to product-cost movement alone and to nothing
    else. Card-price movement is covered separately and in closed form by the
    Phase-15 shock grid, whose perturbations are strictly wider than the card
    drift observable over a window this short.

    It is a SINGLE-REGIME check. The available product-cost history is a
    fortnight of one market state; nothing here is evidence of behaviour across
    a release cycle, a reprint or a crash, and the report must say so.
    """
    dated: Dict[str, Dict[str, Mapping[str, Any]]] = {}
    for row in observations:
        cost = tier_contract.finite_positive(row.get("productMarketCost"))
        packs = tier_contract.finite_positive(row.get("randomPackCount"))
        if cost is None or packs is None:
            continue
        if str(row.get("setKey")) not in price_vectors:
            continue
        dated.setdefault(str(row["date"])[:10], {})[str(row["productKey"])] = row

    dates = sorted(dated)
    if not dates:
        return {"supported": False, "reason": "no dated product costs", "dates": []}
    base_day = str(baseline_date)[:10] if baseline_date else dates[-1]
    if base_day not in dated:
        base_day = dates[-1]

    def profile(row: Mapping[str, Any]) -> Dict[str, Any]:
        prices = price_vectors[str(row["setKey"])]
        pack_cost = tier_contract.pack_equivalent_cost(
            product_market_cost=row["productMarketCost"],
            random_pack_count=row["randomPackCount"])
        return {
            "C": pack_cost,
            "core": membership(prices, pack_cost, tier_contract.CORE_MULTIPLE),
            "extended": membership(prices, pack_cost, tier_contract.EXTENDED_MULTIPLE),
        }

    baseline = {key: profile(row) for key, row in dated[base_day].items()}

    per_date: List[Dict[str, Any]] = []
    per_product: Dict[str, Dict[str, Any]] = {}
    for day in dates:
        core_j, ext_j, core_delta, flips, compared = [], [], [], 0, 0
        base_rank, day_rank = [], []
        for key, row in dated[day].items():
            reference = baseline.get(key)
            if reference is None:
                continue
            current = profile(row)
            compared += 1
            core_j.append(jaccard(current["core"], reference["core"]))
            ext_j.append(jaccard(current["extended"], reference["extended"]))
            core_delta.append(len(current["core"]) - len(reference["core"]))
            # A FLIP is the qualitative event: a product gaining or losing a
            # Core basket entirely. Churn inside a non-empty Core is a magnitude
            # change, not a change of verdict.
            if bool(current["core"]) != bool(reference["core"]):
                flips += 1
            base_rank.append(len(reference["core"]))
            day_rank.append(len(current["core"]))
            slot = per_product.setdefault(
                key, {"costs": [], "coreCounts": [], "dates": []})
            slot["costs"].append(current["C"])
            slot["coreCounts"].append(len(current["core"]))
            slot["dates"].append(day)
        if not compared:
            continue
        per_date.append({
            "date": day,
            "productsCompared": compared,
            "meanCoreJaccard": round(st.mean(core_j), 6),
            "minCoreJaccard": round(min(core_j), 6),
            "meanExtendedJaccard": round(st.mean(ext_j), 6),
            "meanCoreCountDelta": round(st.mean(core_delta), 4),
            "maxAbsoluteCoreCountDelta": max(abs(d) for d in core_delta),
            "coreExistenceFlips": flips,
            "coreCountRankStability": spearman(base_rank, day_rank),
        })

    volatility = []
    for key, slot in per_product.items():
        costs = slot["costs"]
        if len(costs) < 2 or st.mean(costs) <= 0:
            continue
        volatility.append({
            "productKey": key,
            "dates": len(costs),
            "packEquivalentCostCv": st.pstdev(costs) / st.mean(costs),
            "coreCountRange": max(slot["coreCounts"]) - min(slot["coreCounts"]),
        })
    volatility.sort(key=lambda row: -row["packEquivalentCostCv"])

    return {
        "supported": True,
        "reason": None,
        "regime": "single_regime_only",
        "cardPrices": "frozen_at_build_basis",
        "baselineDate": base_day,
        "dates": dates,
        "windowDays": _span_days(dates[0], dates[-1]),
        "perDate": per_date,
        "productVolatility": volatility,
        "worstProductCostCv": volatility[0] if volatility else None,
        "totalCoreExistenceFlips": sum(d["coreExistenceFlips"] for d in per_date),
    }


def _span_days(first: str, last: str) -> Optional[int]:
    from datetime import date
    try:
        return (date.fromisoformat(last[:10]) - date.fromisoformat(first[:10])).days
    except (TypeError, ValueError):
        return None


# --------------------------------------------------------------------------
# Phase 17 - the pathological catalogue
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class PathologicalCase:
    """A constructed product whose correct verdict is known before it is run.

    ``expectation`` receives the evaluated result and returns ``None`` when the
    case passes or a human-readable failure string. Expressing the case as data
    rather than as a bare test function is what lets one catalogue be both a
    pytest suite and a table in the published report.
    """

    key: str
    description: str
    prices: Sequence[float]
    product_market_cost: float
    random_pack_count: int
    expectation: Callable[[Dict[str, Any]], Optional[str]]
    pack_count: Optional[int] = None
    notes: str = ""
    peers: Sequence[str] = field(default_factory=tuple)


def evaluate_case(case: PathologicalCase) -> Dict[str, Any]:
    """The contract applied to one constructed product. No simulator needed.

    The pathological catalogue tests the TIER LAYER, which is a pure function of
    prices and cost. Deliberately not routed through a simulation: a case whose
    answer is known exactly should not be checked against a sampled number.
    """
    pack_cost = tier_contract.pack_equivalent_cost(
        product_market_cost=case.product_market_cost,
        random_pack_count=case.random_pack_count)
    core = (membership(case.prices, pack_cost, tier_contract.CORE_MULTIPLE)
            if pack_cost else frozenset())
    extended = (membership(case.prices, pack_cost, tier_contract.EXTENDED_MULTIPLE)
                if pack_cost else frozenset())
    return {
        "key": case.key,
        "packEquivalentCost": pack_cost,
        "coreThreshold": None if pack_cost is None else tier_contract.CORE_MULTIPLE * pack_cost,
        "extendedThreshold": None if pack_cost is None else tier_contract.EXTENDED_MULTIPLE * pack_cost,
        "core": core,
        "extended": extended,
        "coreCount": len(core),
        "extendedCount": len(extended),
        "randomPackCount": case.random_pack_count,
        "productMarketCost": case.product_market_cost,
    }


def run_catalogue(cases: Sequence[PathologicalCase] = ()) -> List[Dict[str, Any]]:
    """Evaluate every case and record pass/fail with the reason."""
    catalogue = list(cases) if cases else list(PATHOLOGICAL_CASES)
    by_key = {case.key: evaluate_case(case) for case in catalogue}
    results = []
    for case in catalogue:
        outcome = dict(by_key[case.key])
        # Peer cases are handed their partner's result so a case can assert a
        # RELATION - identical per-pack economics, a strictly wider basket -
        # rather than only a property of itself.
        outcome["peers"] = {peer: by_key[peer] for peer in case.peers if peer in by_key}
        failure = case.expectation(outcome)
        results.append({
            "key": case.key, "description": case.description,
            "passed": failure is None, "failure": failure,
            "packEquivalentCost": outcome["packEquivalentCost"],
            "coreCount": outcome["coreCount"],
            "extendedCount": outcome["extendedCount"],
            "notes": case.notes,
        })
    return results


#: A ladder of card prices reused by most cases, so that the only thing varying
#: between two cases is the PRODUCT, which is the point of the catalogue.
LADDER = (400.0, 120.0, 60.0, 30.0, 12.0, 6.0, 3.0, 1.0)


def _expect(**checks: Any) -> Callable[[Dict[str, Any]], Optional[str]]:
    def check(outcome: Dict[str, Any]) -> Optional[str]:
        for key, expected in checks.items():
            actual = outcome.get(key)
            if isinstance(expected, float):
                if actual is None or abs(float(actual) - expected) > 1e-9:
                    return "%s: expected %r, got %r" % (key, expected, actual)
            elif actual != expected:
                return "%s: expected %r, got %r" % (key, expected, actual)
        return None
    return check


def _all(*checks: Callable[[Dict[str, Any]], Optional[str]]
         ) -> Callable[[Dict[str, Any]], Optional[str]]:
    def check(outcome: Dict[str, Any]) -> Optional[str]:
        for one in checks:
            failure = one(outcome)
            if failure is not None:
                return failure
        return None
    return check


def _same_per_pack_as(peer_key: str) -> Callable[[Dict[str, Any]], Optional[str]]:
    """Same cost per pack, different size: per-pack economics must be identical."""
    def check(outcome: Dict[str, Any]) -> Optional[str]:
        peer = outcome["peers"].get(peer_key)
        if peer is None:
            return "peer %s missing" % peer_key
        if abs(outcome["packEquivalentCost"] - peer["packEquivalentCost"]) > COST_EPSILON:
            return "pack-equivalent cost differs from %s" % peer_key
        if outcome["core"] != peer["core"]:
            return "Core membership differs from %s despite equal cost per pack" % peer_key
        if outcome["randomPackCount"] == peer["randomPackCount"]:
            return "case is not a size contrast: both hold %d packs" % outcome["randomPackCount"]
        return None
    return check


def _strictly_wider_than(peer_key: str) -> Callable[[Dict[str, Any]], Optional[str]]:
    """A cheaper product must CONTAIN the dearer product's Core and extend it."""
    def check(outcome: Dict[str, Any]) -> Optional[str]:
        peer = outcome["peers"].get(peer_key)
        if peer is None:
            return "peer %s missing" % peer_key
        if outcome["packEquivalentCost"] >= peer["packEquivalentCost"]:
            return "case is not cheaper per pack than %s" % peer_key
        if not (peer["core"] <= outcome["core"]):
            return "cheaper product does not contain the dearer product's Core"
        if len(outcome["core"]) <= len(peer["core"]):
            return "cheaper product did not widen the Core"
        return None
    return check


def _strictly_narrower_than(peer_key: str) -> Callable[[Dict[str, Any]], Optional[str]]:
    """The mirror image, asserted from the dearer side of the same pair."""
    def check(outcome: Dict[str, Any]) -> Optional[str]:
        peer = outcome["peers"].get(peer_key)
        if peer is None:
            return "peer %s missing" % peer_key
        if outcome["packEquivalentCost"] <= peer["packEquivalentCost"]:
            return "case is not dearer per pack than %s" % peer_key
        if not (outcome["core"] <= peer["core"]):
            return "dearer product qualified a card the cheaper product did not"
        if len(outcome["core"]) >= len(peer["core"]):
            return "dearer product did not narrow the Core"
        return None
    return check


PATHOLOGICAL_CASES: Sequence[PathologicalCase] = (
    # A. Same pack composition, different shelf price. The whole point of V-C.
    PathologicalCase(
        key="A_same_packs_cheap",
        description="36 packs at $4.00/pack",
        prices=LADDER, product_market_cost=144.0, random_pack_count=36,
        expectation=_expect(packEquivalentCost=4.0, coreCount=5, extendedCount=6),
        notes="Core floor $12, Extended floor $4."),
    PathologicalCase(
        key="A_same_packs_dear",
        description="the SAME 36 packs at $10.00/pack",
        prices=LADDER, product_market_cost=360.0, random_pack_count=36,
        peers=("A_same_packs_cheap",),
        expectation=_all(_expect(packEquivalentCost=10.0, coreCount=4, extendedCount=5),
                         _strictly_narrower_than("A_same_packs_cheap")),
        notes="Identical packs, dearer box: strictly fewer cards clear 3x."),

    # B. Same cost per pack, 1 pack versus 36. Must be per-pack IDENTICAL.
    PathologicalCase(
        key="B_single_pack",
        description="one loose pack at $10.00",
        prices=LADDER, product_market_cost=10.0, random_pack_count=1,
        expectation=_expect(packEquivalentCost=10.0, coreCount=4, extendedCount=5)),
    PathologicalCase(
        key="B_thirty_six_packs",
        description="a 36-pack box at the same $10.00/pack",
        prices=LADDER, product_market_cost=360.0, random_pack_count=36,
        peers=("B_single_pack",), expectation=_same_per_pack_as("B_single_pack"),
        notes="Different unit accessibility, identical per-pack economics."),

    # C. Expensive LARGE product. Size must not buy a wider basket.
    PathologicalCase(
        key="C_expensive_large",
        description="a 36-pack box at $40.00/pack",
        prices=LADDER, product_market_cost=1440.0, random_pack_count=36,
        expectation=_expect(packEquivalentCost=40.0, coreCount=2, extendedCount=3),
        notes="Only $400 and $120 clear 3 x $40; being big did not help."),

    # D. Cheap SMALL product. Smallness must not be punished.
    PathologicalCase(
        key="D_cheap_small",
        description="a 2-pack sleeved product at $2.00/pack",
        prices=LADDER, product_market_cost=4.0, random_pack_count=2,
        peers=("C_expensive_large",),
        expectation=_all(_expect(packEquivalentCost=2.0),
                         _strictly_wider_than("C_expensive_large")),
        notes="Core floor $6: strictly contains the big box's Core and widens it."),

    # E. Threshold crossing. Inclusive at exactly the floor, exclusive below.
    PathologicalCase(
        key="E_exactly_on_the_floor",
        description="a cost placing one card EXACTLY on the 3x floor",
        prices=(60.0, 59.99), product_market_cost=200.0, random_pack_count=10,
        expectation=_expect(packEquivalentCost=20.0, coreCount=1, extendedCount=2),
        notes="60 >= 3 x 20 qualifies; 59.99 does not. The floor is inclusive."),

    # F. Hero-only Core: one card carries the entire basket.
    PathologicalCase(
        key="F_hero_only_core",
        description="a set whose only Core member is the chase hero",
        prices=(900.0, 9.0, 8.0, 7.0, 6.0), product_market_cost=360.0,
        random_pack_count=36,
        expectation=_expect(packEquivalentCost=10.0, coreCount=1, extendedCount=1),
        notes="A single-member Core is a valid verdict, not a degenerate basket."),

    # G. Legitimate NO-CORE product. Reported as a measured zero.
    PathologicalCase(
        key="G_no_core",
        description="a product so dear that no card is worth three of its packs",
        prices=(50.0, 20.0, 5.0), product_market_cost=3600.0, random_pack_count=36,
        expectation=_expect(packEquivalentCost=100.0, coreCount=0, extendedCount=0),
        notes="Zero, not missing. The correct economic answer for this product."),

    # H. Guaranteed-promo leakage. The denominator is RANDOM packs only.
    PathologicalCase(
        key="H_guaranteed_promo",
        description="an ETB of 11 random packs plus a guaranteed promo, $110",
        prices=LADDER, product_market_cost=110.0, random_pack_count=11, pack_count=12,
        peers=("B_single_pack",),
        expectation=_all(
            _expect(packEquivalentCost=10.0),
            lambda o: (None if o["core"] == o["peers"]["B_single_pack"]["core"]
                       else "promo pack leaked into the denominator")),
        notes="Dividing by 12 would give $9.17 and a wrongly wider Core."),
)


# --------------------------------------------------------------------------
# The central proof
# --------------------------------------------------------------------------

#: Fields that depend on the product ONLY through its pack-equivalent cost, and
#: must therefore be identical for two equivalent products of the same set.
COST_DETERMINED_FIELDS = ("coreK", "extK", "depth", "pPack", "evReturn", "evShare", "btb")

#: Fields that legitimately differ between equivalent products of different
#: sizes. Requiring these to be equal too would be requiring the framework to
#: ignore pack count, which is the opposite error.
SIZE_DETERMINED_FIELDS = ("pProduct", "packs")


def equivalence_classes(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """Group same-set products by pack-equivalent cost and check they agree.

    A violation here means a product-specific number leaked in from somewhere it
    should not have - per-SKU Monte Carlo noise being the archetype - and it
    falsifies the second half of the central claim.
    """
    groups: Dict[Any, List[Mapping[str, Any]]] = {}
    for row in rows:
        if row.get("C") is None:
            continue
        groups.setdefault((row["set"], round(float(row["C"]), 6)), []).append(row)

    multi = {key: group for key, group in groups.items() if len(group) >= 2}
    violations: List[Dict[str, Any]] = []
    size_contrasts = 0
    for key, group in multi.items():
        head = group[0]
        for other in group[1:]:
            for field_name in COST_DETERMINED_FIELDS:
                a, b = head.get(field_name), other.get(field_name)
                if a is None and b is None:
                    continue
                if a is None or b is None or abs(float(a) - float(b)) > 1e-9:
                    violations.append({
                        "set": key[0], "packEquivalentCost": key[1], "field": field_name,
                        "left": head.get("name"), "right": other.get("name"),
                        "leftValue": a, "rightValue": b})
            if head.get("packs") != other.get("packs"):
                size_contrasts += 1
                # The other half: same C, different size MUST differ per unit.
                if (head.get("pProduct") is not None
                        and other.get("pProduct") is not None
                        and head.get("pProduct") == other.get("pProduct")
                        and (head.get("pPack") or 0) > 0):
                    violations.append({
                        "set": key[0], "packEquivalentCost": key[1],
                        "field": "pProduct(must differ)", "left": head.get("name"),
                        "right": other.get("name"), "leftValue": head.get("pProduct"),
                        "rightValue": other.get("pProduct")})
    pairs = sum(len(g) - 1 for g in multi.values())
    return {
        "equivalencePairsFound": pairs,
        "classesWithMultipleProducts": len(multi),
        "sizeContrastPairs": size_contrasts,
        "violations": violations,
        # A cohort can simply contain no two same-set products at the same cost
        # per pack, which is what the real cohort turns out to look like. That
        # is NOT evidence that equivalence holds, and calling it "holds" would
        # be the exact kind of vacuous pass this stage is supposed to catch.
        "vacuous": pairs == 0,
        "holds": bool(pairs) and not violations,
    }


def near_equivalence(rows: Sequence[Mapping[str, Any]], *,
                     cost_tolerance: float = 0.01) -> Dict[str, Any]:
    """The non-vacuous companion to :func:`equivalence_classes`.

    Exact cost ties are rare in a live market, so this asks the continuous form
    of the same question: when two same-set products are within
    ``cost_tolerance`` of each other on cost per pack, how far apart do their
    cost-determined metrics get?

    Under the Stage V-C architecture the answer must be "barely", because a
    basket is a step function of ``C`` and the pack paths are shared. Under a
    per-SKU re-simulation it would be "by however much Monte Carlo noise
    happens to differ", which is what this measures and would expose.
    """
    by_set: Dict[str, List[Mapping[str, Any]]] = {}
    for row in rows:
        if row.get("C"):
            by_set.setdefault(row["set"], []).append(row)

    pairs: List[Dict[str, Any]] = []
    for name, group in by_set.items():
        ordered = sorted(group, key=lambda r: float(r["C"]))
        for i in range(len(ordered) - 1):
            left, right = ordered[i], ordered[i + 1]
            base = float(left["C"])
            separation = abs(float(right["C"]) - base) / base
            if separation > cost_tolerance:
                continue
            worst_field, worst = None, 0.0
            for field_name in COST_DETERMINED_FIELDS:
                a, b = left.get(field_name), right.get(field_name)
                if a is None or b is None:
                    continue
                scale = max(abs(float(a)), abs(float(b)), 1e-9)
                relative = abs(float(a) - float(b)) / scale
                if relative > worst:
                    worst, worst_field = relative, field_name
            pairs.append({
                "set": name, "left": left.get("name"), "right": right.get("name"),
                "costSeparation": separation, "worstField": worst_field,
                "worstRelativeDivergence": worst,
                "differentSize": left.get("packs") != right.get("packs"),
                "perUnitProbabilityDiffers": left.get("pProduct") != right.get("pProduct"),
            })
    pairs.sort(key=lambda p: -p["worstRelativeDivergence"])
    size_contrasts = [p for p in pairs if p["differentSize"]]
    return {
        "costTolerance": cost_tolerance,
        "pairsFound": len(pairs),
        "sizeContrastPairs": len(size_contrasts),
        "sizeContrastsThatDifferPerUnit": sum(
            1 for p in size_contrasts if p["perUnitProbabilityDiffers"]),
        "maxRelativeDivergence": pairs[0]["worstRelativeDivergence"] if pairs else None,
        "medianRelativeDivergence": (
            st.median([p["worstRelativeDivergence"] for p in pairs]) if pairs else None),
        "worstPairs": pairs[:5],
        "vacuous": not pairs,
    }


def differentiation_report(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """How much do same-set products actually differ, and does the reason hold?

    ``legitimate`` is the discipline: a difference is only legitimate if the two
    products differ in pack-equivalent cost. Two products sharing a ``C`` that
    nonetheless scored differently would be an illegitimate difference, and are
    counted separately rather than folded into the headline.
    """
    by_set: Dict[str, List[Mapping[str, Any]]] = {}
    for row in rows:
        by_set.setdefault(row["set"], []).append(row)

    differentiated, examined, spreads, illegitimate = 0, 0, [], 0
    per_set: List[Dict[str, Any]] = []
    for name, group in sorted(by_set.items()):
        if len(group) < 2:
            continue
        examined += 1
        costs = [float(g["C"]) for g in group if g.get("C") is not None]
        cores = {g.get("coreK") for g in group}
        distinct_costs = len({round(c, 6) for c in costs})
        if distinct_costs > 1:
            differentiated += 1
        elif len(cores) > 1:
            illegitimate += 1
        spread = (max(costs) / min(costs)) if costs and min(costs) > 0 else None
        if spread is not None:
            spreads.append(spread)
        per_set.append({
            "set": name, "products": len(group),
            "distinctPackEquivalentCosts": distinct_costs,
            "distinctCoreCounts": len(cores), "costSpreadRatio": spread,
            "cheapestPerPack": min(costs) if costs else None,
            "dearestPerPack": max(costs) if costs else None,
            "coreCountRange": (max(g["coreK"] for g in group)
                               - min(g["coreK"] for g in group)),
        })
    return {
        "setsExamined": examined,
        "setsWithDistinctProductCosts": differentiated,
        "setsWithIllegitimateDifference": illegitimate,
        "medianCostSpreadRatio": st.median(spreads) if spreads else None,
        "maxCostSpreadRatio": max(spreads) if spreads else None,
        "perSet": per_set,
        "holds": examined > 0 and differentiated == examined and illegitimate == 0,
    }
