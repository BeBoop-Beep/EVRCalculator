"""Explicit readiness, audit, and persisted parity for Rankings publication."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Mapping, Optional, Sequence
from uuid import uuid4

from backend.db.services.set_rip_service import (
    METHODOLOGY_VERSION as SET_RIP_METHODOLOGY_VERSION,
    MINIMUM_PARTICIPATING_FAMILIES,
)
from backend.desirability.scoring_config import (
    CANONICAL_FINANCIAL_RIP_VERSION,
    CANONICAL_OVERALL_RIP_VERSION,
    canonical_collector_appeal_version,
)
from backend.db.services.public_rip_publication_contract import (
    canonical_publication_identity,
    supported_cohort_fingerprint,
)

READY = "READY"
DEFERRED_SIMULATION_COHORT_INCOMPLETE = "DEFERRED_SIMULATION_COHORT_INCOMPLETE"
DEFERRED_SIMULATION_DATE_ROLLOVER = "DEFERRED_SIMULATION_DATE_ROLLOVER"
DEFERRED_SEALED_PRODUCT_FINALIZATION_INCOMPLETE = "DEFERRED_SEALED_PRODUCT_FINALIZATION_INCOMPLETE"
DEFERRED_PRODUCT_RANKINGS_INCOMPLETE = "DEFERRED_PRODUCT_RANKINGS_INCOMPLETE"
DEFERRED_SET_RIP_INCOMPLETE = "DEFERRED_SET_RIP_INCOMPLETE"
FAILED_PUBLICATION_CONTRACT = "FAILED_PUBLICATION_CONTRACT"
FAILED_PUBLICATION_RPC = "FAILED_PUBLICATION_RPC"
FAILED_POST_PUBLICATION_PARITY = "FAILED_POST_PUBLICATION_PARITY"


def _text(value: Any) -> str:
    return str(value or "").strip()


def source_run_fingerprint(source_run_ids: Mapping[str, Any]) -> str:
    canonical = json.dumps(
        {str(key): _text(value) for key, value in sorted(source_run_ids.items())},
        separators=(",", ":"), sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass
class RankingsReadinessReport:
    status: str
    reason_code: str
    detail: str
    market_date: Optional[str] = None
    expected_supported_cohort_count: int = 0
    verified_simulation_cohort_count: int = 0
    sealed_product_finalized_set_count: int = 0
    sealed_product_finalized_product_row_count: int = 0
    product_family_readiness: Dict[str, Any] = field(default_factory=dict)
    set_rip_ranked_set_count: int = 0
    source_run_ids: Dict[str, str] = field(default_factory=dict)
    source_run_fingerprint: Optional[str] = None
    contract_versions: Dict[str, Any] = field(default_factory=dict)
    problems: list[str] = field(default_factory=list)

    @property
    def ready(self) -> bool:
        return self.status == READY

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def deferred_simulation_readiness(
    *, market_date: str, expected_count: int, verified_count: int,
    failures: Sequence[str],
) -> RankingsReadinessReport:
    problems = [str(item) for item in failures]
    return RankingsReadinessReport(
        status=DEFERRED_SIMULATION_COHORT_INCOMPLETE,
        reason_code=DEFERRED_SIMULATION_COHORT_INCOMPLETE,
        detail=(f"authoritative promoted-date simulation cohort is incomplete "
                f"expected={expected_count} verified={verified_count}: " + "; ".join(problems)),
        market_date=market_date,
        expected_supported_cohort_count=expected_count,
        verified_simulation_cohort_count=verified_count,
        problems=problems,
    )


def deferred_simulation_rollover_readiness(
    *, market_date: str, simulation_date: str, expected_count: int,
    current_count: int, pending_keys: Sequence[str],
) -> RankingsReadinessReport:
    pending = sorted(str(key) for key in pending_keys)
    detail = (
        f"promoted market date {market_date} cannot be repaired by simulations executed "
        f"on {simulation_date} because calculation history is dated from actual execution "
        f"time and simulations cannot be backdated; waiting for promoted market date "
        f"{simulation_date}; current={current_count}/{expected_count}; "
        f"pending={','.join(pending)}"
    )
    return RankingsReadinessReport(
        status=DEFERRED_SIMULATION_DATE_ROLLOVER,
        reason_code=DEFERRED_SIMULATION_DATE_ROLLOVER,
        detail=detail,
        market_date=market_date,
        expected_supported_cohort_count=expected_count,
        verified_simulation_cohort_count=current_count,
        problems=[detail],
    )


def evaluate_rankings_publication_readiness(
    row: Mapping[str, Any], snapshot: Mapping[str, Any], *,
    expected_market_date: Optional[str] = None,
    sealed_product_finalization_status: Optional[str] = None,
    sealed_product_finalization_report: Optional[Mapping[str, Any]] = None,
) -> RankingsReadinessReport:
    """Evaluate the already-built candidate before the publication RPC."""
    payload = row.get("ranking_payload_json") if isinstance(row, Mapping) else None
    payload = payload if isinstance(payload, Mapping) else {}
    targets = list(payload.get("targets") or [])
    ranked = [target for target in targets if isinstance(target, Mapping) and
              (target.get("overallRipV10") or {}).get("rank") is not None]
    market_date = _text(snapshot.get("market_date")) or None
    supported = supported_cohort_fingerprint()
    expected_count = int(supported.get("count") or snapshot.get("eligible_cohort_count") or 0)
    source_runs = {
        _text(target.get("canonical_key") or target.get("set_id") or target.get("target_id")):
        _text(target.get("calculation_run_id"))
        for target in ranked
    }
    problems: list[str] = []
    if not market_date or (expected_market_date and market_date != expected_market_date):
        problems.append(f"market date expected={expected_market_date} actual={market_date}")
    missing_runs = sorted(key for key, run_id in source_runs.items() if not run_id)
    if len(ranked) != expected_count or missing_runs:
        problems.append(
            f"simulation authority expected={expected_count} actual={len(ranked)} "
            f"missing_run_ids={missing_runs}"
        )
    if problems:
        return RankingsReadinessReport(
            status=DEFERRED_SIMULATION_COHORT_INCOMPLETE,
            reason_code=DEFERRED_SIMULATION_COHORT_INCOMPLETE,
            detail="; ".join(problems), market_date=market_date,
            expected_supported_cohort_count=expected_count,
            verified_simulation_cohort_count=len(ranked), source_run_ids=source_runs,
            source_run_fingerprint=source_run_fingerprint(source_runs), problems=problems,
        )

    final_report = dict(sealed_product_finalization_report or {})
    finalized_sets = int(final_report.get("setCount") or len(ranked))
    finalized_rows = int(final_report.get("rowsFinalized") or 0)
    if sealed_product_finalization_status and sealed_product_finalization_status not in {
        "ok", "complete", "completed", "success", "already_complete", "validated_dry_run"
    }:
        detail = f"sealed-product finalization status={sealed_product_finalization_status}"
        return RankingsReadinessReport(
            status=DEFERRED_SEALED_PRODUCT_FINALIZATION_INCOMPLETE,
            reason_code=DEFERRED_SEALED_PRODUCT_FINALIZATION_INCOMPLETE, detail=detail,
            market_date=market_date, expected_supported_cohort_count=expected_count,
            verified_simulation_cohort_count=len(ranked),
            sealed_product_finalized_set_count=finalized_sets,
            sealed_product_finalized_product_row_count=finalized_rows,
            source_run_ids=source_runs, source_run_fingerprint=source_run_fingerprint(source_runs),
            problems=[detail],
        )
    if sealed_product_finalization_report and finalized_sets != expected_count:
        detail = f"sealed-product finalized set cohort expected={expected_count} actual={finalized_sets}"
        return RankingsReadinessReport(
            status=DEFERRED_SEALED_PRODUCT_FINALIZATION_INCOMPLETE,
            reason_code=DEFERRED_SEALED_PRODUCT_FINALIZATION_INCOMPLETE, detail=detail,
            market_date=market_date, expected_supported_cohort_count=expected_count,
            verified_simulation_cohort_count=len(ranked),
            sealed_product_finalized_set_count=finalized_sets,
            sealed_product_finalized_product_row_count=finalized_rows,
            source_run_ids=source_runs, source_run_fingerprint=source_run_fingerprint(source_runs),
            problems=[detail],
        )

    families = ((payload.get("productFamilyRankings") or {}).get("families") or {})
    family_summary: Dict[str, Any] = {}
    product_problems = []
    for family_name, block in sorted(families.items()):
        products = list((block or {}).get("products") or [])
        represented = sorted({_text(product.get("setId")) for product in products} - {""})
        family_summary[family_name] = {
            "productCount": len(products), "representedSetCount": len(represented),
            "representedSets": represented,
        }
        for product in products:
            set_id = _text(product.get("setId"))
            target = next((item for item in ranked if _text(item.get("set_id") or item.get("target_id")) == set_id), None)
            if target is None or _text(product.get("calculationRunId")) != _text(target.get("calculation_run_id")):
                product_problems.append(f"{family_name}:{product.get('sealedProductId')}: run authority mismatch")
            if product.get("overallRipLeaderScore") is None or product.get("financialRipLeaderScore") is None:
                product_problems.append(f"{family_name}:{product.get('sealedProductId')}: leader score missing")
    if not families or product_problems:
        detail = "; ".join(product_problems) or "no canonical product-family rankings were formed"
        return RankingsReadinessReport(
            status=DEFERRED_PRODUCT_RANKINGS_INCOMPLETE,
            reason_code=DEFERRED_PRODUCT_RANKINGS_INCOMPLETE, detail=detail,
            market_date=market_date, expected_supported_cohort_count=expected_count,
            verified_simulation_cohort_count=len(ranked),
            sealed_product_finalized_set_count=finalized_sets,
            sealed_product_finalized_product_row_count=finalized_rows,
            product_family_readiness=family_summary, source_run_ids=source_runs,
            source_run_fingerprint=source_run_fingerprint(source_runs), problems=product_problems or [detail],
        )

    set_rip = payload.get("setRip") or {}
    ranked_set_rip = int(set_rip.get("rankedSetCount") or 0)
    set_rip_problems = []
    if set_rip.get("methodologyVersion") != SET_RIP_METHODOLOGY_VERSION or ranked_set_rip != expected_count:
        set_rip_problems.append(
            f"Set RIP expected={expected_count} actual={ranked_set_rip} "
            f"methodology={set_rip.get('methodologyVersion')}"
        )
    for target in ranked:
        block = target.get("setRipV1") or {}
        if (block.get("rankable") is not True or block.get("rank") is None or
                int(block.get("participatingFamilyCount") or 0) < MINIMUM_PARTICIPATING_FAMILIES):
            set_rip_problems.append(
                f"{target.get('canonical_key') or target.get('set_id')}: incomplete Set RIP"
            )
    if set_rip_problems:
        return RankingsReadinessReport(
            status=DEFERRED_SET_RIP_INCOMPLETE, reason_code=DEFERRED_SET_RIP_INCOMPLETE,
            detail="; ".join(set_rip_problems), market_date=market_date,
            expected_supported_cohort_count=expected_count,
            verified_simulation_cohort_count=len(ranked),
            sealed_product_finalized_set_count=finalized_sets,
            sealed_product_finalized_product_row_count=finalized_rows,
            product_family_readiness=family_summary, set_rip_ranked_set_count=ranked_set_rip,
            source_run_ids=source_runs, source_run_fingerprint=source_run_fingerprint(source_runs),
            problems=set_rip_problems,
        )

    identity = canonical_publication_identity()
    versions = {
        "overallRipVersion": identity["overallRipVersion"],
        "financialRipVersion": identity["financialRipVersion"],
        "collectorAppealVersion": identity["collectorAppealVersion"],
        "publicRipContractVersion": identity["publicRipContractVersion"],
        "setRipMethodologyVersion": SET_RIP_METHODOLOGY_VERSION,
    }
    return RankingsReadinessReport(
        status=READY, reason_code=READY,
        detail=f"Rankings candidate is ready for {market_date} with {expected_count} supported sets",
        market_date=market_date, expected_supported_cohort_count=expected_count,
        verified_simulation_cohort_count=len(ranked),
        sealed_product_finalized_set_count=finalized_sets,
        sealed_product_finalized_product_row_count=finalized_rows,
        product_family_readiness=family_summary, set_rip_ranked_set_count=ranked_set_rip,
        source_run_ids=source_runs, source_run_fingerprint=source_run_fingerprint(source_runs),
        contract_versions=versions,
    )


def _first(data: Any) -> Optional[Dict[str, Any]]:
    rows = list(data or [])
    return dict(rows[0]) if rows else None


def read_active_publication(client: Any) -> Dict[str, Any]:
    row = _first(client.table("pokemon_public_rip_leaderboard_snapshots")
                 .select("id,market_date").eq("publication_status", "complete")
                 .order("market_date", desc=True).limit(1).execute().data)
    return row or {}


def start_rankings_publication_attempt(
    client: Any, report: RankingsReadinessReport, *, prior: Optional[Mapping[str, Any]] = None,
) -> str:
    attempt_id = str(uuid4())
    prior = dict(prior or {})
    client.table("pokemon_rankings_publication_attempts").insert({
        "id": attempt_id, "attempted_market_date": report.market_date,
        "status": "evaluating", "reason_code": report.reason_code,
        "reason_detail": report.detail,
        "expected_supported_cohort_count": report.expected_supported_cohort_count,
        "verified_simulation_cohort_count": report.verified_simulation_cohort_count,
        "sealed_product_finalized_set_count": report.sealed_product_finalized_set_count,
        "sealed_product_finalized_product_row_count": report.sealed_product_finalized_product_row_count,
        "product_family_readiness": report.product_family_readiness,
        "set_rip_ranked_set_count": report.set_rip_ranked_set_count,
        "source_run_fingerprint": report.source_run_fingerprint,
        "source_run_ids": report.source_run_ids,
        "prior_active_publication_id": prior.get("id"),
        "previous_active_market_date": prior.get("market_date"),
        "contract_versions": report.contract_versions,
        "diagnostics": {"problems": report.problems},
    }).execute()
    return attempt_id


def finish_rankings_publication_attempt(
    client: Any, attempt_id: str, *, status: str, reason_code: str,
    detail: str, publication_id: Optional[str] = None, error: Optional[BaseException] = None,
) -> None:
    values: Dict[str, Any] = {
        "status": status, "reason_code": reason_code, "reason_detail": detail,
        "resulting_publication_id": publication_id,
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }
    if error is not None:
        values.update(error_type=type(error).__name__, error_message=str(error)[:2000])
    client.table("pokemon_rankings_publication_attempts").update(values).eq("id", attempt_id).execute()


def assert_rankings_publication_parity(
    client: Any, report: RankingsReadinessReport, *, publication_id: str,
) -> Dict[str, Any]:
    latest = _first(client.table("pokemon_explore_rankings_snapshot_latest")
                    .select("ranking_payload_json,updated_at")
                    .eq("tcg", "pokemon").eq("scope", "rip-statistics").limit(1).execute().data)
    history = _first(client.table("pokemon_public_rip_leaderboard_snapshots")
                     .select("id,market_date,publication_status,payload_json,overall_rip_version,financial_rip_version,ca7_version")
                     .eq("id", publication_id).limit(1).execute().data)
    problems = []
    latest_payload = (latest or {}).get("ranking_payload_json") or {}
    snapshot_meta = ((latest_payload.get("meta") or {}).get("snapshot") or {})
    if _text(snapshot_meta.get("marketDate")) != _text(report.market_date):
        problems.append(f"latest market date expected={report.market_date} actual={snapshot_meta.get('marketDate')}")
    published_runs = {
        _text(target.get("canonical_key") or target.get("set_id") or target.get("target_id")):
        _text(target.get("calculation_run_id"))
        for target in latest_payload.get("targets") or []
        if (target.get("overallRipV10") or {}).get("rank") is not None
    }
    if published_runs != report.source_run_ids:
        problems.append("latest source run authority differs from the ready candidate")
    if not history or _text(history.get("publication_status")) != "complete":
        problems.append("historical publication row is missing or incomplete")
    elif _text(history.get("market_date")) != _text(report.market_date):
        problems.append("historical publication market date differs from authority")
    history_payload = (history or {}).get("payload_json") or {}
    historical_runs = {
        _text(target.get("canonical_key") or target.get("set_id") or target.get("target_id")):
        _text(target.get("calculation_run_id"))
        for target in history_payload.get("targets") or []
        if (target.get("overallRipV10") or {}).get("rank") is not None
    }
    if historical_runs != report.source_run_ids:
        problems.append("historical source run authority differs from the ready candidate")
    versions = report.contract_versions
    if history:
        observed = (history.get("overall_rip_version"), history.get("financial_rip_version"), history.get("ca7_version"))
        expected = (versions.get("overallRipVersion"), versions.get("financialRipVersion"), versions.get("collectorAppealVersion"))
        if observed != expected:
            problems.append(f"canonical version mismatch expected={expected} actual={observed}")
    latest_versions = ((latest_payload.get("meta") or {}).get("ripWeightsConfig") or {})
    latest_public_contract = ((latest_versions.get("publicContract") or {}).get("version"))
    if _text(latest_public_contract) != _text(versions.get("publicRipContractVersion")):
        problems.append("latest public scoring contract version is not canonical")
    if len(published_runs) != report.expected_supported_cohort_count:
        problems.append("published supported cohort is incomplete")
    if problems:
        raise RuntimeError("Rankings post-publication parity failed: " + "; ".join(problems))
    return {"status": "passed", "publicationId": publication_id,
            "marketDate": report.market_date, "sourceRunFingerprint": report.source_run_fingerprint,
            "updatedAt": (latest or {}).get("updated_at")}
