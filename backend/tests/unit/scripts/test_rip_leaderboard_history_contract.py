from pathlib import Path

import pytest

from backend.scripts import build_pokemon_explore_rankings_snapshot as command


def _row(*, target_count=1, ca7_version="ca7-v1"):
    targets = [{
        "set_id": f"00000000-0000-0000-0000-{index:012d}",
        "canonical_key": f"set-{index}",
        "rip": {"score": 80 - index, "rank": index + 1},
        "ripCore": {"score": 75 - index, "rank": index + 1},
        "openingExperience": {"collectorAppeal": {"version": ca7_version}},
        "pack_cost": 5,
    } for index in range(target_count)]
    return {"ranking_payload_json": {
        "targets": targets,
        "meta": {
            "comparisonSnapshots": {"currentMarketDate": "2026-08-01"},
            "snapshot": {"builtAt": "2026-08-01T08:00:00Z"},
            "publicAnalyticsCohort": {
                "version": "cohort-v1",
                "eligibleSetCount": target_count,
                "overallRanked": {"rankedSetCount": 1},
            },
            "ripWeightsConfig": {
                "overallRip": {"version": "overall-v4"},
                "financialRip": {"version": "financial-v2"},
            },
        },
    }}


def test_complete_cohort_builds_history_publication_contract():
    snapshot, rows = command._publication_contract(_row())
    assert snapshot["market_date"] == "2026-08-01"
    assert snapshot["eligible_cohort_count"] == 1
    assert len(rows) == 1


def test_incomplete_cohort_fails_closed():
    with pytest.raises(RuntimeError, match="incomplete Overall RIP cohort"):
        command._publication_contract(_row(target_count=2))


def test_missing_or_mixed_ca7_version_fails_closed():
    with pytest.raises(RuntimeError, match="incompatible CA7 versions"):
        command._publication_contract(_row(ca7_version=None))


def test_atomic_rpc_is_idempotent_and_promotes_latest_after_history_rows():
    migration = (
        Path(__file__).resolve().parents[3]
        / "db/migrations/049_add_pokemon_public_rip_leaderboard_history.sql"
    ).read_text(encoding="utf-8")
    assert "ON CONFLICT (market_date, cohort_version, overall_rip_version, financial_rip_version, ca7_version)" in migration
    assert migration.index("INSERT INTO pokemon_public_rip_leaderboard_rows") < migration.index(
        "INSERT INTO pokemon_explore_rankings_snapshot_latest"
    )
