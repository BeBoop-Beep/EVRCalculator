"""Read-only authority for the published Collector Appeal model."""
from __future__ import annotations

from typing import Any, Dict, Iterable, Optional

from backend.db.clients.supabase_client import service_read_client

PUBLIC_CONTRACT_KEY = "publicCollectorAppealContractV1"
PUBLIC_CONTRACT_VERSION = "public_collector_appeal_contract_v1"
UNAVAILABLE_REASON = "collector_appeal_unavailable_no_generalized_frequency"


def _one_in(value: Any) -> Optional[float]:
    if value is None or float(value) <= 0: return None
    return round(1.0 / float(value), 2)


def load_current_set_collector_appeal(set_ids: Optional[Iterable[str]] = None, *, client=None) -> Dict[str, Dict[str, Any]]:
    resolved = client or service_read_client
    query = resolved.table("pokemon_set_collector_appeal_current_v").select("*")
    ids = [str(value) for value in (set_ids or [])]
    if ids: query = query.in_("set_id", ids)
    try:
        rows = list(query.execute().data or [])
    except Exception:
        # Deployment-order compatibility: before the authority migration/view
        # exists, the standalone contract is absent rather than synthesized.
        return {}
    return {str(row["set_id"]): row for row in rows}


def load_set_collector_appeal_for_model(
    model_run_id: str,
    set_ids: Optional[Iterable[str]] = None,
    *,
    client=None,
) -> Dict[str, Dict[str, Any]]:
    """Load one explicit published Collector run for an inactive candidate build.

    This deliberately bypasses only the *current pointer*, not model validation:
    the requested run must already be published and validation-passed. Public
    runtime readers continue to use ``load_current_set_collector_appeal``.
    """
    resolved = client or service_read_client
    headers = list(
        resolved.table("pokemon_collector_appeal_model_runs")
        .select("id,model_version,as_of_date,status,validation_passed,published_at,input_fingerprint")
        .eq("id", str(model_run_id)).limit(1).execute().data or []
    )
    if not headers:
        raise RuntimeError(f"Collector model run {model_run_id} does not exist")
    header = headers[0]
    if (header.get("status") != "published" or header.get("validation_passed") is not True
            or not header.get("published_at")):
        raise RuntimeError(f"Collector model run {model_run_id} is not published and validated")

    ids = [str(value) for value in (set_ids or [])]
    desirability = resolved.table("pokemon_set_collector_desirability_scores").select("*").eq(
        "model_run_id", str(model_run_id)
    )
    appeal = resolved.table("pokemon_set_collector_appeal_scores").select("*").eq(
        "model_run_id", str(model_run_id)
    )
    if ids:
        desirability = desirability.in_("set_id", ids)
        appeal = appeal.in_("set_id", ids)
    d_by_set = {str(row["set_id"]): row for row in (desirability.execute().data or [])}
    a_by_set = {str(row["set_id"]): row for row in (appeal.execute().data or [])}
    rows: Dict[str, Dict[str, Any]] = {}
    for set_id in sorted(set(d_by_set) & set(a_by_set)):
        d_row, a_row = d_by_set[set_id], a_by_set[set_id]
        rows[set_id] = {
            **a_row,
            "model_version": header.get("model_version"),
            "as_of_date": header.get("as_of_date"),
            "collector_roster_desirability_score": d_row.get("collector_desirability_score"),
            "collector_roster_desirability_rank": d_row.get("collector_desirability_rank"),
            "eligible_card_count": d_row.get("eligible_card_count"),
            "scored_card_count": d_row.get("scored_card_count"),
            "neutral_card_count": d_row.get("neutral_card_count"),
            "unsupported_card_count": d_row.get("unsupported_card_count"),
            "score_coverage_ratio": d_row.get("score_coverage_ratio"),
            "subject_rollups_json": d_row.get("subject_rollups_json"),
            "roster_diagnostics_json": d_row.get("diagnostics_json"),
        }
    return rows


def load_current_card_collector_appeal(card_ids: Iterable[str], *, client=None) -> Dict[str, Dict[str, Any]]:
    ids = [str(value) for value in card_ids]
    if not ids: return {}
    resolved = client or service_read_client
    rows = resolved.table("pokemon_card_collector_appeal_current_v").select("*").in_("pokemon_canonical_card_id", ids).execute().data or []
    return {str(row["pokemon_canonical_card_id"]): row for row in rows}


def build_public_card_collector_appeal(row: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not row: return None
    components=row.get("component_inputs_json") or {}
    return {"score":row.get("collector_card_appeal_score"),"status":row.get("score_status"),"subject":{"policy":row.get("subject_policy"),"type":components.get("subjectType"),"identity":components.get("subjectIdentity") or components.get("functionalName"),"baselineScore":row.get("subject_baseline_score"),"neutralBaseline":components.get("neutralBaseline") is True},"playability":{"score":row.get("playability_score") if components.get("playabilityStatus") not in ("unknown","insufficient") else None,"status":components.get("playabilityStatus"),"confidence":row.get("confidence"),"positiveLift":row.get("playability_lift")},"artistModeled":False,"treatmentExcluded":bool(row.get("treatment_input_excluded")),"hitEligibilityIndependent":bool(row.get("hit_eligibility_independent")),"modelRunId":row.get("model_run_id"),"modelVersion":row.get("model_version"),"explanation":"A high Card Collector Appeal does not by itself mean the card counts as a pack hit."}


def build_public_collector_appeal_contract(row: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not row: return None
    scored = row.get("score_status") == "scored"
    f = row.get("generalized_desirable_outcome_frequency")
    roster_diag = row.get("roster_diagnostics_json") or {}
    groups = row.get("subject_rollups_json") or []
    return {
        "contractVersion": PUBLIC_CONTRACT_VERSION,
        "collectorAppeal": {"score": row.get("collector_appeal_score") if scored else None,"absoluteScore":row.get("collector_appeal_score") if scored else None,"rank":row.get("collector_appeal_rank") if scored else None,"rankedSetCount":22,"tier":None,"status":row.get("score_status"),"statusReason":row.get("score_status_reason"),"version":"collector_appeal","modelVersion":row.get("model_version"),"modelRunId":row.get("model_run_id"),"asOfDate":str(row.get("as_of_date")) if row.get("as_of_date") else None,
            "subjectScope":{"modeled":["Pokémon","Trainers","eligible neutral functional cards"],"notYetModeled":["Artist","Treatment","Energy"],"note":"Pokémon, Trainers, and eligible functional cards are modeled. Artist is not modeled; Treatment and Energy are excluded."}},
        "components": {
            "rosterDesirability":{"score":row.get("collector_roster_desirability_score"),"rank":row.get("collector_roster_desirability_rank"),"rankedSetCount":128,"tier":None,"version":"collector_roster_desirability_v1","groupCount":roster_diag.get("distinctGroupCount"),"pokemonGroupCount":roster_diag.get("pokemonGroupCount"),"trainerGroupCount":roster_diag.get("trainerGroupCount"),"neutralFunctionalGroupCount":roster_diag.get("neutralFunctionalGroupCount"),"topCollectorGroups":[{"name":g.get("identity"),"type":g.get("type"),"score":g.get("appeal"),"cardCount":g.get("cardCount")} for g in groups[:10]]},
            "desirableOutcomeFrequency":{"rawValue":f,"displayPercent":round(float(f)*100,2) if f is not None else None,"impliedOddsOneInN":_one_in(f),"status":row.get("generalized_frequency_status"),"statusReason":row.get("generalized_frequency_status_reason"),"version":"generalized_desirable_outcome_frequency_v1","eligibleCardCount":row.get("eligible_card_count"),"modeledCardCount":row.get("scored_card_count"),"coverageRatio":row.get("score_coverage_ratio"),"isFinancialMetric":False},
        },
        "definition":"Collector Appeal measures how compelling a set's collectible roster is and how often a modeled pack can deliver a desirable card.",
        "financialDistinction":"A desirable outcome can still be worth less than the pack price.",
    }


def attach_public_collector_appeal_contracts(targets, *, client=None):
    """Attach one reshaped contract per set; no scoring or client-side ranks."""
    set_ids = [str(t.get("set_id") or t.get("setId") or t.get("target_id") or t.get("id")) for t in targets]
    rows = load_current_set_collector_appeal(set_ids, client=client)
    result = []
    for target, set_id in zip(targets, set_ids):
        copied = dict(target)
        contract = build_public_collector_appeal_contract(rows.get(set_id))
        if contract is not None: copied[PUBLIC_CONTRACT_KEY] = contract
        result.append(copied)
    return result
