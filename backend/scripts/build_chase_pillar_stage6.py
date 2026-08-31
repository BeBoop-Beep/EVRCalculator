"""Stage VI Phase 4: the aligned product-level analysis dataset.

RESEARCH ONLY. Writes ``docs/research/chase_pillar_stage6_dataset.json`` and
touches no production table, score, ranking snapshot, endpoint, schema or UI.

    python -m backend.scripts.build_chase_pillar_stage6

WHAT IS JOINED, AND ON WHAT
---------------------------
One row per scored Stage V-C product, carrying three families of numbers that
must be aligned on the same market state or the whole study is measuring a date
mismatch:

1. **Chase** - read from ``docs/research/product_chase_stage5c.json``, the
   validated Stage V-C artifact. Nothing is recomputed here; Stage VI consumes
   Stage V-C's output exactly as published.
2. **Financial** - ``financial_rip_v4_score`` and its six components, read from
   ``simulation_sealed_product_results`` for the SAME ``calculation_run_id``
   Stage V-C simulated, so the financial score and the chase metrics describe
   one run and not two.
3. **Collector** - Collector Appeal V5 from the live bundle, joined on
   ``set_id``. Collector Appeal is a SET-level score and is projected unchanged
   onto every product of that set, exactly as production's Overall RIP does.

DATE ALIGNMENT IS REPORTED, NOT ASSUMED
---------------------------------------
Three dates are in play: the product-cost ``price_as_of``, the card-price scrape
basis the simulator consumed, and the Collector Appeal ``asOf``. They are
recorded per row and summarized on the artifact. Stage V-C already found a
uniform 2-day card-vs-product skew; any further skew introduced by the appeal
bundle would be invisible if the join simply assumed one date.

THE COLLECTOR APPEAL PROJECTION IS A REAL LIMITATION
----------------------------------------------------
Because Collector Appeal is set-level, every product of one set carries an
IDENTICAL appeal score. Within a set, therefore, CONTROL is a strictly
increasing function of Financial RIP alone. This is production's behaviour, not
an artifact of the join, and it is the single most important fact about what a
third pillar would add: Chase is the only candidate that can separate two
products of the same set on anything other than money.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

TAG = "[CHASE_PILLAR_STAGE6]"
CHASE_ARTIFACT = Path("docs/research/product_chase_stage5c.json")
OUTPUT = Path("docs/research/chase_pillar_stage6_dataset.json")

#: PostgREST caps a page at 1000 rows; the cohort is far smaller but the batch
#: keeps the request bounded if the cohort grows.
BATCH = 60

FINANCIAL_COMPONENTS = (
    "true_win_frequency", "typical_retention", "loss_resilience",
    "realistic_upside", "jackpot_upside", "base_economic_efficiency",
)


def _rows(response: Any) -> List[Dict[str, Any]]:
    return list(getattr(response, "data", None) or [])


def _chase_rows(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Flatten the Stage V-C artifact into one row per product.

    Every Chase number here is read from the CORE basket, because Core is the
    tier the Stage V-C contract validated as the economic chase. Extended K is
    carried as a diagnostic only.
    """
    out: List[Dict[str, Any]] = []
    for entry in payload["sets"]:
        prices = entry["universe"].get("eligiblePrices") or []
        for product in entry["products"]:
            core = product["core"]
            accessibility = core.get("accessibility") or {}
            cost_view = accessibility.get("costNormalised") or {}
            product_ev = core.get("productChaseEv") or {}
            out.append({
                "sealedProductId": str(product["sealedProductId"]),
                "setId": entry["setId"],
                "set": entry["setName"],
                "canonicalKey": entry["canonicalKey"],
                "calculationRunId": entry["calculationRunId"],
                "productName": product["productName"],
                "family": product["productFamily"],
                "productMarketCost": product["productMarketCost"],
                "randomPackCount": product["randomPackCount"],
                "packEquivalentCost": product["tierContract"]["packEquivalentCost"],
                # --- Chase score candidates (Stage V-C survivors) ---
                "coreK": product["membership"]["coreCount"],
                "anyChasePerProduct": ((core.get("productProbability") or {})
                                       .get("probabilityAtLeastOne")),
                "chaseSpend50": (cost_view.get("50") or {}).get("spendPackGranular"),
                "chaseEvReturn": product_ev.get("chaseEvReturn"),
                # --- Explanatory diagnostics ---
                "extK": product["membership"]["extendedCount"],
                "chaseDepth": core.get("chaseDepth"),
                "anyChasePerPack": core.get("packProbability"),
                "chaseEvShare": product_ev.get("chaseEvShareOfFullEv"),
                "chaseEvPerProduct": product_ev.get("chaseEvPerProduct"),
                "beatTheBuy": ((core.get("beatTheBuyPackGranular") or {})
                               .get("closedForm")),
                "medianCostGap": ((core.get("costGapPackGranular") or {})
                                  .get("medianGap")),
                "spend50WholeProduct": (cost_view.get("50") or {}).get("spendWholeProduct"),
                "cardPriceBasisDate": entry.get("cardPriceBasisDate"),
                "eligiblePriceCount": len(prices),
            })
    return out


def financial_rows(client: Any, *, run_ids: Sequence[str],
                   market_date: str) -> Dict[str, Dict[str, Any]]:
    """Financial RIP V4 score plus its six component scores, per product."""
    collected: Dict[str, Dict[str, Any]] = {}
    for run_id in sorted(set(run_ids)):
        response = (client.table("simulation_sealed_product_results")
                    .select("sealed_product_id,price_as_of,financial_rip_v4_score,"
                            "financial_rip_v4_version,financial_rip_v4_status,"
                            "financial_rip_v4_payload,expected_value,p95_value,"
                            "p99_value,median_value,total_value_to_cost_ratio,"
                            "chance_to_recover_cost,random_pack_expected_value")
                    .eq("calculation_run_id", run_id)
                    .eq("price_as_of", str(market_date)[:10])
                    .limit(1000).execute())
        for row in _rows(response):
            payload = row.get("financial_rip_v4_payload") or {}
            components = payload.get("components") or {}
            record: Dict[str, Any] = {
                "financialRip": row.get("financial_rip_v4_score"),
                "financialVersion": row.get("financial_rip_v4_version"),
                "financialStatus": row.get("financial_rip_v4_status"),
                "financialPriceAsOf": row.get("price_as_of"),
                "expectedValue": row.get("expected_value"),
                "p95Value": row.get("p95_value"),
                "p99Value": row.get("p99_value"),
                "medianValue": row.get("median_value"),
                "valueToCostRatio": row.get("total_value_to_cost_ratio"),
                "chanceToRecoverCost": row.get("chance_to_recover_cost"),
                "randomPackExpectedValue": row.get("random_pack_expected_value"),
            }
            for component in FINANCIAL_COMPONENTS:
                block = components.get(component) or {}
                record["fin_" + component] = block.get("score")
            collected[str(row.get("sealed_product_id"))] = record
    return collected


def collector_rows(set_ids: Sequence[str]) -> Dict[str, Dict[str, Any]]:
    """Collector Appeal V5 and its two factors, per SET."""
    from backend.db.services.collector_appeal_service import get_collector_appeal_bundle

    payloads = (get_collector_appeal_bundle() or {}).get("payloads") or {}
    out: Dict[str, Dict[str, Any]] = {}
    for set_id in sorted(set(set_ids)):
        payload = payloads.get(str(set_id))
        if payload is None:
            out[str(set_id)] = {"collectorAppeal": None,
                                "collectorStatus": "no_payload_for_set"}
            continue
        appeal = payload.get("collectorAppeal") or {}
        roster = payload.get("rosterDesirability") or {}
        frequency = payload.get("desirableOutcomeFrequency") or {}
        coverage = payload.get("coverage") or {}
        out[str(set_id)] = {
            "collectorAppeal": appeal.get("score"),
            "collectorAppealVersion": appeal.get("version"),
            "collectorStatus": payload.get("status"),
            "collectorAsOf": payload.get("asOf"),
            "ca_rosterDesirability": roster.get("score"),
            "ca_desirableOutcomeFrequency": frequency.get("rawValue"),
            "ca_modeledSubjectCount": coverage.get("modeledSubjectCount"),
            "ca_eligibleDesirableCardCount": coverage.get("eligibleDesirableCardCount"),
            "ca_eligibleDesirableSubjectCount": coverage.get("eligibleDesirableSubjectCount"),
            "ca_coveredDemandShare": frequency.get("coveredDemandShare"),
            "ca_chaseAppeal": (payload.get("chaseAppeal") or {}).get("score"),
            "ca_eliteScarcity": (payload.get("chaseAppeal") or {}).get("eliteScarcity"),
        }
    return out


def build(client: Any, *, chase_artifact: Path) -> Dict[str, Any]:
    from backend.research.chase_pillar_stage6.control import (
        canonical_versions, control_score,
    )

    payload = json.loads(chase_artifact.read_text(encoding="utf-8"))
    chase = _chase_rows(payload)
    market_date = str(payload["marketDate"])[:10]
    print(f"{TAG} chase rows={len(chase)} market_date={market_date}")

    financial = financial_rows(
        client, run_ids=[r["calculationRunId"] for r in chase], market_date=market_date)
    collector = collector_rows([r["setId"] for r in chase])
    versions = canonical_versions()
    print(f"{TAG} financial rows={len(financial)} collector sets={len(collector)}")

    rows: List[Dict[str, Any]] = []
    unusable: List[Dict[str, Any]] = []
    for record in chase:
        money = financial.get(record["sealedProductId"])
        appeal = collector.get(record["setId"]) or {}
        if money is None:
            unusable.append({**{k: record[k] for k in ("productName", "set")},
                             "reason": "no_financial_row_for_product_in_run"})
            continue
        control = control_score(
            financial_rip_v4_score=money.get("financialRip"),
            collector_appeal_v5_score=appeal.get("collectorAppeal"),
            financial_version=money.get("financialVersion"),
            appeal_version=appeal.get("collectorAppealVersion"))
        if not control["supported"]:
            unusable.append({**{k: record[k] for k in ("productName", "set")},
                             "reason": control["reason"]})
            continue
        rows.append({**record, **money, **appeal,
                     "overallControl": control["score"],
                     "overallControlVersion": control["version"]})

    dates = {
        "productCostDate": market_date,
        "cardPriceBasisDates": sorted({r.get("cardPriceBasisDate") for r in chase}),
        "financialPriceAsOf": sorted({r.get("financialPriceAsOf") for r in financial.values()}),
        "collectorAsOf": sorted({v.get("collectorAsOf") for v in collector.values()
                                 if v.get("collectorAsOf")}),
    }
    return {
        "stage": "stage6-chase-pillar-dataset-v1",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "chaseArtifact": str(chase_artifact),
        "chaseResearchVersion": payload["researchVersion"],
        "chaseTierContract": payload["tierContract"],
        "canonicalVersions": versions,
        "controlDefinition": (
            "OVERALL_CONTROL = compute_overall_rip_v10(financial_rip_v4_score, "
            "collector_appeal_v5_score); appeal is SET-level and projected onto "
            "every product of the set, exactly as production does"),
        "controlStoredColumnPopulated": False,
        "controlStoredColumnNote": (
            "overall_rip_v10_score is NULL for every row of this run because "
            "Collector Appeal was deferred at finalization, so CONTROL is built by "
            "calling the production function rather than compared to a stored value"),
        "marketDate": market_date,
        "dates": dates,
        "rowCount": len(rows),
        "unusableCount": len(unusable),
        "unusable": unusable,
        "setCount": len({r["set"] for r in rows}),
        "familyCounts": dict(Counter(r["family"] for r in rows)),
        "rows": rows,
    }


def main(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(description="Stage VI dataset build.")
    parser.add_argument("--chase-artifact", default=str(CHASE_ARTIFACT))
    parser.add_argument("--output", default=str(OUTPUT))
    args = parser.parse_args(list(argv))

    from backend.db.clients.supabase_client import create_service_role_client

    payload = build(create_service_role_client(),
                    chase_artifact=Path(args.chase_artifact))
    destination = Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    print(f"{TAG} wrote {destination} rows={payload['rowCount']} "
          f"sets={payload['setCount']} unusable={payload['unusableCount']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
