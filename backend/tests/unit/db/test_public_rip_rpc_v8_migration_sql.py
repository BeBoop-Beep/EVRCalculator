"""Structural guarantees for migration 062, the CANONICAL V8 publish RPC.

WHY A STATIC TEST
-----------------
The publish RPC is the last gate before `pokemon_explore_rankings_snapshot_latest`
is promoted, and it runs inside a transaction on a remote database. A defect in
its ranked-target predicate does not surface as a failing test - it surfaces as a
leaderboard published under the wrong model, which is exactly what happened when
migration 054 kept counting the LEGACY `rip.rank` (Overall RIP v4) after the
publisher had moved to `overallRipV7`. Nothing in the application could see the
divergence, because both halves were internally consistent.

These tests read the SQL as text. They cannot execute it, so they deliberately
assert on the things a reviewer would otherwise have to re-check by eye every
time the file is touched: which predicate defines the cohort, that the version
strings match the ONE canonical selection in `scoring_config`, and that the
atomicity/permission properties migration 049/053/054 established are still
present.
"""

from pathlib import Path

import pytest

from backend.desirability.collector_appeal import COLLECTOR_APPEAL_V4_VERSION
from backend.desirability.scoring_config import (
    CANONICAL_FINANCIAL_RIP_VERSION,
    CANONICAL_OVERALL_RIP_VERSION,
    canonical_public_rip_contract_version,
)

_MIGRATIONS = Path(__file__).resolve().parents[3] / "db" / "migrations"
_MIGRATION_062 = _MIGRATIONS / "062_update_public_rip_rpc_to_v8.sql"

# Every migration that (re)defines the publish RPC, oldest first. The LAST one is
# authoritative: it is the definition production ends up running.
_PUBLISH_RPC_MIGRATIONS = (
    "049_add_pokemon_public_rip_leaderboard_history.sql",
    "053_harden_pokemon_public_rip_leaderboard_publication.sql",
    "054_fix_pokemon_public_rip_ranked_target_contract.sql",
    "061_update_public_rip_rpc_to_v7.sql",
    "062_update_public_rip_rpc_to_v8.sql",
)


def _executable(text: str) -> str:
    """The SQL with `--` comment lines removed.

    The predicate checks below must read the EXECUTABLE statements. Migration
    061's header explains the legacy `{rip,rank}` predicate it replaces, and a
    naive substring search over the whole file would flag that prose - which
    would make the test unfixable except by deleting the explanation.
    """
    return "\n".join(
        line for line in text.splitlines() if not line.lstrip().startswith("--")
    )


@pytest.fixture(scope="module")
def sql() -> str:
    return _MIGRATION_062.read_text(encoding="utf-8")


def test_migration_062_exists_and_is_forward_only(sql):
    assert _MIGRATION_062.exists()
    assert sql.strip().startswith("--")
    assert "CREATE OR REPLACE FUNCTION public.publish_pokemon_public_rip_leaderboard" in sql
    assert "BEGIN;" in sql and sql.strip().endswith("COMMIT;")
    # Forward-only: it must not rewrite history.
    assert "DROP FUNCTION" not in sql


def test_canonical_ranked_targets_are_overall_rip_v7(sql):
    assert "target #> '{overallRipV8,rank}' IS NOT NULL" in sql
    assert "target #> '{overallRipV8,rank}' <> 'null'::JSONB" in sql


def test_legacy_v4_rank_predicate_is_gone(sql):
    """The whole point of 061. `{rip,rank}` is the Overall RIP v4 object."""
    assert "{rip,rank}" not in _executable(sql)


def test_no_later_migration_reintroduces_the_legacy_rank_predicate():
    """A future RPC revision may not go back to `{rip,rank}`.

    Scans every migration that redefines the publish function and asserts the
    AUTHORITATIVE one - the last by filename order - does not use the legacy v4
    predicate. Ordered by filename rather than by a hardcoded index so adding
    062 automatically brings it under the check.
    """
    redefiners = sorted(
        path
        for path in _MIGRATIONS.glob("*.sql")
        if "CREATE OR REPLACE FUNCTION public.publish_pokemon_public_rip_leaderboard"
        in path.read_text(encoding="utf-8")
    )
    assert redefiners, "no migration defines the publish RPC"
    latest = redefiners[-1]
    text = _executable(latest.read_text(encoding="utf-8"))
    assert "{rip,rank}" not in text, (
        f"{latest.name} reintroduces the legacy Overall RIP v4 ranked-target "
        "predicate `target #> '{rip,rank}'`. The canonical predicate is "
        "`target #> '{overallRipV8,rank}'`."
    )
    assert "{overallRipV8,rank}" in text


def test_every_publish_rpc_migration_is_accounted_for():
    """The list above must not fall behind the directory."""
    observed = {
        path.name
        for path in _MIGRATIONS.glob("*.sql")
        if "CREATE OR REPLACE FUNCTION public.publish_pokemon_public_rip_leaderboard"
        in path.read_text(encoding="utf-8")
    }
    assert observed == set(_PUBLISH_RPC_MIGRATIONS)


@pytest.mark.parametrize(
    "fragment",
    [
        "target #> '{overallRipV8,score}' IS NOT NULL",
        "target #> '{financialRipV3,score}' IS NOT NULL",
        "target #> '{financialRipV3,rank}' IS NOT NULL",
        "target #>> '{financialRipV3,status}' = 'ready'",
        "target #> '{financialRipV3,rankable}' = 'true'::JSONB",
        "target #>> '{publicRipContractV8,contractVersion}' = c_public_contract_version",
    ],
)
def test_ranked_targets_require_a_complete_canonical_object(sql, fragment):
    """A V7 rank without a ready/rankable V3 score is a half-published row."""
    assert fragment in sql


def test_cohort_size_and_id_uniqueness_are_enforced(sql):
    assert "v_expected <= 0" in sql
    assert "v_rows <> v_expected" in sql
    assert "v_ranked_targets <> v_expected" in sql
    assert "v_total_targets < v_expected" in sql
    assert "v_distinct_ranked_target_ids <> v_expected" in sql
    assert "v_distinct_history_ids <> v_expected" in sql


def test_ranks_must_be_contiguous_and_unique(sql):
    """Cardinality is not a ranking: {1,2,2,4} has the right count."""
    assert "v_distinct_ranks <> v_expected" in sql
    assert "v_min_rank IS DISTINCT FROM 1" in sql
    assert "v_max_rank IS DISTINCT FROM v_expected" in sql


def test_set_parity_is_checked_in_both_directions(sql):
    assert sql.count("EXCEPT") >= 2
    assert "canonical V8 ranked target IDs are missing from the history rows" in sql
    assert "are not canonical V8 ranked targets" in sql


def test_snapshot_version_fields_must_be_the_canonical_identity(sql):
    """Restated literals in SQL, pinned to the ONE Python selection."""
    assert f"c_financial_rip_version CONSTANT TEXT := '{CANONICAL_FINANCIAL_RIP_VERSION}'" in sql
    assert f"c_collector_appeal_version CONSTANT TEXT := '{COLLECTOR_APPEAL_V4_VERSION}'" in sql
    assert f"c_overall_rip_version CONSTANT TEXT := '{CANONICAL_OVERALL_RIP_VERSION}'" in sql
    assert (
        f"c_public_contract_version CONSTANT TEXT := '{canonical_public_rip_contract_version()}'"
        in sql
    )
    for column in ("financial_rip_version", "overall_rip_version", "ca7_version"):
        assert f"p_snapshot->>'{column}' IS DISTINCT FROM" in sql
    assert "v_diag->>'public_rip_contract_version' IS DISTINCT FROM" in sql


def test_atomicity_idempotency_and_grants_are_preserved(sql):
    assert (
        "ON CONFLICT (market_date, cohort_version, overall_rip_version, "
        "financial_rip_version, ca7_version)" in sql
    )
    # History rows are written BEFORE `latest` is promoted.
    assert sql.index("INSERT INTO pokemon_public_rip_leaderboard_rows") < sql.index(
        "INSERT INTO pokemon_explore_rankings_snapshot_latest"
    )
    assert "SECURITY DEFINER SET search_path = public" in sql
    assert "REVOKE ALL ON FUNCTION public.publish_pokemon_public_rip_leaderboard" in sql
    assert "TO service_role" in sql


def test_no_temp_table_is_used_under_a_pinned_search_path(sql):
    """`search_path = public` is pinned, and pg_temp is not on it."""
    assert "CREATE TEMP TABLE" not in sql
