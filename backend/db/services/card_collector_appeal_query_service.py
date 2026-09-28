"""Page-first read service for the current prepared Card Collector rankings."""
from __future__ import annotations

import math
import time
from typing import Any, Dict, Iterable, Optional
from uuid import UUID

SORT_COLUMNS = {
    "rank": "rank", "collector_appeal": "collector_appeal_score",
    "pokemon_appeal": "pokemon_appeal", "trainer_appeal": "trainer_appeal",
    "artist_appeal": "artist_appeal", "playability": "playability",
    "pull_probability": "modeled_pull_probability", "name": "card_name",
}
COMPONENT_LENSES = {
    "overall": ("collector_appeal_score", None),
    "pokemon": ("pokemon_appeal", "pokemon"),
    "trainer": ("trainer_appeal", "trainer"),
    "artist": ("artist_appeal", None),
    "playability": ("playability", None),
}
RANKING_COLUMNS = (
    "model_run_id,pokemon_canonical_card_id,set_id,card_name,rarity,"
    "collector_appeal_score,rank,cohort_size,status,methodology_version,"
    "subject_policy,pokemon_appeal,trainer_appeal,artist_appeal,playability,"
    "treatment_category,modeled_pull_probability"
)
SCORE_COLUMNS = (
    "pokemon_canonical_card_id,subject_policy,subject_baseline_score,"
    "artist_recognition_score,playability_score,confidence,component_inputs_json"
)
_POINTER_TTL_SECONDS = 30.0
_pointer_cache: Dict[int, tuple[float, Dict[str, Any]]] = {}


def _number(value: Any) -> Optional[float]:
    return None if value is None else float(value)


def _rows(response: Any) -> list[Dict[str, Any]]:
    return list(getattr(response, "data", None) or [])


def _by_id(rows: Iterable[Dict[str, Any]], key: str = "id") -> Dict[str, Dict[str, Any]]:
    return {str(row[key]): row for row in rows if row.get(key) is not None}


def _current_pointer(client: Any) -> Dict[str, Any]:
    cache_key = id(client)
    cached = _pointer_cache.get(cache_key)
    now = time.monotonic()
    if cached and now - cached[0] < _POINTER_TTL_SECONDS:
        return cached[1]
    rows = _rows(client.table("pokemon_collector_appeal_current")
                 .select("model_run_id,model_version,as_of_date")
                 .eq("scope", "pokemon").limit(1).execute())
    pointer = rows[0] if rows else {}
    _pointer_cache[cache_key] = (now, pointer)
    return pointer


def _public_row(row: Dict[str, Any]) -> Dict[str, Any]:
    policy = row.get("subject_policy")
    baseline = _number(row.get("subject_baseline_score"))
    return {
        "modelRunId": row.get("model_run_id"), "modelVersion": row.get("model_version"),
        "asOfDate": row.get("as_of_date"), "canonicalCardId": row.get("pokemon_canonical_card_id"),
        "cardName": row.get("card_name"), "setId": row.get("set_id"), "setName": row.get("set_name"),
        "setCanonicalKey": row.get("set_canonical_key"), "eraId": row.get("era_id"),
        "eraName": row.get("era_name"), "rarity": row.get("rarity"), "imageSmallUrl": row.get("image_small_url"),
        "collectorAppeal": _number(row.get("collector_appeal_score")), "rank": row.get("rank"),
        "cohortSize": row.get("cohort_size"), "pokemonAppeal": baseline if policy == "pokemon" else None,
        "trainerAppeal": baseline if policy == "trainer" else None, "subjectType": row.get("subject_type"),
        "subjectIdentity": row.get("subject_identity"), "artistAppeal": _number(row.get("artist_recognition_score")),
        "artistStatus": row.get("artist_status"), "artistNames": row.get("artist_names") or [],
        "playability": _number(row.get("playability_score")), "playabilityStatus": row.get("playability_status"),
        "playabilityConfidence": row.get("playability_confidence"), "treatmentCategory": row.get("treatment_category"),
        "treatmentStatus": row.get("treatment_status"), "modeledPullProbability": _number(row.get("modeled_pull_probability")),
        "methodologyVersion": row.get("methodology_version"),
    }


def _resolve_era_set_ids(client: Any, era: str) -> list[str]:
    try:
        era_id = str(UUID(str(era)))
    except (TypeError, ValueError):
        found = _rows(client.table("eras").select("id").eq("canonical_key", str(era)).limit(1).execute())
        if not found:
            found = _rows(client.table("eras").select("id").eq("name", str(era)).limit(1).execute())
        if not found:
            return []
        era_id = str(found[0]["id"])
    return [str(row["id"]) for row in _rows(
        client.table("sets").select("id").eq("era_id", era_id).execute()
    )]


def query_card_collector_appeal(client: Any, *, page: int = 1, page_size: int = 50,
                                search: Optional[str] = None, era: Optional[str] = None,
                                set_id: Optional[str] = None, rarity: Optional[str] = None,
                                sort: str = "rank", direction: str = "asc",
                                lens: str = "overall") -> Dict[str, Any]:
    page = max(1, int(page)); page_size = min(100, max(1, int(page_size)))
    lens = str(lens).lower()
    if lens not in COMPONENT_LENSES:
        raise ValueError("unsupported Collector lens")
    component_column, subject_policy = COMPONENT_LENSES[lens]
    # Component lenses have their own ranked cohort.  They never reuse the
    # global Collector rank, whose cross-domain meaning is intentionally not
    # asserted by the current production model.
    sort_key = str(sort).lower()
    sort_column = component_column if lens != "overall" and sort_key in {"rank", "collector_appeal"} else SORT_COLUMNS.get(sort_key)
    if not sort_column:
        raise ValueError("unsupported sort")
    direction = str(direction).lower()
    if direction not in {"asc", "desc"}:
        raise ValueError("direction must be asc or desc")

    pointer = _current_pointer(client)
    model_run_id = pointer.get("model_run_id")
    if not model_run_id:
        return {"available": False, "modelRunId": None, "modelVersion": None, "asOfDate": None,
                "page": page, "pageSize": page_size, "total": 0, "totalPages": 0, "rows": []}

    query = (client.table("pokemon_card_collector_appeal_rankings")
             .select(RANKING_COLUMNS, count="exact").eq("model_run_id", str(model_run_id)))
    component_cohort_size = None
    component_page = None
    if lens != "overall":
        component_set_ids = None
        if era:
            component_set_ids = _resolve_era_set_ids(client, str(era))
            if not component_set_ids:
                component_set_ids = []
        if set_id:
            component_set_ids = [str(set_id)] if component_set_ids is None else [value for value in component_set_ids if value == str(set_id)]
        response = client.rpc("get_pokemon_card_component_rankings_v1", {
            "p_model_run_id": str(model_run_id), "p_lens": lens,
            "p_set_ids": component_set_ids, "p_search": str(search).strip()[:100] if search else None,
            "p_rarity": rarity, "p_offset": (page - 1) * page_size, "p_limit": page_size,
        }).execute()
        component_page = getattr(response, "data", None) or {}
    if lens == "overall" and search:
        query = query.ilike("card_name", f"%{str(search).strip()[:100]}%")
    if lens == "overall" and era:
        era_set_ids = _resolve_era_set_ids(client, str(era))
        if not era_set_ids:
            return {"available": True, "modelRunId": str(model_run_id),
                    "modelVersion": pointer.get("model_version"), "asOfDate": pointer.get("as_of_date"),
                    "page": page, "pageSize": page_size, "total": 0, "totalPages": 0, "rows": []}
        query = query.in_("set_id", era_set_ids)
    if lens == "overall" and set_id:
        query = query.eq("set_id", set_id)
    if lens == "overall" and rarity:
        query = query.eq("rarity", rarity)
    start = (page - 1) * page_size
    component_default_desc = lens != "overall" and sort_key in {"rank", "collector_appeal"}
    if component_page is None:
        response = (query.order(sort_column, desc=(direction == "desc" or component_default_desc), nullsfirst=False)
                    .order("pokemon_canonical_card_id").range(start, start + page_size - 1).execute())
        ranking_rows = _rows(response)
        total = int(getattr(response, "count", None) or 0)
    else:
        ranking_rows = list(component_page.get("rows") or [])
        total = int(component_page.get("total") or 0)
        component_cohort_size = int(component_page.get("componentCohortSize") or 0)

    card_ids = [str(row["pokemon_canonical_card_id"]) for row in ranking_rows]
    set_ids = sorted({str(row["set_id"]) for row in ranking_rows if row.get("set_id")})
    cards = _by_id(_rows(client.table("pokemon_canonical_cards").select("id,image_small_url")
                         .in_("id", card_ids).execute())) if card_ids else {}
    scores = _by_id(_rows(client.table("pokemon_card_collector_appeal_scores").select(SCORE_COLUMNS)
                          .eq("model_run_id", str(model_run_id))
                          .in_("pokemon_canonical_card_id", card_ids).execute()), "pokemon_canonical_card_id") if card_ids else {}
    sets = _by_id(_rows(client.table("sets").select("id,name,canonical_key,era_id")
                        .in_("id", set_ids).execute())) if set_ids else {}
    era_ids = sorted({str(row["era_id"]) for row in sets.values() if row.get("era_id")})
    eras = _by_id(_rows(client.table("eras").select("id,name,canonical_key")
                        .in_("id", era_ids).execute())) if era_ids else {}

    enriched = []
    for page_index, ranking in enumerate(ranking_rows):
        card_id = str(ranking["pokemon_canonical_card_id"])
        set_row = sets.get(str(ranking.get("set_id")), {})
        era_row = eras.get(str(set_row.get("era_id")), {})
        component = scores.get(card_id, {})
        inputs = component.get("component_inputs_json") or {}
        enriched.append({**ranking, **component,
                         "component_rank": ranking.get("component_rank") if lens != "overall" else ranking.get("rank"),
                         "model_version": pointer.get("model_version"), "as_of_date": pointer.get("as_of_date"),
                         "image_small_url": cards.get(card_id, {}).get("image_small_url"),
                         "set_name": set_row.get("name"), "set_canonical_key": set_row.get("canonical_key"),
                         "era_id": set_row.get("era_id"), "era_name": era_row.get("name"),
                         "subject_type": inputs.get("subjectType"), "subject_identity": inputs.get("subjectIdentity"),
                         "artist_status": inputs.get("artistEvidenceStatus"), "artist_names": inputs.get("artistNames") or [],
                         "playability_status": "scored" if component.get("playability_score") is not None else "unavailable",
                         "playability_confidence": component.get("confidence"),
                         "treatment_status": (inputs.get("treatmentDiagnostic") or {}).get("status")})

    public_rows = [_public_row(row) for row in enriched]
    if lens != "overall":
        for row, source in zip(public_rows, enriched):
            row["rank"] = source["component_rank"]
            row["cohortSize"] = component_cohort_size
            row["componentScore"] = _number(source.get(component_column))
    return {"available": True, "modelRunId": str(model_run_id),
            "modelVersion": pointer.get("model_version"), "asOfDate": pointer.get("as_of_date"),
            "lens": lens,
            "definitionStatus": "production_overall_price_blind_v7" if lens == "overall" else "component_specific_uncalibrated_domain",
            "rankSemantics": "published_global_overall" if lens == "overall" else "global_component_cohort",
            "componentCohortSize": component_cohort_size if lens != "overall" else None,
            "page": page, "pageSize": page_size, "total": total,
            "totalPages": math.ceil(total / page_size) if total else 0,
            "rows": public_rows}
