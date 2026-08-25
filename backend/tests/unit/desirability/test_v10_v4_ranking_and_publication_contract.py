"""V4/V10 ranking, contract and migration-contract regressions.

Financial RIP V4 and Overall RIP V10 previously existed as ABSOLUTE scores only,
so the canonical publisher had nothing rankable to publish. These tests pin the
ranking path, the publicRipContractV10 attachment, and the two migrations that
make a V10 publication possible without disturbing V9/V3.
"""

import hashlib
from pathlib import Path

from backend.calculations.evr.financial_rip_v4_config import (
    FINANCIAL_RIP_V4_COMPONENT_ORDER,
    FINANCIAL_RIP_V4_VERSION,
)
from backend.calculations.evr.financial_rip_v3_config import (
    FINANCIAL_RIP_V3_PUBLIC_COMPONENT_KEYS,
)
from backend.db.services import explore_rip_statistics_service as svc
from backend.desirability.public_rip_contract_v10 import (
    PUBLIC_RIP_CONTRACT_V10_VERSION,
)
from backend.desirability.scoring_config import OVERALL_RIP_V10_VERSION

MIGRATIONS = Path(__file__).resolve().parents[3] / "db" / "migrations"
RPC_V10 = MIGRATIONS / "072_update_public_rip_rpc_to_v10.sql"
RPC_V10_TIMEOUT = (
    MIGRATIONS / "20260823110000_extend_public_rip_leaderboard_publish_timeout.sql"
)
SEALED_V4 = MIGRATIONS / "073_add_sealed_product_financial_rip_v4_and_overall_rip_v10.sql"

V4_ORDER = FINANCIAL_RIP_V4_COMPONENT_ORDER
PUBLIC_KEYS = FINANCIAL_RIP_V3_PUBLIC_COMPONENT_KEYS

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


def test_public_contract_v10_tiers_follow_leader_scores_not_relative_or_rank_buckets():
    from backend.desirability.public_rip_contract_v10 import build_public_rip_contract_v10

    rows = _ranked([_target("a", 100, 100), _target("b", 89, 89), _target("c", 0, 0)])
    contracts = [build_public_rip_contract_v10(row) for row in rows]
    assert [(c["overallRip"]["relativeScore"], c["overallRip"]["tier"]) for c in contracts] == [
        (100.0, "S"), (89.0, "B"), (0.0, "F"),
    ]
    assert [(c["financialRip"]["relativeScore"], c["financialRip"]["tier"]) for c in contracts] == [
        (100.0, "S"), (89.0, "B"), (0.0, "F"),
    ]


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


def test_applied_v10_rpc_migration_remains_unchanged():
    assert hashlib.sha256(RPC_V10.read_bytes()).hexdigest() == (
        "9c3c86399c10af44aab71d4774df6c2730e5ab09200c9864517a62499af38388"
    )


def test_rpc_timeout_migration_is_narrow_and_forward_only():
    assert RPC_V10_TIMEOUT.exists()
    sql = RPC_V10_TIMEOUT.read_text(encoding="utf-8")
    executable = _executable(sql).upper()

    signature = """ALTER FUNCTION PUBLIC.PUBLISH_POKEMON_PUBLIC_RIP_LEADERBOARD(
    JSONB,
    JSONB,
    JSONB
)"""
    assert signature in executable
    assert "SET STATEMENT_TIMEOUT = '60S';" in executable
    assert executable.count("ALTER FUNCTION") == 1
    assert "CREATE OR REPLACE FUNCTION" not in executable
    assert "ALTER ROLE" not in executable
    assert "ALTER DATABASE" not in executable
    assert "AUTHENTICATOR" not in executable
    assert "SERVICE_ROLE" not in executable
    assert "SCORE_VERSION" not in executable
    assert "STATEMENT_TIMEOUT = '0'" not in executable
    assert "STATEMENT_TIMEOUT = 0" not in executable


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


# --------------------------------------------------------------------------- #
# FINANCIAL RIP V4 COMPONENT STANDINGS
# --------------------------------------------------------------------------- #
# Regression cover for the 2026-08-22 publication failure: every V4 component
# carried an absolute score but no standing, so the V10 public projection was
# missing 22 sets x 6 components x 4 fields = 528 canonical values and Explore
# Rankings refused to publish.


def _component_target(target_id, component_scores, *, v3_component_scores=None):
    """A target whose V4 (and V3) components carry their own absolute scores."""
    row = _target(target_id, 40.0, 44.0)
    row["financialRipV4"]["components"] = {
        key: {"score": value, "available": True, "raw": {}}
        for key, value in component_scores.items()
    }
    v3_scores = v3_component_scores or component_scores
    row["financialRipV3"]["components"] = {
        key: {"score": value, "available": True, "raw": {}}
        for key, value in v3_scores.items()
    }
    return row


def _component_cohort(scores_by_target, *, v3_by_target=None):
    return _ranked(
        [
            _component_target(
                tid,
                scores,
                v3_component_scores=(v3_by_target or {}).get(tid),
            )
            for tid, scores in scores_by_target.items()
        ]
    )


def _flat(value, order):
    return {key: value for key in order}


def test_every_v4_component_is_registered_as_a_ranked_metric():
    registered = dict(svc.PUBLIC_RANKED_METRICS)
    for component in V4_ORDER:
        assert registered.get(f"_rank_v4_{component}") == f"financialRipV4.{component}", component


def test_v4_component_registration_follows_the_v4_order_constant():
    """V4 must not borrow V3's component order.

    The two constants are equal today (V4 aliases V3), so an implementation that
    looped V3 would pass a naive count check. This asserts the registration is
    derived from the V4 constant by name.
    """
    registered = dict(svc.PUBLIC_RANKED_METRICS)
    v4_keys = {key for key in registered.values() if key.startswith("financialRipV4.")}
    assert v4_keys == {f"financialRipV4.{c}" for c in V4_ORDER}


def test_v4_component_extractors_read_the_v4_component_score():
    row = _component_target("a", _flat(33.0, V4_ORDER), v3_component_scores=_flat(99.0, V4_ORDER))
    for component in V4_ORDER:
        extractor = getattr(svc, f"_rank_v4_{component}")
        assert extractor(row) == 33.0, component
        # and it must not fall through to the V3 namespace
        assert extractor({}) is None, component


def test_v4_components_receive_rank_tier_and_cohort_denominator():
    targets = _component_cohort(
        {
            "a": _flat(80.0, V4_ORDER),
            "b": _flat(50.0, V4_ORDER),
            "c": _flat(20.0, V4_ORDER),
        }
    )
    for row in targets:
        components = row["financialRipV4"]["components"]
        for component in V4_ORDER:
            block = components[component]
            assert block["rank"] is not None, component
            assert block["tier"] is not None, component
            assert block["cohortSize"] == 3, component


def test_v4_components_receive_independent_relative_scores():
    targets = _component_cohort(
        {
            "a": _flat(80.0, V4_ORDER),
            "b": _flat(50.0, V4_ORDER),
            "c": _flat(20.0, V4_ORDER),
        }
    )
    by_id = {row["target_id"]: row for row in targets}
    for component in V4_ORDER:
        assert by_id["a"]["financialRipV4"]["components"][component]["relativeScore"] == 100.0
        assert by_id["c"]["financialRipV4"]["components"][component]["relativeScore"] == 0.0


def test_each_v4_component_is_ranked_from_its_own_score_not_the_parent():
    """Component ranks must differ when component scores differ."""
    high_upside = dict(_flat(10.0, V4_ORDER))
    high_upside["realistic_upside"] = 90.0
    low_upside = dict(_flat(90.0, V4_ORDER))
    low_upside["realistic_upside"] = 10.0
    targets = _component_cohort({"a": high_upside, "b": low_upside})
    by_id = {row["target_id"]: row for row in targets}
    a = by_id["a"]["financialRipV4"]["components"]
    b = by_id["b"]["financialRipV4"]["components"]
    assert a["realistic_upside"]["rank"] == 1
    assert b["realistic_upside"]["rank"] == 2
    assert a["true_win_frequency"]["rank"] == 2
    assert b["true_win_frequency"]["rank"] == 1


def test_realistic_upside_v4_standing_is_not_copied_from_v3():
    """Realistic Upside changed in V4; its standing must come from V4 alone.

    V3 and V4 are given OPPOSITE orderings for this component, so a copy would
    invert the V4 ranks.
    """
    targets = _ranked(
        [
            _component_target(
                "a",
                {**_flat(50.0, V4_ORDER), "realistic_upside": 90.0},
                v3_component_scores={**_flat(50.0, V4_ORDER), "realistic_upside": 10.0},
            ),
            _component_target(
                "b",
                {**_flat(50.0, V4_ORDER), "realistic_upside": 10.0},
                v3_component_scores={**_flat(50.0, V4_ORDER), "realistic_upside": 90.0},
            ),
        ]
    )
    by_id = {row["target_id"]: row for row in targets}
    v4_a = by_id["a"]["financialRipV4"]["components"]["realistic_upside"]
    v4_b = by_id["b"]["financialRipV4"]["components"]["realistic_upside"]
    v3_a = by_id["a"]["financialRipV3"]["components"]["realistic_upside"]
    v3_b = by_id["b"]["financialRipV3"]["components"]["realistic_upside"]

    assert v4_a["rank"] == 1 and v4_b["rank"] == 2
    assert v3_a["rank"] == 2 and v3_b["rank"] == 1
    assert v4_a["relativeScore"] == 100.0 and v3_a["relativeScore"] == 0.0


def test_v3_component_standings_are_unchanged_by_v4_support():
    targets = _component_cohort(
        {"a": _flat(80.0, V4_ORDER), "b": _flat(20.0, V4_ORDER)}
    )
    by_id = {row["target_id"]: row for row in targets}
    for component in V4_ORDER:
        v3 = by_id["a"]["financialRipV3"]["components"][component]
        assert v3["rank"] == 1, component
        assert v3["cohortSize"] == 2, component
        assert v3["relativeScore"] == 100.0, component


def test_v4_and_v3_component_namespaces_do_not_conflate():
    """Writing a V4 standing must never land on the V3 component object."""
    targets = _ranked(
        [
            _component_target("a", _flat(80.0, V4_ORDER), v3_component_scores=_flat(20.0, V4_ORDER)),
            _component_target("b", _flat(20.0, V4_ORDER), v3_component_scores=_flat(80.0, V4_ORDER)),
        ]
    )
    by_id = {row["target_id"]: row for row in targets}
    for component in V4_ORDER:
        assert by_id["a"]["financialRipV4"]["components"][component]["rank"] == 1
        assert by_id["a"]["financialRipV3"]["components"][component]["rank"] == 2


def test_v10_contract_carries_complete_financial_component_standings():
    """The exact shape the publisher validates, end to end.

    This is the assertion that would have caught the 2026-08-22 failure: the
    contract projection is built from a fully ranked cohort and every Financial
    RIP component must arrive with all six canonical fields populated.
    """
    from backend.desirability.public_rip_contract_v10 import (
        build_public_rip_contract_v10,
    )

    targets = _component_cohort(
        {
            "a": _flat(80.0, V4_ORDER),
            "b": _flat(50.0, V4_ORDER),
            "c": _flat(20.0, V4_ORDER),
        }
    )
    for row in targets:
        contract = build_public_rip_contract_v10(row)
        components = contract["financialRip"]["components"]
        # The public contract renames components through the canonical key map;
        # assert against that map rather than the internal snake_case names.
        assert set(components) >= {PUBLIC_KEYS[c] for c in V4_ORDER}
        for component in V4_ORDER:
            block = components[PUBLIC_KEYS[component]]
            for field in (
                "score",
                "absoluteScore",
                "relativeScore",
                "rank",
                "tier",
                "rankedSetCount",
            ):
                assert block.get(field) is not None, f"{component}.{field}"
            assert block["rankedSetCount"] == 3, component


def test_publisher_reports_no_missing_v10_component_standings_for_a_ranked_target():
    """`_score_contract_problems` must be silent on a correctly ranked target."""
    from backend.desirability.public_rip_contract_v10 import (
        PUBLIC_RIP_CONTRACT_V10_KEY,
        build_public_rip_contract_v10,
    )
    from backend.scripts.pokemon_explore_rankings_publisher import (
        _score_contract_problems,
    )

    targets = _component_cohort(
        {"a": _flat(80.0, V4_ORDER), "b": _flat(50.0, V4_ORDER), "c": _flat(20.0, V4_ORDER)}
    )
    row = targets[0]
    row["set_id"] = "set-a"
    row[PUBLIC_RIP_CONTRACT_V10_KEY] = build_public_rip_contract_v10(row)

    problems = _score_contract_problems(row)
    component_problems = [
        problem
        for problem in problems
        if "financialRip.components" in str(problem)
    ]
    assert component_problems == [], component_problems
