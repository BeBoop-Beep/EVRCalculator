"""Read-time builder for Universal Set Desirability V4 contextual chase.

V3 remains in ``universal_set_desirability_service``.  This module deliberately
requires the simulation input rows from the exact latest authoritative RIP run;
it never substitutes checklist rarity or a different run when evidence is absent.
"""

from __future__ import annotations

from collections import defaultdict
import re
from typing import Any, Dict, List, Mapping, Sequence

from backend.db.clients.supabase_client import public_read_client
from backend.db.services.universal_set_desirability_service import (
    _chunked, _load_authoritative_species_ranks, _load_current_component_rows,
    _paged_select, _to_optional_float,
)
from backend.desirability.card_links import CARD_DESIRABILITY_LINK_TABLE
from backend.desirability.card_appeal import normalize_pull_probability
from backend.desirability.universal_set_desirability import (
    compute_universal_set_desirability_v4, rank_universal_scores,
)


def _latest_runs(set_ids: Sequence[str]) -> Dict[str, Dict[str, Any]]:
    rows = _paged_select(lambda: public_read_client.table("explore_rip_statistics_latest")
                         .select("set_id,calculation_run_id,run_at")
                         .in_("set_id", list(set_ids)).order("run_at", desc=True))
    return {str(row["set_id"]): row for row in rows if row.get("set_id") and row.get("calculation_run_id")}


def _card_evidence(run_ids: Sequence[str]) -> Dict[str, List[Dict[str, Any]]]:
    cards: List[Dict[str, Any]] = []
    for chunk in _chunked(list(run_ids), 20):
        cards.extend(_paged_select(lambda chunk=list(chunk): public_read_client.table("simulation_input_cards")
                                   .select("calculation_run_id,card_id,card_variant_id,card_name,rarity_bucket,price_used,effective_pull_rate,ev_contribution")
                                   .in_("calculation_run_id", chunk)))
    # simulation_input_cards.card_id is the legacy ``cards`` UUID, while the
    # desirability link table keys the canonical-card UUID. Resolve through the
    # shared Pokemon TCG API identity; never fuzzy-match names here.
    card_ids = sorted({str(row["card_id"]) for row in cards if row.get("card_id")})
    legacy_rows: List[Dict[str, Any]] = []
    for chunk in _chunked(card_ids, 200):
        legacy_rows.extend(_paged_select(lambda chunk=list(chunk): public_read_client.table("cards")
                                         .select("id,set_id,name,rarity,pokemon_tcg_api_id").in_("id", chunk)))
    legacy_by_id = {str(row["id"]): row for row in legacy_rows if row.get("id")}
    api_by_legacy = {str(row["id"]): str(row["pokemon_tcg_api_id"])
                     for row in legacy_rows if row.get("id") and row.get("pokemon_tcg_api_id")}
    variant_ids = sorted({str(row["card_variant_id"]) for row in cards if row.get("card_variant_id")})
    variant_rows: List[Dict[str, Any]] = []
    for chunk in _chunked(variant_ids, 200):
        variant_rows.extend(_paged_select(lambda chunk=list(chunk): public_read_client.table("card_variants")
                                          .select("id,card_id,pokemon_tcg_api_id").in_("id", chunk)))
    api_by_variant = {str(row["id"]): str(row["pokemon_tcg_api_id"])
                      for row in variant_rows if row.get("id") and row.get("pokemon_tcg_api_id")}
    api_ids = sorted(set(api_by_legacy.values()) | set(api_by_variant.values()))
    canonical_rows: List[Dict[str, Any]] = []
    for chunk in _chunked(api_ids, 200):
        canonical_rows.extend(_paged_select(lambda chunk=list(chunk): public_read_client.table("pokemon_canonical_cards")
                                            .select("id,pokemon_tcg_api_card_id,rarity")
                                            .in_("pokemon_tcg_api_card_id", chunk)))
    set_ids = sorted({str(row["set_id"]) for row in legacy_rows if row.get("set_id")})
    for chunk in _chunked(set_ids, 100):
        canonical_rows.extend(_paged_select(lambda chunk=list(chunk): public_read_client.table("pokemon_canonical_cards")
                                            .select("id,set_id,name,pokemon_tcg_api_card_id,rarity")
                                            .in_("set_id", chunk)))
    canonical_by_api = {str(row["pokemon_tcg_api_card_id"]): row for row in canonical_rows
                        if row.get("pokemon_tcg_api_card_id")}
    def norm(value: Any) -> str:
        return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())
    canonical_by_set_name: Dict[tuple[str, str], List[Dict[str, Any]]] = defaultdict(list)
    for row in canonical_rows:
        canonical_by_set_name[(str(row.get("set_id")), norm(row.get("name")))].append(row)
    canonical_ids = sorted({str(row["id"]) for row in canonical_rows if row.get("id")})
    links: List[Dict[str, Any]] = []
    for chunk in _chunked(canonical_ids, 200):
        links.extend(_paged_select(lambda chunk=list(chunk): public_read_client.table(CARD_DESIRABILITY_LINK_TABLE)
                                   .select("pokemon_canonical_card_id,pokemon_reference_id,contribution_weight,is_hit_eligible,hit_policy_version")
                                   .in_("pokemon_canonical_card_id", chunk)))
    links_by_card: Dict[str, List[Mapping[str, Any]]] = defaultdict(list)
    for link in links:
        if link.get("is_hit_eligible") is not False:
            links_by_card[str(link.get("pokemon_canonical_card_id"))].append(link)
    by_run: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for card in cards:
        api_id = api_by_variant.get(str(card.get("card_variant_id"))) or api_by_legacy.get(str(card.get("card_id")))
        canonical = canonical_by_api.get(str(api_id)) or {}
        if not canonical:
            legacy = legacy_by_id.get(str(card.get("card_id"))) or {}
            matches = canonical_by_set_name.get((str(legacy.get("set_id")), norm(legacy.get("name") or card.get("card_name")))) or []
            if len(matches) == 1:
                canonical = matches[0]
        canonical_id = str(canonical.get("id")) if canonical.get("id") else None
        candidates = links_by_card.get(str(canonical_id)) or []
        # Same canonical primary-subject rule used by card_links: largest
        # contribution weight. Ties are deterministic by reference id.
        usable = []
        for link in candidates:
            try:
                ref = int(link.get("pokemon_reference_id"))
                weight = float(link.get("contribution_weight") if link.get("contribution_weight") is not None else 1.0)
            except (TypeError, ValueError):
                continue
            if weight > 0:
                usable.append((weight, -ref, ref))
        reference_id = max(usable)[2] if usable else None
        by_run[str(card.get("calculation_run_id"))].append({
            "pokemon_reference_id": reference_id,
            "card_id": canonical_id, "card_name": card.get("card_name"),
            "rarity": canonical.get("rarity"),
            "rarity_bucket": card.get("rarity_bucket"),
            "market_value": _to_optional_float(card.get("price_used")),
            "modeled_probability": normalize_pull_probability(card.get("effective_pull_rate")),
            "ev_contribution": _to_optional_float(card.get("ev_contribution")),
        })
    return by_run


def build_contextual_desirability_bundle(*, min_card_share: float = 0.01, always_include_top_n: int = 5) -> Dict[str, Any]:
    selection = _load_current_component_rows()
    source_rows = selection["selected"]
    runs = _latest_runs(list(source_rows))
    evidence_by_run = _card_evidence([str(row["calculation_run_id"]) for row in runs.values()])
    ranks = _load_authoritative_species_ranks()
    rows = []
    for set_id, source in source_rows.items():
        run = runs.get(set_id)
        evidence = evidence_by_run.get(str((run or {}).get("calculation_run_id")), [])
        result = compute_universal_set_desirability_v4(
            source.get("subject_rollups_json") or [], evidence,
            min_card_share=min_card_share, always_include_top_n=always_include_top_n,
        )
        modeled = []
        for position, subject in enumerate(result.get("modeled_subjects") or [], start=1):
            representative = subject.get("representative_chase_card") or {}
            ref = subject.get("pokemon_reference_id")
            modeled.append({
                "name": subject.get("subject_name"), "pokemonReferenceId": ref,
                "desirabilityScore": _to_optional_float(subject.get("max_desirability_score")),
                "speciesRank": ranks.get(int(ref)) if ref is not None else None,
                "setRosterPosition": position, "role": subject.get("role"),
                "chasePriorityRank": subject.get("chase_priority_rank"),
                "representativeCard": {
                    "id": representative.get("card_id"), "name": representative.get("card_name"),
                    "rarity": representative.get("rarity") or representative.get("rarity_bucket"),
                    "modeledProbability": representative.get("modeled_probability"),
                    "evContribution": representative.get("ev_contribution"),
                    "evShare": representative.get("ev_share"),
                    "cardChaseRank": representative.get("card_chase_rank"),
                } if representative else None,
            })
        rows.append({"set_id": set_id, "set_name": source.get("set_name"),
                     "set_canonical_key": source.get("set_canonical_key"), **result,
                     "modeled_pokemon": modeled,
                     "source_calculation_run_id": (run or {}).get("calculation_run_id"),
                     "source_run_at": (run or {}).get("run_at")})
    rank_universal_scores([row for row in rows if row.get("score") is not None])
    return {"payloads": {row["set_id"]: row for row in rows},
            "sourceSelection": selection.get("counts"),
            "availableCount": sum(row.get("score") is not None for row in rows)}
