"""Export Treatment Direct Preference V1 responses for the frozen analyzer.

Research only. Reads only the isolated preference-response table and writes a
local JSON artifact. No production mutations.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
STUDY_VERSION = "treatment_direct_preference_v1"
SCHEDULE_FINGERPRINT = "4b08be6bd2fe4c3b1dde4627da0780f3832740c53ee411c7df81a2f976830055"


def _paged(query_factory):
    rows = []
    start = 0
    while True:
        part = list(query_factory().range(start, start + 999).execute().data or [])
        rows.extend(dict(row) for row in part)
        if len(part) < 1000:
            return rows
        start += 1000


def export_rows(db: Any) -> dict[str, Any]:
    rows = _paged(
        lambda: db.table("pokemon_treatment_preference_v1_responses")
        .select(
            "session_hash,underlying_pair_id,left_card_id,right_card_id,"
            "randomized_orientation_receipt,response,submitted_at"
        )
        .eq("study_version", STUDY_VERSION)
        .eq("schedule_fingerprint", SCHEDULE_FINGERPRINT)
        .order("submitted_at")
    )
    responses = [
        {
            "study_version": STUDY_VERSION,
            "anonymous_session_id": str(row["session_hash"]),
            "underlying_pair_id": str(row["underlying_pair_id"]),
            "left_card_id": str(row["left_card_id"]),
            "right_card_id": str(row["right_card_id"]),
            "randomized_orientation_receipt": str(row["randomized_orientation_receipt"]),
            "response": str(row["response"]),
            "submitted_at": str(row["submitted_at"]),
        }
        for row in rows
    ]
    pair_counts = Counter(row["underlying_pair_id"] for row in responses)
    return {
        "study_version": STUDY_VERSION,
        "schedule_fingerprint": SCHEDULE_FINGERPRINT,
        "response_count": len(responses),
        "session_count": len({row["anonymous_session_id"] for row in responses}),
        "pair_count_with_responses": len(pair_counts),
        "pair_response_min": min(pair_counts.values()) if pair_counts else 0,
        "pair_response_max": max(pair_counts.values()) if pair_counts else 0,
        "responses": responses,
        "production_writes": 0,
    }


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args(argv)

    load_dotenv(ROOT / "backend/.env", override=False)
    from backend.db.clients.supabase_client import create_service_role_client

    result = export_rows(create_service_role_client())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result["responses"], indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {k: v for k, v in result.items() if k != "responses"},
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
