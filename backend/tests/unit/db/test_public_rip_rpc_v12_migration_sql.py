"""Migration-contract regressions for 078_update_public_rip_rpc_to_v12.sql.

Overall RIP advances from V10 (90% Financial V4 / 10% Collector Appeal V5) to
V12 (86% Financial V4 / 4% Chase Accessibility V1 / 10% Collector Appeal V5).
Financial RIP stays V4, Collector Appeal stays V5, and the public contract
advances from V10 to V11. These tests pin the publish-RPC migration's
identity constants, its canonical JSON paths, its fail-closed behaviour
against the old V10 predicate, and every structural invariant carried over
unchanged from 072 (contiguous ranks, bidirectional set parity, version-aware
conflict key, history-before-latest ordering, SECURITY DEFINER + grants).
"""

import hashlib
from pathlib import Path

from backend.desirability.public_rip_contract_v11 import (
    PUBLIC_RIP_CONTRACT_V11_VERSION,
)
from backend.desirability.scoring_config import (
    OVERALL_RIP_V10_VERSION,
    OVERALL_RIP_V12_VERSION,
)

MIGRATIONS = Path(__file__).resolve().parents[3] / "db" / "migrations"
RPC_V10 = MIGRATIONS / "072_update_public_rip_rpc_to_v10.sql"
RPC_V12 = MIGRATIONS / "078_update_public_rip_rpc_to_v12.sql"

FINANCIAL_RIP_V4_VERSION = "financial_rip_v4_outcome_profile_p95_only_25_20_15_25_10_5"
COLLECTOR_APPEAL_V5_VERSION = (
    "collector_appeal_v5_contextual_roster_h_only_d_baseline_up4_down2"
)


def _executable(sql):
    """Only the statements, with `--` commentary stripped.

    The migration's prose deliberately mentions V10 to explain what it is
    superseding; asserting against raw text would read those explanations as
    if they were DDL.
    """
    body = sql.split("BEGIN;", 1)[1]
    return "\n".join(line.split("--", 1)[0] for line in body.splitlines())


# --------------------------------------------------------------------------- #
# FILE PRESENCE / NUMBERING
# --------------------------------------------------------------------------- #
def test_v12_migration_file_exists_at_the_expected_number():
    assert RPC_V12.exists()
    assert RPC_V12.name == "078_update_public_rip_rpc_to_v12.sql"


def test_v12_migration_does_not_edit_the_v10_migration():
    v10 = RPC_V10.read_text(encoding="utf-8")
    assert OVERALL_RIP_V10_VERSION in v10
    assert "chase_accessibility" not in v10


# --------------------------------------------------------------------------- #
# CANONICAL IDENTITY CONSTANTS
# --------------------------------------------------------------------------- #
def test_rpc_migration_pins_the_v12_v11_identities():
    sql = RPC_V12.read_text(encoding="utf-8")
    assert "c_financial_rip_version CONSTANT TEXT := '" + FINANCIAL_RIP_V4_VERSION + "'" in sql
    assert "c_overall_rip_version CONSTANT TEXT := '" + OVERALL_RIP_V12_VERSION + "'" in sql
    assert "c_public_contract_version CONSTANT TEXT := 'public_rip_contract_v11'" in sql
    assert "c_collector_appeal_version CONSTANT TEXT := '" + COLLECTOR_APPEAL_V5_VERSION + "'" in sql


def test_overall_v12_constant_matches_the_python_scoring_config():
    assert OVERALL_RIP_V12_VERSION == (
        "overall_rip_v12_86_financial_v4_04_chase_accessibility_v1_10_collector_appeal_v5"
    )


def test_public_contract_v11_constant_matches_the_python_module():
    assert PUBLIC_RIP_CONTRACT_V11_VERSION == "public_rip_contract_v11"


def test_financial_stays_v4_and_collector_appeal_stays_v5():
    sql = RPC_V12.read_text(encoding="utf-8")
    assert FINANCIAL_RIP_V4_VERSION in sql
    assert COLLECTOR_APPEAL_V5_VERSION in sql


# --------------------------------------------------------------------------- #
# CANONICAL JSON PATHS
# --------------------------------------------------------------------------- #
def test_rpc_migration_reads_v12_v11_json_paths_and_fails_closed():
    sql = RPC_V12.read_text(encoding="utf-8")
    for path in (
        "{overallRipV12,rank}",
        "{overallRipV12,score}",
        "{financialRipV4,score}",
        "{financialRipV4,rank}",
        "{financialRipV4,status}",
        "{financialRipV4,rankable}",
        "{publicRipContractV11,contractVersion}",
    ):
        assert path in sql, path
    assert "'ready'" in sql
    assert "'true'::JSONB" in sql


def test_rpc_migration_has_no_v10_fallback_in_its_executable_body():
    executable = _executable(RPC_V12.read_text(encoding="utf-8"))
    for token in (
        "overallRipV10",
        "publicRipContractV10",
        "overall_rip_v10_90",
        "public_rip_contract_v10",
    ):
        assert token not in executable, "V12 publication must not fall back to " + token


def test_v10_may_still_appear_in_migration_prose_comments():
    """The comment header legitimately documents the V10-to-V12 transition."""
    sql = RPC_V12.read_text(encoding="utf-8")
    assert "072_update_public_rip_rpc_to_v10" in sql or "V10" in sql


# --------------------------------------------------------------------------- #
# STRUCTURAL INVARIANTS CARRIED OVER FROM 072
# --------------------------------------------------------------------------- #
def test_rpc_migration_preserves_security_and_grants():
    sql = RPC_V12.read_text(encoding="utf-8")
    assert "SECURITY DEFINER" in sql and "SET search_path = public" in sql
    assert "CREATE OR REPLACE FUNCTION public.publish_pokemon_public_rip_leaderboard" in sql
    assert "REVOKE" in sql and "service_role" in sql
    assert "GRANT EXECUTE ON FUNCTION public.publish_pokemon_public_rip_leaderboard" in sql
    assert "TO service_role" in sql


def test_rpc_migration_keeps_exact_rank_contiguity_check():
    sql = RPC_V12.read_text(encoding="utf-8")
    assert "v_min_rank IS DISTINCT FROM 1" in sql
    assert "v_max_rank IS DISTINCT FROM v_expected" in sql
    assert "are not contiguous 1..%" in sql


def test_rpc_migration_keeps_duplicate_rank_check():
    sql = RPC_V12.read_text(encoding="utf-8")
    assert "v_distinct_ranks <> v_expected" in sql
    assert "ranks contain duplicates" in sql


def test_rpc_migration_keeps_bidirectional_set_parity_checks():
    sql = RPC_V12.read_text(encoding="utf-8")
    assert sql.count("\n        EXCEPT\n") == 2
    assert "missing from the history rows" in sql
    assert "that are not canonical V12 ranked targets" in sql


def test_rpc_migration_keeps_version_aware_conflict_key():
    sql = RPC_V12.read_text(encoding="utf-8")
    assert (
        "ON CONFLICT (market_date, cohort_version, overall_rip_version, "
        "financial_rip_version, ca7_version)" in sql
    )


def test_history_insert_precedes_latest_promotion():
    sql = RPC_V12.read_text(encoding="utf-8")
    history_at = sql.index("INSERT INTO pokemon_public_rip_leaderboard_rows")
    latest_at = sql.index("INSERT INTO pokemon_explore_rankings_snapshot_latest")
    assert history_at < latest_at


def test_rpc_migration_keeps_publication_metadata_checks():
    sql = RPC_V12.read_text(encoding="utf-8")
    assert "publicationId" in sql
    assert "marketDate" in sql
    assert "builtAt" in sql
    assert "malformed canonical RIP latest publication metadata" in sql


def test_rpc_migration_keeps_canonical_version_assertions():
    sql = RPC_V12.read_text(encoding="utf-8")
    assert "financial RIP version % is not the canonical %" in sql
    assert "overall RIP version % is not the canonical %" in sql
    assert "collector appeal version % is not the canonical %" in sql
    assert "public RIP contract version % is not the canonical %" in sql


def test_v10_and_v12_identities_are_distinct_strings():
    assert OVERALL_RIP_V12_VERSION != OVERALL_RIP_V10_VERSION
    assert PUBLIC_RIP_CONTRACT_V11_VERSION != "public_rip_contract_v10"


def test_applied_v10_rpc_migration_is_unchanged_by_this_effort():
    """072 is immutable; this new migration must not have edited it."""
    assert hashlib.sha256(RPC_V10.read_bytes()).hexdigest() == (
        "9c3c86399c10af44aab71d4774df6c2730e5ab09200c9864517a62499af38388"
    )
