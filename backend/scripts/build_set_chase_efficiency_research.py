"""Stage-I Set Chase Efficiency research build.

RESEARCH ONLY. Writes a JSON artifact under ``docs/research/`` and touches no
production table, score, ranking snapshot or API contract.

    python -m backend.scripts.build_set_chase_efficiency_research \
        --packs 1000000 --out docs/research/set_chase_efficiency_stage1.json

Cohort authority is ``resolve_research_cohort`` - the same freshness authority
``pokemon_rip_stats_service`` consumes - so the study analyses exactly the sets
whose authoritative simulation is current for the resolved market date, and a
stale set is reported rather than silently analysed at an older date.
"""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

TAG = "[SET_CHASE_EFFICIENCY_STAGE1]"

def _rows(response: Any) -> List[Dict[str, Any]]:
    return list((getattr(response, "data", None) or []))


def _positive(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number > 0.0 else None


def code_version() -> str:
    """The commit the artifact was produced from, so a result is traceable."""
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except Exception:
        return "unknown"


def resolve_pack_cost(client: Any, *, calculation_run_id: str,
                      market_date: str) -> Dict[str, Any]:
    """Cheapest VERIFIED pack-equivalent acquisition cost for one run.

    Uses the same authority and the same verification rule as the published
    card-level Chase Efficiency (``simulation_sealed_product_results``, price
    dated to the market date, composition verified, positive random pack count),
    so a set-level CE and a card-level CE are divided by the same denominator
    and remain commensurable.

    Every candidate route is returned, not just the winner, because "which
    product defines the cost" is a real sensitivity the study has to be able to
    show.
    """
    products = _rows(
        client.table("simulation_sealed_product_results")
        .select(
            "sealed_product_id,product_name,product_family,product_market_cost,"
            "pack_count,random_pack_count,guaranteed_component_market_value,"
            "composition_id,composition_version,price_as_of,price_source"
        )
        .eq("calculation_run_id", calculation_run_id)
        .eq("price_as_of", str(market_date)[:10])
        .execute()
    )
    routes: List[Dict[str, Any]] = []
    for row in products:
        random_count = row.get("random_pack_count")
        # A Stage 1 product has no guaranteed component, so all of its packs are
        # random and pack_count is the random pack count.
        stage1 = random_count is None and row.get("guaranteed_component_market_value") is None
        count = row.get("pack_count") if stage1 else random_count
        price = _positive(row.get("product_market_cost"))
        verified = bool(
            count and float(count) > 0
            and (stage1 or row.get("composition_id") or row.get("composition_version"))
        )
        if price is None or not verified:
            routes.append({
                "sealedProductId": row.get("sealed_product_id"),
                "productName": row.get("product_name"),
                "productFamily": row.get("product_family"),
                "packEquivalentCost": None,
                "usable": False,
                "reason": "unverified_composition" if price is not None else "no_product_price",
            })
            continue
        routes.append({
            "sealedProductId": row.get("sealed_product_id"),
            "productName": row.get("product_name"),
            "productFamily": row.get("product_family"),
            "productPrice": price,
            "randomPackCount": int(count),
            "packEquivalentCost": round(price / int(count), 6),
            "priceAsOf": row.get("price_as_of"),
            "priceSource": row.get("price_source"),
            "usable": True,
            "reason": None,
        })
    usable = [route for route in routes if route["usable"]]
    chosen = min(
        usable,
        key=lambda route: (route["packEquivalentCost"], str(route["sealedProductId"] or "")),
    ) if usable else None
    loose = [
        route for route in usable
        if str(route.get("productFamily") or "") in {"booster_pack", "loose_booster_pack"}
    ]
    return {
        "packEquivalentCost": chosen["packEquivalentCost"] if chosen else None,
        "chosenProductName": chosen["productName"] if chosen else None,
        "chosenProductFamily": chosen["productFamily"] if chosen else None,
        "loosePackPrice": min((r["packEquivalentCost"] for r in loose), default=None),
        "routes": routes,
        "unusableRouteCount": len(routes) - len(usable),
    }


def build(
    client: Any,
    *,
    market_date: Optional[str] = None,
    canonical_keys: Optional[Sequence[str]] = None,
    pack_count: int,
) -> Dict[str, Any]:
    from backend.db.services.ev_representativeness_service import resolve_research_cohort
    from backend.db.services.evr_input_preparation_service import EVRInputPreparationService
    from backend.jobs.evr_runner import _resolve_set_config
    from backend.research.set_chase_efficiency.runner import analyse_set
    from backend.research.set_chase_efficiency.version import (
        SET_CHASE_EFFICIENCY_CALCULATION_VERSION,
        SET_CHASE_EFFICIENCY_RESEARCH_VERSION,
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
                config, canonical_key, str(getattr(config, "SET_NAME", canonical_key))
            )
            cost_basis = resolve_pack_cost(
                client, calculation_run_id=target.calculation_run_id, market_date=day
            )
            result = analyse_set(
                config=config,
                dataframe=prepared["dataframe"],
                set_id=target.set_id,
                set_name=target.set_name,
                canonical_key=canonical_key,
                calculation_run_id=target.calculation_run_id,
                market_date=day,
                pack_cost=cost_basis["packEquivalentCost"],
                pack_cost_basis=cost_basis,
                pack_count=pack_count,
            )
            result["authoritativeRunPackCost"] = target.pack_cost
            result["authoritativeRunMeanPackValue"] = target.simulated_mean
            result["authoritativeRunSimulationCount"] = target.simulation_count
            sets.append(result)
            print(
                f"{TAG} [{index}/{len(targets)}] {target.set_name} "
                f"eligible={result['coverage']['eligibleChaseUniverse']} "
                f"cost={cost_basis['packEquivalentCost']} "
                f"{round(time.perf_counter() - set_started, 1)}s"
            )
        except Exception as error:  # research driver: one bad set must not lose the rest
            failures.append({
                "setName": target.set_name,
                "canonicalKey": target.canonical_key,
                "calculationRunId": target.calculation_run_id,
                "error": f"{type(error).__name__}: {error}",
            })
            print(f"{TAG} [{index}/{len(targets)}] {target.set_name} FAILED: {error}")

    return {
        "researchVersion": SET_CHASE_EFFICIENCY_RESEARCH_VERSION,
        "calculationVersion": SET_CHASE_EFFICIENCY_CALCULATION_VERSION,
        "codeVersion": code_version(),
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "marketDate": day,
        "packCount": pack_count,
        "cohortSize": len(targets),
        "analysedSetCount": len(sets),
        "failures": failures,
        "totalSeconds": round(time.perf_counter() - started, 1),
        "sets": sets,
    }


def _resolve_market_date(client: Any) -> str:
    rows = _rows(
        client.table("pokemon_scrape_batches")
        .select("market_date,status,promoted_at")
        .eq("status", "complete")
        .not_.is_("promoted_at", "null")
        .order("market_date", desc=True)
        .limit(1)
        .execute()
    )
    if not rows:
        raise RuntimeError("no promoted complete market date could be resolved")
    return str(rows[0]["market_date"])[:10]


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--market-date", default=None)
    parser.add_argument("--sets", nargs="*", default=None, help="canonical keys; default all")
    parser.add_argument("--packs", type=int, default=1_000_000)
    parser.add_argument("--out", default="docs/research/set_chase_efficiency_stage1.json")
    args = parser.parse_args(argv)

    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    from backend.db.clients.supabase_client import create_service_role_client

    client = create_service_role_client()
    report = build(
        client,
        market_date=args.market_date,
        canonical_keys=args.sets,
        pack_count=args.packs,
    )
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"{TAG} wrote {out} sets={report['analysedSetCount']} failures={len(report['failures'])}")
    return 1 if report["failures"] else 0


if __name__ == "__main__":
    sys.exit(main())
