"""Stage VI Phases 23-24: price-shock and short-window temporal scenarios.

RESEARCH ONLY. Writes ``docs/research/chase_pillar_stage6_scenarios.json`` and
touches no production state.

    python -m backend.scripts.build_chase_pillar_stage6_scenarios

WHY THIS IS A SEPARATE, EXPENSIVE BUILD
---------------------------------------
Stage V-C could recompute a card-price shock in closed form because it only
needed tier MEMBERSHIP, which is a step function of price against a threshold.
Stage VI needs more than membership: ``anyChasePerProduct``, ``chaseSpend50``
and ``chaseEvReturn`` are all properties of the simulated pack paths, and no
algebra recovers them from a stored price vector.

So each set is simulated ONCE - the Stage V-C architecture, unchanged - and
every scenario is then evaluated against those same recorded pack paths. That
keeps the comparison controlled: a difference between the base scenario and a
+10% card shock is caused by the shock and by nothing else, with no Monte Carlo
noise between them. Re-simulating per scenario would have made the shock results
uninterpretable at the magnitudes being measured.

THE TWO SCENARIO KINDS
----------------------
* **shock** - card prices multiplied by ``cardFactor``, product costs by
  ``productFactor``. Both sides of the tier contract move, and the EV numerator
  moves with the card prices, which is why the prices are actually scaled rather
  than the threshold divided.
* **temporal** - the real dated ``product_market_cost`` observations from the
  Stage V-C temporal artifact, with card prices held at the build basis. This is
  a 13-day, 9-date, SINGLE-REGIME window. It is not long-term validation and the
  artifact records that in its own fields.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

import numpy as np

TAG = "[CHASE_PILLAR_STAGE6_SCENARIOS]"
DATASET = Path("docs/research/chase_pillar_stage6_dataset.json")
TEMPORAL = Path("docs/research/product_chase_stage5c_temporal.json")
OUTPUT = Path("docs/research/chase_pillar_stage6_scenarios.json")

SHOCKS = (0.02, 0.05, 0.10, 0.20)
DEFAULT_PACK_COUNT = 250_000



def _observed_price_date(frame):
    """Modal ``captured_at`` day across the prepared card rows.

    The scrape moves independently of the run's ``price_as_of``, so the basis
    must be read off the data every time rather than inherited from an artifact
    written on an earlier day.
    """
    from collections import Counter
    if frame is None or "captured_at" not in getattr(frame, "columns", []):
        return None
    days = [str(v)[:10] for v in frame["captured_at"].tolist()
            if str(v).strip() and str(v) != "nan"]
    return Counter(days).most_common(1)[0][0] if days else None


def shock_scenarios() -> List[Dict[str, Any]]:
    scenarios = [{"key": "base", "kind": "shock", "cardFactor": 1.0, "productFactor": 1.0}]
    for shock in SHOCKS:
        for sign in (1.0, -1.0):
            magnitude = 1.0 + sign * shock
            label = "%+d%%" % int(round(sign * shock * 100))
            scenarios.append({"key": "card%s" % label, "kind": "shock",
                              "cardFactor": magnitude, "productFactor": 1.0})
            scenarios.append({"key": "prod%s" % label, "kind": "shock",
                              "cardFactor": 1.0, "productFactor": magnitude})
    return scenarios


def _evaluate(*, decomposition, identities, prices, product_cost, random_pack_count,
              pack_independent, full_pack_values):
    """One product's Core-basket Chase candidates under one scenario."""
    from backend.research.product_chase_economics import contract as tier_contract
    from backend.research.product_chase_economics.runner import evaluate_product_basket

    pack_cost = tier_contract.pack_equivalent_cost(
        product_market_cost=product_cost, random_pack_count=random_pack_count)
    if pack_cost is None:
        return None
    basket = tier_contract.product_basket(identities, pack_cost)
    members = [e for e in identities if int(e.entity_id) in set(basket["coreEntityIds"])]
    result = evaluate_product_basket(
        decomposition=decomposition, prices=prices, entities=members,
        entity_ids=basket["coreEntityIds"], pack_cost=pack_cost,
        product_cost=product_cost, random_pack_count=random_pack_count,
        full_pack_values=full_pack_values, pack_independent=pack_independent)
    cost_view = ((result.get("accessibility") or {}).get("costNormalised") or {})
    return {
        "packEquivalentCost": pack_cost,
        "coreK": basket["coreCount"],
        "extK": basket["extendedCount"],
        "anyChasePerPack": result.get("packProbability"),
        "anyChasePerProduct": ((result.get("productProbability") or {})
                               .get("probabilityAtLeastOne")),
        "chaseSpend50": (cost_view.get("50") or {}).get("spendPackGranular"),
        "chaseEvReturn": ((result.get("productChaseEv") or {}).get("chaseEvReturn")),
    }


def build(client: Any, *, dataset: Path, temporal: Path,
          pack_count: int) -> Dict[str, Any]:
    from backend.db.services.ev_representativeness_service import resolve_research_cohort
    from backend.db.services.evr_input_preparation_service import EVRInputPreparationService
    from backend.jobs.evr_runner import _resolve_set_config
    from backend.research.set_chase_efficiency.baskets import partition_universe
    from backend.research.set_chase_efficiency.runner import entity_identities, simulate_set

    payload = json.loads(dataset.read_text(encoding="utf-8"))
    rows = payload["rows"]
    market_date = payload["marketDate"]

    by_set: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        by_set.setdefault(row["canonicalKey"], []).append(row)

    dated_costs: Dict[str, Dict[str, float]] = {}
    temporal_dates: List[str] = []
    if temporal.exists():
        history = json.loads(temporal.read_text(encoding="utf-8"))
        for observation in history["observations"]:
            if observation.get("productMarketCost") is None:
                continue
            dated_costs.setdefault(str(observation["date"])[:10], {})[
                str(observation["productKey"])] = float(observation["productMarketCost"])
        temporal_dates = sorted(dated_costs)
        print(f"{TAG} temporal dates={len(temporal_dates)}")

    scenarios = shock_scenarios()
    preparation = EVRInputPreparationService()
    targets = {t.canonical_key: t for t in resolve_research_cohort(
        client, market_date=market_date, canonical_keys=list(by_set))}

    observations: List[Dict[str, Any]] = []
    failures: List[Dict[str, Any]] = []
    started = time.perf_counter()

    for index, (canonical_key, group) in enumerate(sorted(by_set.items()), start=1):
        set_started = time.perf_counter()
        try:
            target = targets[canonical_key]
            config_cls, resolved_key = _resolve_set_config(canonical_key)
            config = config_cls()
            prepared = preparation.prepare_for_set(
                config, resolved_key, str(getattr(config, "SET_NAME", resolved_key)))
            run = simulate_set(config=config, dataframe=prepared["dataframe"],
                               calculation_run_id=target.calculation_run_id,
                               canonical_key=resolved_key, pack_count=pack_count)
            decomposition = run["decomposition"]
            identities = entity_identities(decomposition, run["dataframe"])
            basis = _observed_price_date(prepared["dataframe"]) or market_date
            eligible, excluded = partition_universe(identities, market_date=basis)
            if not eligible:
                raise RuntimeError(
                    "no eligible printings for %s at basis %s (%d excluded) - the "
                    "freshness filter would make every scenario report a Core of 0"
                    % (canonical_key, basis, len(excluded)))
            base_prices = decomposition.price_vector()

            for scenario in scenarios:
                prices = base_prices * float(scenario["cardFactor"])
                # The identity objects carry the price the tier contract reads,
                # so they are rebuilt per scenario rather than mutated in place.
                factor = float(scenario["cardFactor"])
                shocked = (eligible if factor == 1.0 else
                           [replace(e, price=float(e.price) * factor) for e in eligible])
                full_pack_values = decomposition.pack_values(prices)
                for row in group:
                    result = _evaluate(
                        decomposition=decomposition, identities=shocked, prices=prices,
                        product_cost=float(row["productMarketCost"])
                        * float(scenario["productFactor"]),
                        random_pack_count=int(row["randomPackCount"]),
                        pack_independent=True, full_pack_values=full_pack_values)
                    if result is None:
                        continue
                    observations.append({
                        "scenario": scenario["key"], "kind": "shock",
                        "sealedProductId": row["sealedProductId"], **result})

            if temporal_dates:
                full_pack_values = decomposition.pack_values(base_prices)
                for day in temporal_dates:
                    costs = dated_costs.get(day) or {}
                    for row in group:
                        cost = costs.get(row["sealedProductId"])
                        if cost is None:
                            continue
                        result = _evaluate(
                            decomposition=decomposition, identities=eligible,
                            prices=base_prices, product_cost=cost,
                            random_pack_count=int(row["randomPackCount"]),
                            pack_independent=True, full_pack_values=full_pack_values)
                        if result is None:
                            continue
                        observations.append({
                            "scenario": day, "kind": "temporal",
                            "sealedProductId": row["sealedProductId"], **result})

            print(f"{TAG} [{index}/{len(by_set)}] {canonical_key} "
                  f"products={len(group)} rows={len(observations)} "
                  f"{round(time.perf_counter() - set_started, 1)}s", flush=True)
        except Exception as error:  # research driver: one bad set must not lose the rest
            failures.append({"canonicalKey": canonical_key,
                             "error": f"{type(error).__name__}: {error}"})
            print(f"{TAG} [{index}/{len(by_set)}] {canonical_key} FAILED: {error}",
                  flush=True)

    return {
        "stage": "stage6-chase-pillar-scenarios-v1",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "marketDate": market_date,
        "packCount": pack_count,
        "architecture": "one simulation per set; every scenario shares those pack paths",
        "temporalRegime": "single_regime_only_13_day_9_date_window",
        "temporalCardPrices": "frozen_at_build_basis",
        "shockScenarios": [s["key"] for s in scenarios],
        "temporalDates": temporal_dates,
        "observationCount": len(observations),
        "failures": failures,
        "totalSeconds": round(time.perf_counter() - started, 1),
        "observations": observations,
    }


def main(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(description="Stage VI scenario build.")
    parser.add_argument("--dataset", default=str(DATASET))
    parser.add_argument("--temporal", default=str(TEMPORAL))
    parser.add_argument("--packs", type=int, default=DEFAULT_PACK_COUNT)
    parser.add_argument("--output", default=str(OUTPUT))
    args = parser.parse_args(list(argv))

    from backend.db.clients.supabase_client import create_service_role_client

    payload = build(create_service_role_client(), dataset=Path(args.dataset),
                    temporal=Path(args.temporal), pack_count=args.packs)
    destination = Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    print(f"{TAG} wrote {destination} observations={payload['observationCount']} "
          f"failures={len(payload['failures'])} {payload['totalSeconds']}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
