"""P4C estimate writer: frozen `estimate()` over PERSISTED evidence, append-only persistence.

Only SUFFICIENT depth yields a numeric estimate row (the table forbids anything else). THIN and INSUFFICIENT depth is
carried as diagnostics derived from the persisted per-card summaries and is never given a price.
"""
from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any, Mapping, Sequence

from backend.pricing_pipeline.contracts import NM_CONDITION_ID, PipelineError
from backend.scripts.freeze_ebay_active_ask_v1 import VERSION as ESTIMATOR_VERSION, estimate
from backend.scripts.ebay_english_price_eligibility_v1 import VERSION as ELIGIBILITY_VERSION


def estimate_id(variant_id: str, market_date: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"ebay-estimate:{variant_id}:{NM_CONDITION_ID}:{market_date}:{ESTIMATOR_VERSION}"))


def depth_from_summary(summary: Mapping[str, Any]) -> str:
    sellers = int(summary.get("eligible_seller_count") or 0)
    return "SUFFICIENT" if sellers >= 5 else "THIN" if sellers >= 3 else "INSUFFICIENT"


def _decision_rows(evidence: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [{"state": "ENGLISH_PRICE_ELIGIBLE", "item_id": e["listing_item_id"], "seller_key_sha256": e["seller_key_sha256"],
             "landed_ask_usd": format(Decimal(str(e["landed_ask_usd"])), ".2f")} for e in evidence]


def build(evidence: Sequence[Mapping[str, Any]], summaries: Sequence[Mapping[str, Any]], manifest: Mapping[str, Any], *,
          pricing_run_id: str, market_date: str, evidence_digest: str) -> dict[str, Any]:
    by_card: dict[str, list[Mapping[str, Any]]] = {}
    for row in evidence:
        by_card.setdefault(str(row["canonical_card_id"]), []).append(row)
    targets = {t["canonical_card_id"]: t for t in manifest["cards"]}
    rows, diagnostics = [], {}
    for summary in sorted(summaries, key=lambda s: s["canonical_card_id"]):
        cid = str(summary["canonical_card_id"])
        target = targets[cid]
        card_rows = by_card.get(cid, [])
        result = estimate({"canonical_card_id": cid, "card_variant_id": target.get("card_variant_id")}, _decision_rows(card_rows),
                          market_date, pricing_run_id)
        depth = result["depth_state"]
        if depth != depth_from_summary(summary):
            raise PipelineError("ESTIMATOR_DEPTH_SUMMARY_MISMATCH", cid)
        diagnostics[cid] = {"depth_state": depth, "distinct_seller_count": result["distinct_seller_count"],
                            "eligible_listing_count": result["eligible_listing_count"]}
        if depth != "SUFFICIENT" or result["estimated_price"] is None:
            continue  # no numeric price without SUFFICIENT depth and a resolved variant
        if result["estimator_version"] != ESTIMATOR_VERSION:
            raise PipelineError("ESTIMATOR_VERSION_MISMATCH", result["estimator_version"])
        id_by_item = {r["listing_item_id"]: r["id"] for r in card_rows}
        contributing = [dict(c, evidence_row_id=id_by_item[c["listing_item_id"]]) for c in result["contributing_evidence"]]
        rows.append({
            "id": estimate_id(result["card_variant_id"], market_date), "pricing_run_id": pricing_run_id,
            "canonical_card_id": cid, "card_variant_id": result["card_variant_id"], "condition_id": NM_CONDITION_ID,
            "market_date": market_date, "source": "eBayActiveAsk", "evidence_kind": "active_ask",
            "estimator_version": ESTIMATOR_VERSION, "eligibility_policy_version": ELIGIBILITY_VERSION,
            "eligible_listing_count": result["eligible_listing_count"], "distinct_seller_count": result["distinct_seller_count"],
            "landed_ask_min": result["landed_ask_min"], "landed_ask_max": result["landed_ask_max"],
            "selected_ask_1": result["selected_ask_1"], "selected_ask_2": result["selected_ask_2"], "selected_ask_3": result["selected_ask_3"],
            "estimated_price": result["estimated_price"], "depth_state": "SUFFICIENT",
            "input_evidence_fingerprint": result["input_evidence_fingerprint"], "estimator_fingerprint": result["estimator_fingerprint"],
            "contributing_evidence": contributing, "source_artifact_fingerprint": evidence_digest,
        })
    return {"rows": rows, "diagnostics": diagnostics}


def verify_replay(row: Mapping[str, Any], evidence: Sequence[Mapping[str, Any]]) -> bool:
    """Recompute the frozen estimate from persisted evidence and compare the estimator fingerprint."""
    card_rows = [e for e in evidence if str(e["canonical_card_id"]) == str(row["canonical_card_id"])]
    result = estimate({"canonical_card_id": row["canonical_card_id"], "card_variant_id": row["card_variant_id"]},
                      _decision_rows(card_rows), str(row["market_date"]), str(row["pricing_run_id"]))
    return result["estimator_fingerprint"] == row["estimator_fingerprint"] and result["estimated_price"] == format(Decimal(str(row["estimated_price"])), ".2f")
