"""Deterministic global card ranks for scored Collector Appeal cards."""
from __future__ import annotations

from typing import Any, Iterable, Mapping

METHODOLOGY_VERSION = "card_collector_appeal_global_ordinal_v1"


def build_card_collector_ranking_rows(
    card_rows: Iterable[Mapping[str, Any]], model_run_id: str
) -> list[dict[str, Any]]:
    scored = [
        row for row in card_rows
        if row.get("score_status") == "scored"
        and row.get("collector_card_appeal_score") is not None
    ]
    scored.sort(key=lambda row: (
        -float(row["collector_card_appeal_score"]),
        str(row["pokemon_canonical_card_id"]),
    ))
    cohort_size = len(scored)
    return [
        {
            "model_run_id": model_run_id,
            "pokemon_canonical_card_id": row["pokemon_canonical_card_id"],
            "collector_appeal_score": row["collector_card_appeal_score"],
            "rank": rank,
            "cohort_size": cohort_size,
            "status": "scored",
            "methodology_version": METHODOLOGY_VERSION,
        }
        for rank, row in enumerate(scored, 1)
    ]
