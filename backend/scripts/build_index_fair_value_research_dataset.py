"""Build the read-only inDex Fair Value F1 cohort and authority audit.

This is a preregistration/research builder.  It performs SELECTs only and writes
versioned local artifacts; it never publishes a model or changes database state.
"""
from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.desirability.treatment_taxonomy_v3 import (  # noqa: E402
    TAXONOMY_VERSION,
    as_json,
    resolve_treatment_v3,
    taxonomy_fingerprint,
)

MODEL_VERSION = "pokemon_collector_appeal_v7_expanded_price_blind_v1"
MODEL_RUN_ID = "e282f26e-2136-4105-b0a3-f0974c4d9d70"
BUILDER_VERSION = "index_fair_value_f1_dataset_contract_v1"
TREATMENT_FINGERPRINT = "85fdb2344d9ae7842a91bf0b3b0a434e02e99298be4cb025c8b3826066f67ddc"
ARTIFACT_DIR = ROOT / "backend/artifacts/index_fair_value"


def paged(factory: Callable[[], Any], page_size: int = 1000) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    start = 0
    while True:
        page = list(factory().range(start, start + page_size - 1).execute().data or [])
        rows.extend(page)
        if len(page) < page_size:
            return rows
        start += page_size


def canonical_hash(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _days_old(value: str | None, today: date) -> int | None:
    if not value:
        return None
    return (today - date.fromisoformat(str(value)[:10])).days


def _count(client: Any, table: str, **equals: Any) -> int | None:
    try:
        query = client.table(table).select("*", count="exact").limit(0)
        for key, value in equals.items():
            query = query.eq(key, value)
        return query.execute().count
    except Exception:
        return None


def _probe(client: Any, table: str) -> dict[str, Any]:
    try:
        row = (client.table(table).select("*").limit(1).execute().data or [None])[0]
        return {"available": True, "columns": sorted(row or {})}
    except Exception as exc:
        return {"available": False, "error": type(exc).__name__}


def build(client: Any, *, as_of_date: date | None = None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    today = as_of_date or datetime.now().date()
    current = (client.table("pokemon_collector_appeal_current")
               .select("model_run_id,model_version,as_of_date")
               .eq("scope", "pokemon").single().execute().data)
    if current.get("model_version") != MODEL_VERSION or str(current.get("model_run_id")) != MODEL_RUN_ID:
        raise RuntimeError("frozen Collector Appeal V7 binding does not match live authority")

    sets = paged(lambda: client.table("sets").select(
        "id,name,era_id,release_date,parent_opening_set_id,counts_toward_parent_set_value").order("id"))
    eras = paged(lambda: client.table("eras").select("id,name").order("id"))
    cards = paged(lambda: client.table("pokemon_canonical_cards").select(
        "id,set_id,pokemon_tcg_api_card_id,name,number,printed_number,rarity,artist,supertype,subtypes").order("id"))
    legacy = paged(lambda: client.table("cards").select(
        "id,set_id,pokemon_tcg_api_id,name,card_number,rarity").order("id"))
    variants = paged(lambda: client.table("card_variants").select(
        "id,card_id,pokemon_tcg_api_id,printing_type,special_type,edition").order("id"))
    prices = paged(lambda: client.table("pokemon_canonical_card_market_prices_latest").select(
        "canonical_card_id,set_id,legacy_card_id,card_variant_id,condition_id,printing_type,market_price,captured_at,source,price_selection_reason,refreshed_at").order("canonical_card_id"))
    appeal = paged(lambda: client.table("pokemon_card_collector_appeal_scores").select(
        "pokemon_canonical_card_id,set_id,subject_policy,subject_baseline_score,artist_recognition_score,playability_score,collector_card_appeal_score,score_status,confidence,component_inputs_json,lineage_json,price_input_excluded,treatment_input_excluded").eq("model_run_id", MODEL_RUN_ID).order("pokemon_canonical_card_id"))
    authorities = paged(lambda: client.table("explore_rip_statistics_latest").select(
        "set_id,calculation_run_id").order("set_id"))
    accepted_runs = {str(x["calculation_run_id"]) for x in authorities if x.get("calculation_run_id")}
    rates: list[dict[str, Any]] = []
    for run_id in sorted(accepted_runs):
        rates.extend(paged(lambda run_id=run_id: client.table("simulation_card_variant_pull_rates").select(
            "card_id,card_variant_id,set_id,calculation_run_id,modeled_probability,effective_pull_rate,model_source,model_version,status,price_used,created_at").eq("calculation_run_id", run_id)))

    set_by = {str(x["id"]): x for x in sets}
    era_by = {str(x["id"]): x.get("name") for x in eras}
    legacy_by_api = {str(x.get("pokemon_tcg_api_id")): x for x in legacy if x.get("pokemon_tcg_api_id")}
    variant_by = {str(x["id"]): x for x in variants}
    price_by = {str(x["canonical_card_id"]): x for x in prices}
    appeal_by = {str(x["pokemon_canonical_card_id"]): x for x in appeal}
    rate_by_variant: dict[str, dict[str, Any]] = {}
    for row in rates:
        vid = str(row.get("card_variant_id"))
        old = rate_by_variant.get(vid)
        if old is None or str(row.get("created_at")) > str(old.get("created_at")):
            rate_by_variant[vid] = row

    out: list[dict[str, Any]] = []
    exclusions = Counter()
    for card in cards:
        cid = str(card["id"])
        sid = str(card["set_id"])
        set_row = set_by.get(sid, {})
        era = era_by.get(str(set_row.get("era_id")))
        price = price_by.get(cid)
        score = appeal_by.get(cid)
        legacy_row = legacy_by_api.get(str(card.get("pokemon_tcg_api_card_id")))
        selected_variant = variant_by.get(str((price or {}).get("card_variant_id")), {})
        rate = rate_by_variant.get(str((price or {}).get("card_variant_id")))
        treatment = resolve_treatment_v3(
            rarity=card.get("rarity"), era=era,
            printing_type=selected_variant.get("printing_type"),
            special_type=selected_variant.get("special_type"), edition=selected_variant.get("edition"))
        reasons: list[str] = []
        if not card.get("pokemon_tcg_api_card_id") or not legacy_row:
            reasons.append("inadequate_or_ambiguous_identity")
        if not price or not price.get("market_price") or float(price["market_price"]) <= 0:
            reasons.append("no_trustworthy_canonical_price")
        if not score or score.get("score_status") != "scored":
            reasons.append("collector_appeal_unavailable")
        if not rate or not rate.get("modeled_probability") or float(rate["modeled_probability"]) <= 0:
            reasons.append("exact_pull_scarcity_unavailable")
        if treatment.treatment_key is None:
            reasons.append("treatment_unresolved")
        if not set_row.get("release_date"):
            reasons.append("release_date_unavailable")
        for reason in set(reasons):
            exclusions[reason] += 1
        probability = float(rate["modeled_probability"]) if rate and rate.get("modeled_probability") else None
        parent = set_row.get("parent_opening_set_id")
        root_set_id = str(parent or sid)
        out.append({
            "canonical_card_id": cid, "pokemon_tcg_api_card_id": card.get("pokemon_tcg_api_card_id"),
            "legacy_card_id": (price or {}).get("legacy_card_id") or (legacy_row or {}).get("id"),
            "card_variant_id": (price or {}).get("card_variant_id"), "card_name": card.get("name"),
            "card_number": card.get("number"), "set_id": sid, "set_name": set_row.get("name"),
            "root_set_id": root_set_id, "era": era, "release_date": set_row.get("release_date"),
            "age_days": _days_old(set_row.get("release_date"), today), "supertype": card.get("supertype"),
            "subtypes": card.get("subtypes"), "rarity_label": card.get("rarity"),
            "printing_type": selected_variant.get("printing_type"), "special_type": selected_variant.get("special_type"),
            "edition": selected_variant.get("edition"), **as_json(treatment),
            "target_market_price_usd": float(price["market_price"]) if price and price.get("market_price") else None,
            "target_condition": "Near Mint", "target_price_date": (price or {}).get("captured_at"),
            "target_price_source": (price or {}).get("source"), "price_selection_reason": (price or {}).get("price_selection_reason"),
            "collector_appeal": (score or {}).get("collector_card_appeal_score"),
            "pokemon_or_trainer_component": (score or {}).get("subject_baseline_score"),
            "artist_component": (score or {}).get("artist_recognition_score"),
            "playability_component": (score or {}).get("playability_score"),
            "collector_model_version": MODEL_VERSION, "collector_model_run_id": MODEL_RUN_ID,
            "pull_probability": probability, "negative_log10_pull_probability": (-__import__("math").log10(probability) if probability else None),
            "expected_packs": (1.0 / probability if probability else None),
            "scarcity_calculation_run_id": (rate or {}).get("calculation_run_id"),
            "treatment_taxonomy_version": TAXONOMY_VERSION,
            "point_in_time_safe_for_current_value": True,
            "eligible_v1_strict": not reasons, "exclusion_reasons": sorted(reasons),
        })

    eligible = [x for x in out if x["eligible_v1_strict"]]
    fingerprint_fields = [
        "canonical_card_id", "card_variant_id", "target_market_price_usd", "target_price_date",
        "collector_model_run_id", "scarcity_calculation_run_id", "treatment_taxonomy_version",
    ]
    fingerprint = canonical_hash([{k: x.get(k) for k in fingerprint_fields} for x in eligible])
    probe_tables = [
        "card_variant_price_observations", "pokemon_canonical_card_market_prices_latest",
        "pokemon_card_collector_appeal_scores", "simulation_card_variant_pull_rates",
        "psa_population", "grading_population", "completed_sales", "card_listings",
    ]
    dates = [str(x.get("captured_at"))[:10] for x in prices if x.get("captured_at")]
    audit = {
        "auditVersion": BUILDER_VERSION, "generatedAt": datetime.now(timezone.utc).isoformat(),
        "asOfDate": today.isoformat(), "researchOnly": True, "databaseWrites": 0,
        "authorityBindings": {"collectorModelVersion": MODEL_VERSION, "collectorModelRunId": MODEL_RUN_ID,
                              "treatmentTaxonomyVersion": TAXONOMY_VERSION,
                              "treatmentTaxonomyFingerprint": TREATMENT_FINGERPRINT},
        "liveCounts": {"canonicalCards": len(cards), "sets": len(sets), "eras": len(eras),
                       "canonicalCurrentPrices": len(prices), "collectorScores": len(appeal),
                       "acceptedScarcityRuns": len(accepted_runs), "acceptedScarcityRows": len(rates),
                       "strictEligibleRows": len(eligible), "strictEligibleSets": len({x["set_id"] for x in eligible}),
                       "strictEligibleRootSets": len({x["root_set_id"] for x in eligible}),
                       "strictEligibleEras": len({x["era"] for x in eligible})},
        "exclusionCountsOverCanonicalUniverse": dict(sorted(exclusions.items())),
        "priceAuthority": {"table": "pokemon_canonical_card_market_prices_latest", "condition": "Near Mint",
                           "currency": "USD", "nature": "TCGPlayer market price; listing-derived, not completed sales",
                           "currentRows": len(prices), "oldestSelectedDate": min(dates) if dates else None,
                           "newestSelectedDate": max(dates) if dates else None,
                           "sourceCounts": dict(Counter(str(x.get("source")) for x in prices)),
                           "selectionReasonCounts": dict(Counter(str(x.get("price_selection_reason")) for x in prices)),
                           "historyTable": "card_variant_price_observations",
                           "historyRows": _count(client, "card_variant_price_observations")},
        "schemaProbes": {table: _probe(client, table) for table in probe_tables},
        "datasetFingerprint": fingerprint,
        "eligibilityPolicy": "English canonical cards; raw preferred physical variant; Near Mint USD; exact identity, frozen Collector V7, accepted exact pull scarcity, Treatment V3, and release date required.",
        "unsupportedCardPolicy": "Exclude from strict V1; retain explicit reason for later low-confidence cohorts.",
        "scopeDecision": "MODERN_V1_ONLY_VINTAGE_DEFERRED",
        "gradedCardDecision": "EXCLUDED_DISTINCT_PRODUCT_WITHOUT_AUTHORITY",
        "peerMarketDecision": "RETAIN_AS_SEPARATE_MODEL_D_RESEARCH_CANDIDATE_ONLY",
        "primaryValidation": "LEAVE_CANONICAL_ROOT_SET_OUT_NESTED_GROUPED",
        "f2Blockers": ["Vintage lacks compatible exact scarcity and surviving-NM supply authority",
                       "Graded and non-NM targets lack a canonical cross-grade/condition authority",
                       "Supply, liquidity, completed-sales, and grading features are unavailable and cannot support claims"],
        "f2Readiness": "READY_FOR_STRICT_MODERN_MODEL_FITTING",
        "finalStatus": "INDEX_FAIR_VALUE_F1_READY",
    }
    return out, audit


def main() -> int:
    load_dotenv(ROOT / "backend/.env", override=False)
    from backend.db.clients.supabase_client import create_service_role_client
    rows, audit = build(create_service_role_client())
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    (ARTIFACT_DIR / "index_fair_value_f1_dataset.json").write_text(
        json.dumps({"manifest": audit, "rows": rows}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (ARTIFACT_DIR / "index_fair_value_f1_audit.json").write_text(
        json.dumps(audit, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(audit, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
