"""Semantic freshness evaluation for persisted Set-page RIP decisions."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Mapping, Optional

from backend.db.services.rip_decision_service import RIP_DECISION_CONTRACT_VERSION


def _text(value: Any) -> Optional[str]:
    text = str(value).strip() if value is not None else ""
    return text or None


def _instant(value: Any) -> Optional[datetime]:
    text = _text(value)
    if text is None:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def evaluate_rip_decision_staleness(
    decision: Any,
    *,
    ranked: bool,
    expected_run_id: Any,
    expected_sealed_market_classification_version: Any,
    expected_sealed_market_contract_version: Any = None,
    expected_product_result_count: Optional[int] = None,
    expected_product_results_updated_at: Any = None,
) -> List[Dict[str, str]]:
    """Return stable, explicit reasons; an empty list means semantically fresh."""
    reasons: List[Dict[str, str]] = []

    def add(code: str, message: str) -> None:
        reasons.append({"code": code, "message": message})

    if not isinstance(decision, Mapping):
        add("rip_decision_missing", "ripDecision is missing")
        return reasons
    if decision.get("contractVersion") != RIP_DECISION_CONTRACT_VERSION:
        add("contract_version_mismatch", "ripDecision contractVersion is stale")
    if not ranked:
        return reasons

    run_id = _text(expected_run_id)
    if decision.get("currentRunAvailable") is not True:
        add("current_run_unavailable", "ripDecision currentRunAvailable is not true for ranked set")
    if _text(decision.get("sourceCalculationRunId")) != run_id:
        add("source_run_mismatch", "ripDecision source calculation run is stale")

    sealed = decision.get("sealedProducts")
    if not isinstance(sealed, Mapping):
        add("sealed_products_missing", "ripDecision sealedProducts is missing")
        sealed = {}
    if _text(sealed.get("sourceCalculationRunId")) != run_id:
        add("sealed_products_run_mismatch", "ripDecision sealedProducts run is stale")
    if int(sealed.get("productCount") or 0) <= 0:
        add("modeled_products_missing", "ripDecision has no modeled products for ranked set")

    chase = decision.get("topChase")
    if not isinstance(chase, Mapping):
        add("top_chase_missing", "ripDecision Top Chase is missing")
    elif _text(chase.get("sourceCalculationRunId")) != run_id:
        add("top_chase_run_mismatch", "ripDecision Top Chase run is stale")

    actual_classification = _text(decision.get("sourceSealedMarketClassificationVersion"))
    expected_classification = _text(expected_sealed_market_classification_version)
    if actual_classification is None:
        add("classification_provenance_missing", "ripDecision sealed-market classification version is missing")
    elif expected_classification is not None and actual_classification != expected_classification:
        add("classification_version_mismatch", "ripDecision sealed-market classification version is stale")

    actual_contract = _text(decision.get("sourceSealedMarketSnapshotContractVersion"))
    expected_contract = _text(expected_sealed_market_contract_version)
    if expected_contract is not None and actual_contract is None:
        add("sealed_market_contract_provenance_missing", "ripDecision sealed-market snapshot contract provenance is missing")
    elif actual_contract is not None and expected_contract is not None and actual_contract != expected_contract:
        add("sealed_market_contract_mismatch", "ripDecision sealed-market snapshot contract version is stale")

    actual_count = decision.get("sourceSealedProductResultCount")
    if expected_product_result_count is not None and actual_count != expected_product_result_count:
        add("product_result_count_mismatch", "ripDecision sealed-product result population is incomplete")
    actual_updated = _text(decision.get("sourceSealedProductResultsUpdatedAt"))
    expected_updated = _text(expected_product_results_updated_at)
    actual_instant = _instant(actual_updated)
    expected_instant = _instant(expected_updated)
    product_results_older = (
        expected_updated is not None
        and (
            actual_updated is None
            or (actual_instant is not None and expected_instant is not None and actual_instant < expected_instant)
            or (actual_instant is None and actual_updated != expected_updated)
        )
    )
    if product_results_older:
        add("product_results_stale", "ripDecision sealed-product results provenance is stale")
    return reasons
