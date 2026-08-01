from __future__ import annotations

from typing import Any, Dict, Optional

from backend.db.services.publication_gate import (
    REASON_ALLOWED_COMPLETE,
    REASON_BLOCKED_AUTHORITY_UNAVAILABLE,
    REASON_BLOCKED_INCOMPLETE,
    REASON_BLOCKED_INVALID_BATCH_CONTRACT,
    REASON_BLOCKED_NO_BATCH,
    evaluate_publication_gate,
)
from backend.db.services.opening_simulation_gate import (
    STATUS_CURRENT, STATUS_INVALID, STATUS_MISSING, STATUS_STALE, STATUS_UNRESOLVED,
    evaluate_opening_simulation_freshness,
)

_REASON_MAP = {
    REASON_BLOCKED_NO_BATCH: "batch_missing",
    REASON_BLOCKED_INCOMPLETE: "batch_incomplete",
    REASON_BLOCKED_AUTHORITY_UNAVAILABLE: "batch_authority_unavailable",
    REASON_BLOCKED_INVALID_BATCH_CONTRACT: "invalid_batch_contract",
}


def evaluate_onboarding_publication_readiness(
    client: Any, *, set_id: str, canonical_key: str, market_date: str,
) -> Dict[str, Any]:
    """Read-only set-local extension of the authoritative publication gate."""
    decision = evaluate_publication_gate(
        client, market_date=market_date, override=False, mode="required",
    )
    evidence = {
        "complete": False, "dates_aligned": False, "market_date": market_date,
        "batch_id": decision.batch_id, "batch_status": decision.batch_status,
        "missing_set_count": decision.missing_set_count,
        "expected_set_count": decision.expected_set_count,
        "promoted_at": decision.promoted_at,
        "set_observation_present": False, "simulation_aligned": False,
        "simulation_status": None, "simulation_snapshot_date": None,
        "calculation_run_id": None,
        "reason_code": _REASON_MAP.get(decision.reason_code, decision.reason_code),
        "gate_reason": decision.reason,
        "force_publish": False,
    }
    if not decision.allowed or decision.reason_code != REASON_ALLOWED_COMPLETE:
        return evidence
    try:
        cards = client.table("cards").select("id").eq("set_id", set_id).limit(1000).execute().data or []
        card_ids = [row["id"] for row in cards if row.get("id")]
        variants = []
        for start in range(0, len(card_ids), 250):
            variants.extend(
                client.table("card_variants").select("id")
                .in_("card_id", card_ids[start:start + 250]).execute().data or []
            )
        variant_ids = [row["id"] for row in variants if row.get("id")]
        observations = []
        for start in range(0, len(variant_ids), 250):
            observations.extend(
                client.table("card_variant_price_observations").select("captured_at,market_price")
                .in_("card_variant_id", variant_ids[start:start + 250]).gt("market_price", 0)
                .gte("captured_at", f"{market_date}T00:00:00-07:00")
                .lt("captured_at", f"{market_date}T23:59:59.999999-07:00").limit(1).execute().data or []
            )
        evidence["set_observation_present"] = bool(observations)
        freshness = evaluate_opening_simulation_freshness(
            client, market_date=market_date, canonical_keys=[canonical_key],
        )
        if freshness.error:
            evidence.update(reason_code="simulation_history_invalid", simulation_error=freshness.error)
            return evidence
        target = freshness.statuses[0] if freshness.statuses else None
        evidence["simulation_status"] = target.status if target else STATUS_MISSING
        evidence["simulation_snapshot_date"] = target.simulation_snapshot_date if target else None
        evidence["calculation_run_id"] = target.calculation_run_id if target else None
        evidence["simulation_reason"] = target.reason if target else "no target freshness status"
        evidence["simulation_aligned"] = bool(
            target and target.status == STATUS_CURRENT
            and target.latest_simulation_date == market_date
            and target.calculation_run_id
        )
    except Exception as exc:
        evidence["reason_code"] = "batch_authority_unavailable"
        evidence["error"] = str(exc)
        return evidence
    if not evidence["set_observation_present"]:
        evidence["reason_code"] = "set_observation_missing"
        return evidence
    if not evidence["simulation_aligned"]:
        status = evidence["simulation_status"]
        if status in (STATUS_MISSING, STATUS_UNRESOLVED):
            evidence["reason_code"] = "simulation_history_missing"
        elif status == STATUS_STALE:
            evidence["reason_code"] = (
                "simulation_market_date_mismatch"
                if evidence["simulation_snapshot_date"] else "simulation_history_stale"
            )
        elif status == STATUS_INVALID:
            evidence["reason_code"] = "simulation_history_invalid"
        else:
            evidence["reason_code"] = "simulation_market_date_mismatch"
        return evidence
    evidence.update(complete=True, dates_aligned=True, reason_code="allowed_complete")
    return evidence
