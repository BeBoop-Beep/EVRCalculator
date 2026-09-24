"""Daily builder for `pokemon_multi_source_card_price_v1`: applies the frozen policy, makes no research decisions.

Rows exist for every card evaluated by the eBay stage that day (the shadow authority is sparse by design); a card
without a row today is simply TCGplayer-primary in canonical pricing. eBay depth is TODAY's actual depth: nothing is
carried forward from earlier days.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Mapping, Sequence

from backend.pricing_pipeline.contracts import NM_CONDITION_ID, PipelineError
from backend.pricing_pipeline.estimates import depth_from_summary
from backend.scripts import pokemon_multi_source_card_price_v1 as policy


def build(manifest: Mapping[str, Any], summaries: Sequence[Mapping[str, Any]], estimates: Sequence[Mapping[str, Any]],
          tcg_prices: Mapping[str, Mapping[str, Any]], *, market_date: str, pipeline_run_id: str) -> list[dict[str, Any]]:
    if policy.POLICY_VERSION != "pokemon_multi_source_card_price_v1":
        raise PipelineError("POLICY_VERSION_MISMATCH", policy.POLICY_VERSION)
    targets = {t["canonical_card_id"]: t for t in manifest["cards"]}
    estimate_by_card = {str(e["canonical_card_id"]): e for e in estimates}
    when = date.fromisoformat(market_date)
    rows = []
    for summary in sorted(summaries, key=lambda s: s["canonical_card_id"]):
        cid = str(summary["canonical_card_id"])
        target = targets[cid]
        price = tcg_prices.get(cid)
        tcg = {"canonical_card_id": cid, "card_variant_id": price["card_variant_id"], "market_price": price["market_price"],
               "captured_at": price["captured_at"]} if price else None
        variant = (price or {}).get("card_variant_id") or target.get("card_variant_id")
        est = estimate_by_card.get(cid)
        ebay = {"canonical_card_id": cid, "card_variant_id": variant, "estimator_version": policy.EBAY_ESTIMATOR_VERSION,
                "market_date": market_date, "distinct_seller_count": summary["eligible_seller_count"],
                "eligible_listing_count": summary["persisted_count"], "depth_state": depth_from_summary(summary),
                "estimated_price": None, "estimator_fingerprint": None}
        if est is not None:
            ebay.update(estimated_price=str(est["estimated_price"]), depth_state="SUFFICIENT",
                        distinct_seller_count=est["distinct_seller_count"], eligible_listing_count=est["eligible_listing_count"],
                        estimator_fingerprint=est["estimator_fingerprint"], estimator_version=est["estimator_version"],
                        card_variant_id=est["card_variant_id"])
        decision = policy.decide(tcg, ebay, when, NM_CONDITION_ID)
        if decision["card_variant_id"] is None:
            continue  # identity-unresolved cards are not persisted (never selected as targets anyway)
        rows.append(dict(decision, pipeline_run_id=pipeline_run_id, ebay_estimate_id=est["id"] if est and decision["ebay_price"] else None))
    return rows


def decision_counts(rows: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {state: 0 for state in policy.DECISION_STATES}
    for row in rows:
        counts[row["decision_state"]] += 1
    return counts
