"""Stage V-C native product-level Chase Economics research build.

RESEARCH ONLY. Writes a JSON artifact under ``docs/research/`` and touches no
production table, score, ranking snapshot, endpoint or schema.

    python -m backend.scripts.build_product_chase_stage5c --packs 250000

One set is simulated once, with ``PackDecompositionRecorder`` attached, and
every product belonging to that set is evaluated against those same recorded
pack paths. Products differ only where Stage V-C says they may: in their
acquisition cost, and therefore in their tier membership and their product
construction.

Cohort, market date and simulator are the Stage I-IV ones, so this artifact is
directly comparable with ``set_chase_tiers_stage4.json`` rather than merely
similar.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from backend.scripts.build_set_chase_efficiency_research import (
    _resolve_market_date,
    resolve_pack_cost,
)

TAG = "[PRODUCT_CHASE_STAGE5C]"
OUTPUT = Path("docs/research/product_chase_stage5c.json")

#: Enough packs for stable basket probabilities without a multi-hour run. Core
#: baskets sit around p ~ 0.01-0.05, so 250k packs give a standard error near
#: 4e-4 -- an order of magnitude below the effects being measured.
DEFAULT_PACK_COUNT = 250_000


def _observed_price_date(frame: Any) -> Optional[str]:
    """Modal ``captured_at`` day across the prepared card rows."""
    from collections import Counter
    if frame is None or "captured_at" not in getattr(frame, "columns", []):
        return None
    days = [str(v)[:10] for v in frame["captured_at"].tolist() if str(v).strip() and str(v) != "nan"]
    return Counter(days).most_common(1)[0][0] if days else None


def _rows(response: Any) -> List[Dict[str, Any]]:
    return list(getattr(response, "data", None) or [])


def products_for_run(client: Any, *, calculation_run_id: str,
                     market_date: str) -> List[Dict[str, Any]]:
    """Every scored product for one run, supported or not.

    Unsupported products are returned too, so the coverage audit can name them
    with a reason code rather than silently covering only the easy formats.
    """
    products = _rows(
        client.table("simulation_sealed_product_results")
        .select(
            "sealed_product_id,product_name,product_family,product_market_cost,"
            "pack_count,random_pack_count,guaranteed_component_market_value,"
            "composition_id,composition_version,price_as_of,price_source,"
            "pack_independence_assumption,expected_value"
        )
        .eq("calculation_run_id", calculation_run_id)
        .eq("price_as_of", str(market_date)[:10])
        .execute()
    )
    for row in products:
        # A Stage 1 product has no guaranteed component, so all of its packs are
        # random and pack_count IS the random pack count. Recorded explicitly so
        # the runner's verification branch does not have to re-derive it.
        stage1 = (row.get("random_pack_count") is None
                  and row.get("guaranteed_component_market_value") is None)
        row["stage1_all_random"] = stage1
        if stage1 and row.get("random_pack_count") is None:
            row["random_pack_count"] = row.get("pack_count")
    return products


def build(client: Any, *, market_date: Optional[str],
          canonical_keys: Optional[Sequence[str]], pack_count: int) -> Dict[str, Any]:
    from backend.db.services.ev_representativeness_service import resolve_research_cohort
    from backend.db.services.evr_input_preparation_service import EVRInputPreparationService
    from backend.jobs.evr_runner import _resolve_set_config
    from backend.research.product_chase_economics.runner import analyse_set_products
    from backend.research.product_chase_economics.version import (
        PRODUCT_CHASE_ECONOMICS_VERSION,
        PRODUCT_CHASE_TIER_CONTRACT,
    )

    day = str(market_date)[:10] if market_date else _resolve_market_date(client)
    targets = resolve_research_cohort(client, market_date=day, canonical_keys=canonical_keys)
    print(f"{TAG} market_date={day} cohort={len(targets)} packs={pack_count}")

    sets: List[Dict[str, Any]] = []
    failures: List[Dict[str, Any]] = []
    started = time.perf_counter()
    preparation = EVRInputPreparationService()

    for index, target in enumerate(targets, start=1):
        set_started = time.perf_counter()
        try:
            config_cls, canonical_key = _resolve_set_config(target.canonical_key)
            config = config_cls()
            prepared = preparation.prepare_for_set(
                config, canonical_key, str(getattr(config, "SET_NAME", canonical_key)))
            products = products_for_run(
                client, calculation_run_id=target.calculation_run_id, market_date=day)
            # Card prices come from the LATEST scrape, which need not be the
            # run's product price_as_of. Read the basis off the data instead of
            # assuming the two dates agree.
            basis = _observed_price_date(prepared["dataframe"]) or day
            result = analyse_set_products(
                config=config, dataframe=prepared["dataframe"], set_id=target.set_id,
                set_name=target.set_name, canonical_key=canonical_key,
                calculation_run_id=target.calculation_run_id, market_date=day,
                products=products, pack_count=pack_count, price_basis_date=basis)
            # The Stage-IV set-wide cheapest route, carried for the Phase-13
            # inheritance-error comparison ONLY. It is never a product attribute.
            result["setCheapestRoute"] = resolve_pack_cost(
                client, calculation_run_id=target.calculation_run_id, market_date=day)
            sets.append(result)
            print(f"{TAG} [{index}/{len(targets)}] {target.set_name} "
                  f"eligible={result['universe']['eligiblePrintings']} "
                  f"scored={len(result['products'])} "
                  f"unsupported={len(result['unsupportedProducts'])} "
                  f"{round(time.perf_counter() - set_started, 1)}s", flush=True)
        except Exception as error:  # research driver: one bad set must not lose the rest
            failures.append({
                "setName": target.set_name, "canonicalKey": target.canonical_key,
                "calculationRunId": target.calculation_run_id,
                "error": f"{type(error).__name__}: {error}"})
            print(f"{TAG} [{index}/{len(targets)}] {target.set_name} FAILED: {error}",
                  flush=True)

    return {
        "stage": "stage5c-native-product-chase-economics-v1",
        "researchVersion": PRODUCT_CHASE_ECONOMICS_VERSION,
        "tierContract": PRODUCT_CHASE_TIER_CONTRACT,
        "aggregationAssumption": "model_consistent_iid",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "marketDate": day,
        "packCount": pack_count,
        "setCount": len(sets),
        "scoredProductCount": sum(len(s["products"]) for s in sets),
        "unsupportedProductCount": sum(len(s["unsupportedProducts"]) for s in sets),
        "failures": failures,
        "totalSeconds": round(time.perf_counter() - started, 1),
        "sets": sets,
    }


def main(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(description="Stage V-C product chase research build.")
    parser.add_argument("--packs", type=int, default=DEFAULT_PACK_COUNT)
    parser.add_argument("--market-date", default=None)
    parser.add_argument("--sets", nargs="*", default=None,
                        help="canonical keys; default is the full research cohort")
    parser.add_argument("--output", default=str(OUTPUT))
    args = parser.parse_args(list(argv))

    from backend.db.clients.supabase_client import create_service_role_client

    payload = build(create_service_role_client(), market_date=args.market_date,
                    canonical_keys=args.sets, pack_count=args.packs)
    destination = Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    print(f"{TAG} wrote {destination} sets={payload['setCount']} "
          f"scored={payload['scoredProductCount']} "
          f"unsupported={payload['unsupportedProductCount']} "
          f"{payload['totalSeconds']}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
