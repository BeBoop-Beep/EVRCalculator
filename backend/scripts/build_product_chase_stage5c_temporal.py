"""Stage V-C Phase 16: dated product costs for the temporal replay.

RESEARCH ONLY. Writes ``docs/research/product_chase_stage5c_temporal.json`` and
touches no production table, score, ranking snapshot, endpoint or schema.

    python -m backend.scripts.build_product_chase_stage5c_temporal

WHY THIS IS A SEPARATE, SMALL BUILD
-----------------------------------
The Phase-16 question is whether the thing Stage V-C introduces - the
product-native denominator ``C = product_market_cost / random_pack_count`` -
is stable enough for tier membership to mean anything. That question needs one
cheap table read per observed ``price_as_of`` day. It does NOT need the set
re-simulated per day: the recorded pack paths and the card price vector are held
fixed on purpose, so that any membership churn reported by the replay is
attributable to product-cost movement and to nothing else.

Card-price movement is not ignored; it is covered in closed form by the Phase-15
shock grid, whose +/-2/5/10/20% perturbations are strictly wider than the card
drift observable over a window this short.

THE WINDOW IS SHORT AND THE REPORT MUST SAY SO
----------------------------------------------
``simulation_sealed_product_results`` carries a fortnight of product costs, not
a release cycle. This build records the real dates it found rather than a
nominal window, so the analysis cannot quietly inherit a longer history than
exists.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Sequence

TAG = "[PRODUCT_CHASE_STAGE5C_TEMPORAL]"
ARTIFACT = Path("docs/research/product_chase_stage5c.json")
OUTPUT = Path("docs/research/product_chase_stage5c_temporal.json")

#: PostgREST caps a response at 1000 rows and times out on a wide unfiltered
#: scan of this table, so product ids are requested in batches.
BATCH = 60


def _rows(response: Any) -> List[Dict[str, Any]]:
    return list(getattr(response, "data", None) or [])


def dated_costs(client: Any, sealed_product_ids: Sequence[str]) -> List[Dict[str, Any]]:
    """Every dated cost observation for the Stage V-C product cohort."""
    collected: List[Dict[str, Any]] = []
    ids = list(sealed_product_ids)
    for start in range(0, len(ids), BATCH):
        chunk = ids[start:start + BATCH]
        collected.extend(_rows(
            client.table("simulation_sealed_product_results")
            .select("sealed_product_id,product_name,price_as_of,product_market_cost,"
                    "pack_count,random_pack_count,guaranteed_component_market_value")
            .in_("sealed_product_id", chunk)
            .limit(1000)
            .execute()))
        print(f"{TAG} batch {start // BATCH + 1} rows={len(collected)}", flush=True)
    return collected


def build(client: Any, *, artifact: Path) -> Dict[str, Any]:
    payload = json.loads(artifact.read_text(encoding="utf-8"))

    # setKey is the SET, because the frozen card price vector belongs to the set.
    set_of_product: Dict[str, str] = {}
    packs_of_product: Dict[str, Any] = {}
    price_vectors: Dict[str, List[float]] = {}
    for entry in payload["sets"]:
        price_vectors[entry["setName"]] = list(entry["universe"]["eligiblePrices"])
        for product in entry["products"]:
            key = str(product["sealedProductId"])
            set_of_product[key] = entry["setName"]
            packs_of_product[key] = product["randomPackCount"]

    raw = dated_costs(client, sorted(set_of_product))
    observations: List[Dict[str, Any]] = []
    skipped_unknown = 0
    for row in raw:
        key = str(row.get("sealed_product_id"))
        if key not in set_of_product:
            skipped_unknown += 1
            continue
        # Stage 1 products record no random_pack_count; all of their packs are
        # random, exactly as the main build resolves it. The pack COUNT is a
        # composition fact and does not move day to day, so where a dated row
        # omits it the cohort's verified value is used rather than pack_count.
        packs = row.get("random_pack_count")
        if packs is None and row.get("guaranteed_component_market_value") is None:
            packs = row.get("pack_count")
        if packs is None:
            packs = packs_of_product.get(key)
        observations.append({
            "setKey": set_of_product[key],
            "productKey": key,
            "productName": row.get("product_name"),
            "date": str(row.get("price_as_of"))[:10],
            "productMarketCost": row.get("product_market_cost"),
            "randomPackCount": packs,
        })

    dates = sorted({o["date"] for o in observations})
    return {
        "stage": "stage5c-phase16-temporal-product-costs-v1",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "sourceArtifact": str(artifact),
        "sourceMarketDate": payload["marketDate"],
        "cardPrices": "frozen_at_build_basis",
        "regime": "single_regime_only",
        "productCohortSize": len(set_of_product),
        "observationCount": len(observations),
        "skippedOutsideCohort": skipped_unknown,
        "dates": dates,
        "priceVectors": price_vectors,
        "observations": observations,
    }


def main(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(description="Stage V-C Phase 16 cost history.")
    parser.add_argument("--artifact", default=str(ARTIFACT))
    parser.add_argument("--output", default=str(OUTPUT))
    args = parser.parse_args(list(argv))

    from backend.db.clients.supabase_client import create_service_role_client

    payload = build(create_service_role_client(), artifact=Path(args.artifact))
    destination = Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    print(f"{TAG} wrote {destination} products={payload['productCohortSize']} "
          f"observations={payload['observationCount']} dates={len(payload['dates'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
