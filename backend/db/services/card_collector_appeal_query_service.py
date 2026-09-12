"""Plus read projection for current prepared card Collector Appeal ranks."""
from __future__ import annotations

import math
from typing import Any, Dict, Optional
from uuid import UUID

SORT_COLUMNS = {
    "rank": "rank", "collector_appeal": "collector_appeal_score",
    "pokemon_appeal": "pokemon_appeal", "trainer_appeal": "trainer_appeal",
    "artist_appeal": "artist_recognition_score", "playability": "playability_score",
    "pull_probability": "modeled_pull_probability", "name": "card_name",
}


def _number(value: Any) -> Optional[float]:
    return None if value is None else float(value)


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


def query_card_collector_appeal(client: Any, *, page: int = 1, page_size: int = 50,
                                search: Optional[str] = None, era: Optional[str] = None,
                                set_id: Optional[str] = None, rarity: Optional[str] = None,
                                sort: str = "rank", direction: str = "asc") -> Dict[str, Any]:
    page = max(1, int(page)); page_size = min(100, max(1, int(page_size)))
    sort_key = str(sort).lower(); sort_column = SORT_COLUMNS.get(sort_key)
    if not sort_column: raise ValueError("unsupported sort")
    direction = str(direction).lower()
    if direction not in {"asc", "desc"}: raise ValueError("direction must be asc or desc")
    query = client.table("pokemon_card_collector_appeal_rankings_current_v").select("*", count="exact")
    if search: query = query.ilike("card_name", f"%{str(search).strip()[:100]}%")
    if era:
        try: era_id = str(UUID(str(era)))
        except ValueError:
            rows = list(client.table("eras").select("id").eq("canonical_key", str(era)).limit(1).execute().data or [])
            if not rows: rows = list(client.table("eras").select("id").eq("name", str(era)).limit(1).execute().data or [])
            era_id = str(rows[0]["id"]) if rows else "00000000-0000-0000-0000-000000000000"
        query = query.eq("era_id", era_id)
    if set_id: query = query.eq("set_id", set_id)
    if rarity: query = query.eq("rarity", rarity)
    start = (page - 1) * page_size
    response = (query.order(sort_column, desc=direction == "desc", nullsfirst=False)
                .order("pokemon_canonical_card_id").range(start, start + page_size - 1).execute())
    rows = list(response.data or []); total = int(getattr(response, "count", None) or 0)
    first = rows[0] if rows else {}
    return {"available": bool(rows) or total == 0, "modelRunId": first.get("model_run_id"),
            "modelVersion": first.get("model_version"), "asOfDate": first.get("as_of_date"),
            "page": page, "pageSize": page_size, "total": total,
            "totalPages": math.ceil(total / page_size) if total else 0,
            "rows": [_public_row(row) for row in rows]}
