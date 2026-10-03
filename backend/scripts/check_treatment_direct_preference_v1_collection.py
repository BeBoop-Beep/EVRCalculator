"""Coverage monitor for Treatment Direct Preference V1 collection.

Reports collection readiness only. It does not expose aggregate preference
directions and performs no writes.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from typing import Any

from dotenv import load_dotenv

STUDY_VERSION = "treatment_direct_preference_v1"
SCHEDULE_FINGERPRINT = "4b08be6bd2fe4c3b1dde4627da0780f3832740c53ee411c7df81a2f976830055"
MIN_EVALUABLE = 40
MIN_NON_TIE = 20


def _paged(query_factory):
    rows = []
    start = 0
    while True:
        part = list(query_factory().range(start, start + 999).execute().data or [])
        rows.extend(dict(row) for row in part)
        if len(part) < 1000:
            return rows
        start += 1000


def status(db: Any) -> dict[str, Any]:
    responses = _paged(
        lambda: db.table("pokemon_treatment_preference_v1_responses")
        .select("underlying_pair_id,response")
        .eq("study_version", STUDY_VERSION)
        .eq("schedule_fingerprint", SCHEDULE_FINGERPRINT)
    )
    claims = _paged(
        lambda: db.table("pokemon_treatment_preference_v1_block_claims")
        .select("block_index,session_hash,completed_at,expires_at")
        .eq("study_version", STUDY_VERSION)
        .eq("schedule_fingerprint", SCHEDULE_FINGERPRINT)
    )

    pair_total = Counter()
    pair_non_tie = Counter()
    for row in responses:
        pid = str(row["underlying_pair_id"])
        pair_total[pid] += 1
        if str(row["response"]) != "TIE":
            pair_non_tie[pid] += 1

    ready_pairs = {
        pid
        for pid, count in pair_total.items()
        if count >= MIN_EVALUABLE and pair_non_tie[pid] >= MIN_NON_TIE
    }
    completed_blocks = sum(row.get("completed_at") is not None for row in claims)
    active_claims = sum(
        row.get("session_hash") is not None and row.get("completed_at") is None
        for row in claims
    )

    return {
        "study_version": STUDY_VERSION,
        "schedule_fingerprint": SCHEDULE_FINGERPRINT,
        "response_count": len(responses),
        "completed_blocks": completed_blocks,
        "active_or_abandoned_claims": active_claims,
        "ready_pairs": len(ready_pairs),
        "total_pairs": 135,
        "pair_response_min": min(pair_total.values()) if pair_total else 0,
        "pair_response_max": max(pair_total.values()) if pair_total else 0,
        "collection_minimum_reached": len(ready_pairs) == 135,
        "preference_directions_exposed": False,
        "production_writes": 0,
    }


def main(argv=None) -> int:
    argparse.ArgumentParser().parse_args(argv)
    from backend.db.clients.supabase_client import create_service_role_client

    load_dotenv(override=False)
    print(json.dumps(status(create_service_role_client()), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
