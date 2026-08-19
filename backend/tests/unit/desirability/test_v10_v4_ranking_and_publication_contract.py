"""V4/V10 ranking, contract and migration-contract regressions.

Financial RIP V4 and Overall RIP V10 previously existed as ABSOLUTE scores only,
so the canonical publisher had nothing rankable to publish. These tests pin the
ranking path, the publicRipContractV10 attachment, and the two migrations that
make a V10 publication possible without disturbing V9/V3.
"""

from pathlib import Path

from backend.calculations.evr.financial_rip_v4_config import FINANCIAL_RIP_V4_VERSION
from backend.db.services import explore_rip_statistics_service as svc
from backend.desirability.public_rip_contract_v10 import (
    PUBLIC_RIP_CONTRACT_V10_VERSION,
)
from backend.desirability.scoring_config import OVERALL_RIP_V10_VERSION

MIGRATIONS = Path(__file__).resolve().parents[3] / "db" / "migrations"
RPC_V10 = MIGRATIONS / "072_update_public_rip_rpc_to_v10.sql"
SEALED_V4 = MIGRATIONS / "073_add_sealed_product_financial_rip_v4_and_overall_rip_v10.sql"

V9_VERSION = "overall_rip_v9_90_financial_v3_10_collector_appeal_v5"
V3_VERSION = "financial_rip_v3_outcome_profile_25_20_15_25_10_5"


def _executable(sql):
    """Only the statements, with `--` commentary stripped.

    The migration's prose deliberately mentions NOT NULL and the V3 columns to
    explain what it is NOT doing; asserting against raw text would read those
    explanations as if they were DDL.
    """
    body = sql.lower().split("begin;", 1)[1]
    return "\n".join(line.split("--", 1)[0] for line in body.splitlines())


def _target(target_id, f4, v10, *, f3=50.0, v9=50.0):
    return {
        "target_id": target_id,
        "canonical_key": "set-" + str(target_id),
        "financialRipV3": {"score": f3, "status": "ready", "rankable": True},
        "overallRipV9": {"score": v9},
        "financialRipV4": {
            "score": f4,
            "status": "ready",
            "rankable": True,
            "scoreVersion": FINANCIAL_RIP_V4_VERSION,
        },
        "overallRipV10": {"score": v10, "version": OVERALL_RIP_V10_VERSION},
        "openingExperience": {"collectorAppeal": {"score": 60.0}},
    }


def _ranked(targets):
    svc._rank_within_cohort(targets, cohort_size=len(targets))
    return targets


# --------------------------------------------------------------------------- #
# RANKING
# --------------------------------------------------------------------------- #
def test_v4_and_v10_are_registered_as_publicly_ranked_metrics():
    registered = dict(svc.PUBLIC_RANKED_METRICS)
    assert registered.get("_rank_financial_rip_v4") == "financialRipV4"
    assert registered.get("_rank_overall_rip_v10") == "overallRipV10"


def test_v4_and_v10_extractors_read_the_absolute_score():
    row = _target("a", 40.0, 44.0)
    assert svc._rank_financial_rip_v4(row) == 40.0
    assert svc._rank_overall_rip_v10(row) == 44.0
    assert svc._rank_financial_rip_v4({}) is None
    assert svc._rank_overall_rip_v10({}) is None


def test_v4_and_v10_receive_rank_tier_and_cohort_denominator():
    targets = _ranked(
        [_target("a", 40.0, 44.0), _target("b", 30.0, 33.0), _target("c", 20.0, 22.0)]
    )
    for row in targets:
        for key in ("financialRipV4", "overallRipV10"):
            block = row[key]
            assert block["rank"] is not None, key
            assert block["tier"] is not None, key
            assert block["cohortSize"] == 3, key
            assert block["relativeScore"] is not None, key


def test_v4_and_v10_rank_order_follows_the_absolute_score():
    targets = _ranked(
        [_target("a", 20.0, 22.0), _target("b", 40.0, 44.0), _target("c", 30.0, 33.0)]
    )
    by_id = {row["target_id"]: row for row in targets}
    assert by_id["b"]["financialRipV4"]["rank"] == 1
    assert by_id["c"]["financialRipV4"]["rank"] == 2
    assert by_id["a"]["financialRipV4"]["rank"] == 3
    assert by_id["b"]["overallRipV10"]["rank"] == 1
    assert by_id["a"]["overallRipV10"]["rank"] == 3


def test_v4_v10_are_ranked_against_the_identical_cohort_as_v3_v9():
    """A candidate ranked on a different population cannot be compared."""
    targets = _ranked([_target(str(i), 40.0 - i, 44.0 - i) for i in range(5)])
    for row in targets:
        sizes = {
            row[key]["cohortSize"]
            for key in ("financialRipV3", "overallRipV9", "financialRipV4", "overallRipV10")
        }
        assert sizes == {5}, sizes
    assert len({row["cohortFingerprint"] for row in targets}) == 1


def test_tied_v4_scores_rank_deterministically():
    first = _ranked(
        [_target("a", 30.0, 33.0), _target("b", 30.0, 33.0), _target("c", 10.0, 11.0)]
    )
    second = _ranked(
        [_target("b", 30.0, 33.0), _target("a", 30.0, 33.0), _target("c", 10.0, 11.0)]
    )

    def rank_of(rows):
        return {row["target_id"]: row["financialRipV4"]["rank"] for row in rows}

    assert rank_of(first) == rank_of(second)


def test_unrankable_v4_target_does_not_take_a_rank_from_the_cohort():
    targets = [_target("a", 40.0, 44.0), _target("b", 30.0, 33.0)]
    targets[1]["financialRipV4"] = {"score": None, "status": "unavailable", "rankable": False}
    targets[1]["overallRipV10"] = {"score": None}
    _ranked(targets)
    assert targets[0]["financialRipV4"]["rank"] == 1
    assert targets[1]["financialRipV4"].get("rank") is None


# --------------------------------------------------------------------------- #
# CONTRACT
# --------------------------------------------------------------------------- #
def test_public_contract_v10_declares_the_v10_and_v4_identities():
    from backend.desirability.public_rip_contract_v10 import build_public_rip_contract_v10

    contract = build_public_rip_contract_v10(_target("a", 40.0, 44.0))
    assert contract["contractVersion"] == PUBLIC_RIP_CONTRACT_V10_VERSION
    blob = repr(contract)
    assert FINANCIAL_RIP_V4_VERSION in blob
    assert OVERALL_RIP_V10_VERSION in blob


def test_contract_v10_key_is_attached_in_the_same_pass_as_v9():
    source = Path(svc.__file__).read_text(encoding="utf-8")
    assert "target[PUBLIC_RIP_CONTRACT_V10_KEY] = build_public_rip_contract_v10(target)" in source
    v9_at = source.index("target[PUBLIC_RIP_CONTRACT_V9_KEY]")
    v10_at = source.index("target[PUBLIC_RIP_CONTRACT_V10_KEY] = ")
    assert v10_at > v9_at, "V10 contract must be attached alongside V9, not instead of it"


# --------------------------------------------------------------------------- #
# PUBLICATION RPC MIGRATION
# --------------------------------------------------------------------------- #
def test_rpc_migration_pins_the_v10_v4_identities():
    sql = RPC_V10.read_text(encoding="utf-8")
    assert "c_financial_rip_version CONSTANT TEXT := '" + FINANCIAL_RIP_V4_VERSION + "'" in sql
    assert "c_overall_rip_version CONSTANT TEXT := '" + OVERALL_RIP_V10_VERSION + "'" in sql
    assert "c_public_contract_version CONSTANT TEXT := 'public_rip_contract_v10'" in sql
    assert "collector_appeal_v5_contextual_roster_h_only_d_baseline_up4_down2" in sql


def test_rpc_migration_reads_v10_v4_json_paths_and_fails_closed():
    sql = RPC_V10.read_text(encoding="utf-8")
    for path in (
        "{overallRipV10,rank}",
        "{overallRipV10,score}",
        "{financialRipV4,score}",
        "{financialRipV4,rank}",
        "{financialRipV4,status}",
        "{financialRipV4,rankable}",
        "{publicRipContractV10,contractVersion}",
    ):
        assert path in sql, path
    assert "'ready'" in sql
    assert "'true'::JSONB" in sql


def test_rpc_migration_has_no_v9_v3_fallback_in_its_executable_body():
    body = "\n".join(
        line.split("--", 1)[0]
        for line in RPC_V10.read_text(encoding="utf-8").split("BEGIN;", 1)[1].splitlines()
    )
    for token in (
        "overallRipV9",
        "financialRipV3",
        "publicRipContractV9",
        "financial_rip_v3_outcome_profile",
        "overall_rip_v9_90",
    ):
        assert token not in body, "V10 publication must not fall back to " + token


def test_rpc_migration_preserves_security_and_grants():
    sql = RPC_V10.read_text(encoding="utf-8")
    assert "SECURITY DEFINER" in sql and "SET search_path = public" in sql
    assert "CREATE OR REPLACE FUNCTION public.publish_pokemon_public_rip_leaderboard" in sql
    assert "REVOKE" in sql and "service_role" in sql


def test_rpc_migration_does_not_edit_the_v9_migration():
    v9 = (MIGRATIONS / "067_update_public_rip_rpc_to_v9.sql").read_text(encoding="utf-8")
    assert V9_VERSION in v9
    assert "financial_rip_v4" not in v9


# --------------------------------------------------------------------------- #
# SAME-DATE MULTI-VERSION HISTORY
# --------------------------------------------------------------------------- #
def test_snapshot_key_carries_model_identity_so_v9_and_v10_coexist():
    """A V10 snapshot INSERTs as a separate lineage; it must not mutate V9."""
    sql = RPC_V10.read_text(encoding="utf-8")
    for column in (
        "market_date",
        "cohort_version",
        "overall_rip_version",
        "financial_rip_version",
        "ca7_version",
    ):
        assert column in sql, column


def test_v9_and_v10_identities_are_distinct_strings():
    assert OVERALL_RIP_V10_VERSION != V9_VERSION
    assert FINANCIAL_RIP_V4_VERSION != V3_VERSION
    assert PUBLIC_RIP_CONTRACT_V10_VERSION != "public_rip_contract_v9"


# --------------------------------------------------------------------------- #
# SEALED-PRODUCT MIGRATION
# --------------------------------------------------------------------------- #
def test_sealed_migration_is_additive_and_nullable():
    sql = SEALED_V4.read_text(encoding="utf-8").lower()
    for column in (
        "financial_rip_v4_score",
        "financial_rip_v4_status",
        "financial_rip_v4_rankable",
        "financial_rip_v4_version",
        "financial_rip_v4_payload",
        "overall_rip_v10_score",
        "overall_rip_v10_version",
        "overall_rip_v10_rankable",
        "overall_rip_v10_payload",
    ):
        assert "add column if not exists " + column in sql, column
    statements = _executable(sql)
    assert "drop column" not in statements
    assert "rename" not in statements
    assert "not null" not in statements, "new columns must stay nullable"
    assert "update public.simulation_sealed_product_results" not in statements


def test_sealed_migration_does_not_touch_v3_columns_or_the_unique_key():
    statements = _executable(SEALED_V4.read_text(encoding="utf-8"))
    assert "alter column financial_rip_v3" not in statements
    assert "drop constraint" not in statements
    assert "uq_simulation_sealed_product_results_run_product" not in statements
