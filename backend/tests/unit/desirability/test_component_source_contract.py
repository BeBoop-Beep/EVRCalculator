"""The component table's REAL unique key, and the version-exact source contract.

WHY THIS FILE EXISTS
--------------------
The previous rollout wrote ``upsert(payloads, on_conflict="set_id")`` and every
test passed, because the test fake accepted any string as a conflict key. The
fake was more permissive than Postgres, so it validated a statement the database
would have rejected - and the tests reported that as safety.

These tests encode the schema itself:

    pokemon_set_desirability_component_unique_key UNIQUE
      (set_id, scoring_version, hit_policy_version,
       composite_scoring_version, fan_popularity_snapshot_id, config_fingerprint)

verified against ``pg_indexes`` in production. ``set_id`` alone is NOT unique -
511 rows across 171 sets - so a fake that accepts ``on_conflict="set_id"`` is
lying, and :class:`SchemaAwareTable` refuses to.
"""

from __future__ import annotations

from backend.desirability.component_source import (
    COMPONENT_NON_UNIQUE_COLUMNS,
    COMPONENT_PRIMARY_KEY,
    COMPONENT_SOURCE_COLUMNS,
    COMPONENT_UNIQUE_KEY,
    DUPLICATE_CURRENT_COMPONENT_SOURCE_ROW,
    EXPECTED_COMPOSITE_SCORING_VERSION,
    EXPECTED_HIT_POLICY_VERSION,
    EXPECTED_SCORING_VERSION,
    MISSING_CURRENT_COMPONENT_SOURCE_ROW,
    build_source_identity,
    expected_source_versions,
    matches_expected_versions,
    rebuild_command_for,
    select_component_source_rows,
    source_identity_matches_row,
)

# The production hit policies observed in the component table, newest build first.
V1 = "pokemon_card_desirability_hit_policy_v1"
V2 = "pokemon_card_desirability_hit_policy_v2"
V2_CLEANUP = "pokemon_card_desirability_hit_policy_v2_coverage_cleanup"


def _row(set_id, hit_policy, *, row_id=None, built_at="2026-06-14T22:59:34Z", **overrides):
    row = {
        "id": row_id or f"{set_id}-{hit_policy}",
        "set_id": set_id,
        "set_name": f"Set {set_id}",
        "set_canonical_key": "evolvingSkies",
        "scoring_version": EXPECTED_SCORING_VERSION,
        "hit_policy_version": hit_policy,
        "composite_scoring_version": EXPECTED_COMPOSITE_SCORING_VERSION,
        "fan_popularity_snapshot_id": "snap-1",
        "config_fingerprint": f"cfg-{set_id}",
        "set_desirability_score": 70.0,
        "built_at": built_at,
        "updated_at": built_at,
        "diagnostics_json": {},
        "subject_rollups_json": [],
    }
    row.update(overrides)
    return row


# ---------------------------------------------------------------------------
# The schema contract
# ---------------------------------------------------------------------------

def test_unique_key_is_the_six_column_key_from_the_database():
    """Verified against pg_indexes. If the schema moves, this must move with it."""
    assert tuple(COMPONENT_UNIQUE_KEY) == (
        "set_id",
        "scoring_version",
        "hit_policy_version",
        "composite_scoring_version",
        "fan_popularity_snapshot_id",
        "config_fingerprint",
    )


def test_set_id_alone_is_not_a_unique_key():
    """The defect in one assertion: set_id is a prefix of the key, not the key."""
    assert "set_id" in COMPONENT_NON_UNIQUE_COLUMNS
    assert tuple(COMPONENT_UNIQUE_KEY) != ("set_id",)
    assert len(COMPONENT_UNIQUE_KEY) > 1


def test_primary_key_is_id():
    assert COMPONENT_PRIMARY_KEY == "id"


def test_source_columns_include_every_identity_and_concurrency_field():
    columns = set(COMPONENT_SOURCE_COLUMNS.split(","))
    for required in (*COMPONENT_UNIQUE_KEY, COMPONENT_PRIMARY_KEY, "built_at", "updated_at",
                     "set_name", "set_canonical_key", "set_desirability_score",
                     "subject_rollups_json", "diagnostics_json", "component_inputs_json"):
        assert required in columns, f"source read is missing {required}"


def test_expected_versions_track_the_defining_modules():
    """Read live, never duplicated - a parallel copy would certify stale rows."""
    from backend.desirability.composite import COMPOSITE_SCORING_VERSION
    from backend.desirability.rarity_buckets import HIT_POLICY_VERSION
    from backend.desirability.set_components import SCORING_VERSION

    assert expected_source_versions() == {
        "scoring_version": SCORING_VERSION,
        "hit_policy_version": HIT_POLICY_VERSION,
        "composite_scoring_version": COMPOSITE_SCORING_VERSION,
    }


def test_the_expected_hit_policy_is_the_v2_coverage_cleanup_one():
    """Pins the production fact the rollout was repaired around."""
    assert EXPECTED_HIT_POLICY_VERSION == V2_CLEANUP


# ---------------------------------------------------------------------------
# Version-exact selection
# ---------------------------------------------------------------------------

def test_the_newest_row_is_not_selected_when_its_version_is_wrong():
    """THE production defect, reproduced.

    In production the v1 rows are the NEWEST (built 2026-07-16) and the
    v2_coverage_cleanup rows are older (2026-06-14). "Take the latest" therefore
    selects v1 for every set while the code fingerprints v2 - so recency must not
    win over an exact version match.
    """
    rows = [
        _row("s1", V1, built_at="2026-07-16T00:08:49Z"),   # newest, WRONG version
        _row("s1", V2_CLEANUP, built_at="2026-06-14T22:59:34Z"),
        _row("s1", V2, built_at="2026-06-14T05:24:42Z"),
    ]
    selection = select_component_source_rows(rows)
    assert selection["selected"]["s1"]["hit_policy_version"] == V2_CLEANUP
    assert selection["selected"]["s1"]["built_at"] == "2026-06-14T22:59:34Z"


def test_a_set_with_no_exact_version_row_is_unavailable_not_downgraded():
    """Chaos Rising's shape: v1 exists, v2_coverage_cleanup does not."""
    rows = [_row("chaos", V1, built_at="2026-07-16T00:08:49Z")]
    selection = select_component_source_rows(rows)

    assert "chaos" not in selection["selected"]
    missing = selection["missing"][0]
    assert missing["set_id"] == "chaos"
    assert missing["reason"] == MISSING_CURRENT_COMPONENT_SOURCE_ROW
    assert missing["expected_versions"]["hit_policy_version"] == V2_CLEANUP
    assert [entry["hit_policy_version"] for entry in missing["available_versions"]] == [V1]


def test_available_older_versions_are_listed_newest_first():
    rows = [
        _row("s1", V1, built_at="2026-07-16T00:00:00Z"),
        _row("s1", V2, built_at="2026-06-14T05:00:00Z"),
    ]
    missing = select_component_source_rows(rows)["missing"][0]
    assert [entry["hit_policy_version"] for entry in missing["available_versions"]] == [V1, V2]


def test_a_mismatched_scoring_version_also_disqualifies_a_row():
    """All THREE versions must match, not just the hit policy."""
    rows = [_row("s1", V2_CLEANUP, scoring_version="something_else_v9")]
    selection = select_component_source_rows(rows)
    assert not selection["selected"]
    assert selection["missing"][0]["reason"] == MISSING_CURRENT_COMPONENT_SOURCE_ROW


def test_a_mismatched_composite_version_also_disqualifies_a_row():
    rows = [_row("s1", V2_CLEANUP, composite_scoring_version="composite_v9")]
    assert not select_component_source_rows(rows)["selected"]


def test_duplicate_exact_version_rows_are_reported_not_silently_resolved():
    """Two rows differing only in config_fingerprint are both valid under the key.

    Picking one would be picking an input set - an operator's decision.
    """
    rows = [
        _row("s1", V2_CLEANUP, row_id="a", config_fingerprint="cfg-a"),
        _row("s1", V2_CLEANUP, row_id="b", config_fingerprint="cfg-b"),
    ]
    selection = select_component_source_rows(rows)
    assert "s1" not in selection["selected"]
    duplicate = selection["duplicates"][0]
    assert duplicate["reason"] == DUPLICATE_CURRENT_COMPONENT_SOURCE_ROW
    assert duplicate["row_count"] == 2
    assert sorted(entry["id"] for entry in duplicate["rows"]) == ["a", "b"]


def test_selection_counts_report_found_missing_and_duplicate():
    rows = [
        _row("ok", V2_CLEANUP),
        _row("missing", V1),
        _row("dupe", V2_CLEANUP, row_id="d1", config_fingerprint="c1"),
        _row("dupe", V2_CLEANUP, row_id="d2", config_fingerprint="c2"),
    ]
    counts = select_component_source_rows(rows)["counts"]
    assert counts["rows_scanned"] == 4
    assert counts["sets_scanned"] == 3
    assert counts["exact_version_rows_found"] == 1
    assert counts["sets_missing_exact_version_row"] == 1
    assert counts["sets_with_duplicate_exact_version_rows"] == 1


def test_version_distribution_marks_only_the_expected_triple():
    rows = [_row("s1", V1), _row("s2", V2), _row("s3", V2_CLEANUP)]
    distribution = select_component_source_rows(rows)["version_distribution"]
    expected_entries = [entry for entry in distribution if entry["is_expected"]]
    assert len(expected_entries) == 1
    assert expected_entries[0]["hit_policy_version"] == V2_CLEANUP


def test_matches_expected_versions_requires_an_exact_triple():
    assert matches_expected_versions(_row("s1", V2_CLEANUP)) is True
    assert matches_expected_versions(_row("s1", V1)) is False


# ---------------------------------------------------------------------------
# Source identity
# ---------------------------------------------------------------------------

def test_source_identity_carries_every_required_field():
    identity = build_source_identity(_row("s1", V2_CLEANUP))
    for field in ("component_row_id", "scoring_version", "hit_policy_version",
                  "composite_scoring_version", "fan_popularity_snapshot_id",
                  "config_fingerprint", "built_at", "updated_at"):
        assert identity.get(field) is not None, f"source identity missing {field}"
    assert identity["unique_key"] == list(COMPONENT_UNIQUE_KEY)


def test_source_identity_matches_only_its_own_row():
    row = _row("s1", V2_CLEANUP)
    identity = build_source_identity(row)
    assert source_identity_matches_row(identity, row) is True

    other = _row("s1", V1, row_id="other")
    assert source_identity_matches_row(identity, other) is False


def test_a_v2_identity_never_matches_a_v1_row():
    """The blocker-2 invariant at its narrowest."""
    v2_identity = build_source_identity(_row("s1", V2_CLEANUP))
    v1_row = _row("s1", V1)
    assert source_identity_matches_row(v2_identity, v1_row) is False


def test_rebuild_command_names_the_set_and_the_expected_hit_policy():
    command = rebuild_command_for("5bdbfae1-3f2e-44e7-b8c9-1035ad45b896", "Chaos Rising")
    assert "5bdbfae1-3f2e-44e7-b8c9-1035ad45b896" in command
    assert V2_CLEANUP in command
    assert "--dry-run" in command
    assert "build_pokemon_set_desirability_component_scores.py" in command
