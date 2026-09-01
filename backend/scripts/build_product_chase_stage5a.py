"""Stage V-A canonical economic Chase floor research build.

RESEARCH ONLY. Writes a JSON artifact under ``docs/research/`` and touches no
production table, score, ranking snapshot, endpoint or schema.

    python -m backend.scripts.build_product_chase_stage5a

Stage IV validated an economic floor at the SET level against the cheapest
verified pack-equivalent route. Stage V has to carry a floor onto individual
sealed products, whose pack-equivalent cost differs from the cheapest route by
up to 6.2x inside a single set. This build therefore evaluates every candidate
floor twice: once at set level on the Stage-IV cost basis (reproduction), and
once against every usable product route (survival).

Two deliberate methodology changes from Stage IV's temporal study:

* DAILY sampling over the true extent of ``card_variant_price_observations``
  rather than weekly over a fixed 91-day lookback. The observation history is
  shallower than Stage IV's lookback implied (it begins 2026-06-28), so the
  window is shorter but roughly 7x denser.
* A BALANCED PANEL. Only variants observed on every retained date are scored.
  Stage IV kept any date holding 50% of the widest coverage, which lets a card
  that is merely *unobserved* on one date read as a card that left the tier.
  Membership churn measured here is a price movement, not a coverage gap.

Pack cost is held at its market-date value across the temporal series: sealed
price history is a Stage V-B question and inventing it here would smuggle an
unvalidated cost basis into a floor decision.
"""

from __future__ import annotations

import argparse
import json
import statistics as st
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

TAG = "[PRODUCT_CHASE_STAGE5A]"
STAGE = "stage5a-canonical-economic-floor-v1"

#: Near-mint. The whole programme defines tier rules on NM prices.
NEAR_MINT_CONDITION_ID = "4f8d1181-670e-4aea-937c-4d98d2e531a6"

#: Variant ids per PostgREST request. ``card_variant_price_observations`` has no
#: set_id, so the cohort is addressed by variant id and chunked to stay inside
#: httpx's URL length limit.
VARIANT_CHUNK = 80

#: A date is scored only if it carries this share of the widest observed
#: coverage. Stricter than Stage IV's 0.5, for the reason in the module docstring.
COVERAGE_FLOOR = 0.90

#: Candidate floors, as multiples of pack-equivalent cost.
FLOORS: Tuple[float, ...] = (1.0, 1.5, 2.0, 3.0, 5.0, 10.0)

#: Core/Extended pairings carried forward from Stage IV's system grid.
PAIRS: Tuple[Tuple[float, float], ...] = ((2.0, 1.0), (3.0, 1.0), (5.0, 2.0), (10.0, 3.0))

#: Boundary bands for threshold-proximity occupancy.
BANDS: Tuple[float, ...] = (0.02, 0.05, 0.10, 0.20)

STAGE4_ARTIFACT = Path("docs/research/set_chase_tiers_stage4.json")
OUTPUT = Path("docs/research/product_chase_stage5a.json")


def _rows(response: Any) -> List[Dict[str, Any]]:
    return list(getattr(response, "data", None) or [])


def variants_for_run(client: Any, *, calculation_run_id: str, set_id: str) -> List[str]:
    """Drawable variant universe for one authoritative run.

    ``simulation_card_variant_pull_rates`` is the simulator's own entity list,
    so this is the same universe the Stage-IV tiers were drawn from rather than
    a second opinion assembled from the card tables.
    """
    found = set()
    page = 0
    while True:
        batch = _rows(
            client.table("simulation_card_variant_pull_rates")
            .select("card_variant_id")
            .eq("calculation_run_id", calculation_run_id)
            .eq("set_id", set_id)
            .range(page * 1000, page * 1000 + 999)
            .execute()
        )
        found.update(str(r["card_variant_id"]) for r in batch if r.get("card_variant_id"))
        if len(batch) < 1000:
            break
        page += 1
    return sorted(found)


def daily_prices(client: Any, *, variant_ids: Sequence[str], start: str,
                 end: str) -> Dict[str, Dict[str, float]]:
    """Return ``{captured_date: {card_variant_id: nm_market_price}}``, unfiltered."""
    observations: Dict[str, Dict[str, float]] = defaultdict(dict)
    identifiers = sorted({str(v) for v in variant_ids if v})
    for offset in range(0, len(identifiers), VARIANT_CHUNK):
        chunk = identifiers[offset:offset + VARIANT_CHUNK]
        page = 0
        while True:
            batch = _rows(
                client.table("card_variant_price_observations")
                .select("card_variant_id,market_price,captured_date")
                .in_("card_variant_id", chunk)
                .eq("condition_id", NEAR_MINT_CONDITION_ID)
                .gte("captured_date", start).lte("captured_date", end)
                .range(page * 1000, page * 1000 + 999)
                .execute()
            )
            for row in batch:
                try:
                    price = float(row["market_price"])
                except (TypeError, ValueError, KeyError):
                    continue
                if price > 0:
                    day = str(row.get("captured_date") or "")[:10]
                    observations[day][str(row["card_variant_id"])] = price
            if len(batch) < 1000:
                break
            page += 1
    return dict(observations)


def _jaccard(left: set, right: set) -> float:
    union = left | right
    return 1.0 if not union else len(left & right) / len(union)


def temporal_for_set(observations: Dict[str, Dict[str, float]],
                     pack_cost: float) -> Dict[str, Any]:
    """Daily balanced-panel membership stability for every candidate pair."""
    if not observations:
        return {"status": "NO_OBSERVATIONS"}
    widest = max(len(p) for p in observations.values())
    dates = sorted(d for d, p in observations.items() if len(p) >= COVERAGE_FLOOR * widest)
    if len(dates) < 5:
        return {"status": "INSUFFICIENT_DATES", "dateCount": len(dates)}

    panel = set(observations[dates[0]])
    for day in dates[1:]:
        panel &= set(observations[day])
    panel_ids = sorted(panel)

    out: Dict[str, Any] = {
        "status": "SCORED", "dateCount": len(dates), "firstDate": dates[0],
        "lastDate": dates[-1], "panelSize": len(panel_ids),
        "widestCoverage": widest, "droppedDates": len(observations) - len(dates),
        "packCostHeldAt": pack_cost, "systems": {},
    }
    for core_floor, ext_floor in PAIRS:
        core_sets: List[set] = []
        ext_sets: List[set] = []
        for day in dates:
            prices = observations[day]
            core_sets.append({v for v in panel_ids if prices[v] >= core_floor * pack_cost})
            ext_sets.append({v for v in panel_ids if prices[v] >= ext_floor * pack_cost})
        core_j = [_jaccard(core_sets[i], core_sets[i + 1]) for i in range(len(core_sets) - 1)]
        ext_j = [_jaccard(ext_sets[i], ext_sets[i + 1]) for i in range(len(ext_sets) - 1)]
        counts = [len(s) for s in core_sets]
        bands = {
            "%dpct" % int(b * 100): st.mean([
                sum(1 for v in panel_ids
                    if abs(observations[d][v] - core_floor * pack_cost)
                    <= b * core_floor * pack_cost)
                for d in dates
            ]) for b in BANDS
        }
        key = "core%gx_ext%gx" % (core_floor, ext_floor)
        out["systems"][key] = {
            "coreJaccardMean": st.mean(core_j), "coreJaccardMin": min(core_j),
            "extendedJaccardMean": st.mean(ext_j),
            "coreKMin": min(counts), "coreKMax": max(counts),
            "coreKMedian": st.median(counts),
            "endpointCoreJaccard": _jaccard(core_sets[0], core_sets[-1]),
            "coreExits": sum(len(core_sets[i] - core_sets[i + 1])
                             for i in range(len(core_sets) - 1)),
            "emptyCoreDates": sum(1 for k in counts if k == 0),
            "singletonCoreDates": sum(1 for k in counts if k == 1),
            "boundaryOccupancy": bands,
        }
    return out


def product_survival(prices: Sequence[float],
                     routes: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Tier size for every usable product route at its OWN pack-equivalent cost.

    This is the test Stage IV could not run: a floor calibrated on the cheapest
    route in a set says nothing about that same floor applied to a Pokemon Center
    ETB in the same set at six times the per-pack cost.
    """
    usable = [r for r in routes if r.get("usable") and r.get("packEquivalentCost")]
    if not usable:
        return []
    cheapest = min(r["packEquivalentCost"] for r in usable)
    out: List[Dict[str, Any]] = []
    for route in usable:
        cost = float(route["packEquivalentCost"])
        record: Dict[str, Any] = {
            "sealedProductId": route.get("sealedProductId"),
            "productName": route.get("productName"),
            "productFamily": route.get("productFamily"),
            "productPrice": route.get("productPrice"),
            "randomPackCount": route.get("randomPackCount"),
            "packEquivalentCost": cost,
            "cheapestRouteCost": cheapest,
            "costRatioToCheapest": round(cost / cheapest, 4) if cheapest else None,
        }
        for floor in FLOORS:
            record["k%gx" % floor] = sum(1 for p in prices if p >= floor * cost)
        out.append(record)
    return out


def build(client: Any, *, start: str, end: str) -> Dict[str, Any]:
    stage4 = json.loads(STAGE4_ARTIFACT.read_text(encoding="utf-8"))
    sets_out: List[Dict[str, Any]] = []
    for entry in stage4.get("sets", []):
        name = entry.get("setName")
        acquisition = entry.get("acquisitionCost") or {}
        cost = acquisition.get("packEquivalentCost")
        if not cost:
            print("%s skip %s: no pack cost" % (TAG, name), flush=True)
            continue
        variant_ids = variants_for_run(
            client, calculation_run_id=entry["calculationRunId"], set_id=entry["setId"])
        observations = daily_prices(client, variant_ids=variant_ids, start=start, end=end)
        latest = max(observations) if observations else None
        prices = sorted(observations.get(latest, {}).values(), reverse=True) if latest else []
        record = {
            "setId": entry["setId"], "setName": name,
            "canonicalKey": entry.get("canonicalKey"),
            "calculationRunId": entry["calculationRunId"],
            "stage4PackEquivalentCost": cost,
            "stage4ChosenProduct": acquisition.get("chosenProductName"),
            "variantUniverse": len(variant_ids),
            "latestPricedDate": latest,
            "setLevelK": {"k%gx" % f: sum(1 for p in prices if p >= f * cost) for f in FLOORS},
            "temporal": temporal_for_set(observations, cost),
            "products": product_survival(prices, acquisition.get("routes") or []),
        }
        sets_out.append(record)
        print("%s %s: variants=%d dates=%s products=%d" % (
            TAG, name, len(variant_ids),
            record["temporal"].get("dateCount", 0), len(record["products"])), flush=True)
    return {
        "stage": STAGE,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "observationWindow": {"start": start, "end": end},
        "coverageFloor": COVERAGE_FLOOR,
        "floors": list(FLOORS),
        "pairs": [list(p) for p in PAIRS],
        "setCount": len(sets_out),
        "productCount": sum(len(s["products"]) for s in sets_out),
        "sets": sets_out,
    }


def main(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(description="Stage V-A economic floor research build.")
    parser.add_argument("--start", default="2026-06-28",
                        help="first observation date (default: start of price history)")
    parser.add_argument("--end", default="2026-08-28",
                        help="last observation date (default: Stage-IV market date)")
    parser.add_argument("--output", default=str(OUTPUT))
    args = parser.parse_args(list(argv))

    from backend.db.clients.supabase_client import create_service_role_client

    payload = build(create_service_role_client(), start=args.start, end=args.end)
    destination = Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    print("%s wrote %s sets=%d products=%d" % (
        TAG, destination, payload["setCount"], payload["productCount"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
