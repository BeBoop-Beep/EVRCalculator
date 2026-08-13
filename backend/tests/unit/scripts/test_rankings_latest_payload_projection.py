"""The persisted `_latest` Rankings payload carries only what its consumers read.

WHY THIS EXISTS
---------------
The measured bottleneck on GET /explore/rip-statistics/targets is not SQL (0.117 ms
planned, ~48 ms with a forced detoast) and not the index (UNIQUE (tcg, scope), used).
It is that ~600 ms of a ~667 ms PostgREST call is spent moving a 2.8 MB JSON document
across the DB boundary. 99.7% of that document is `targets`, and 37.47% of the target
bytes are three superseded public contracts:

    publicRipContractV6   532,879 B   20.33%
    publicRipContractV5   394,150 B   15.04%
    publicRipContractV4    55,081 B    2.10%
                        ---------------------
                          982,110 B   37.47%

Removing them from the PERSISTED `_latest` row is safe because nothing that reads
that row consumes them:

  * the set page still gets them - `_merge_canonical_rip_contract_into_set_payload`
    lifts them from `get_rip_statistics_targets_payload()`, the LIVE builder, not
    from this persisted artifact, so set Insights keeps V4/V5/V6 verbatim;
  * publication validation requires `publicRipContractV7` only
    (`_score_contract_problems`);
  * 1D rank movement reads only ids plus `overallRipV7.rank` /
    `financialRipV3.rank` (`attach_daily_rip_rank_movements`);
  * `canonicalRipV7.mjs` declares "deliberately no third step" - it never falls back
    to V5/V6, they are different models;
  * no `getRipStatisticsTargets` consumer (Rankings, Market, landing, set route,
    sitemap, /Explore/rip-statistics) reads them.

The projection is applied ONLY to the `_latest` row and ONLY after validation, so
the publication contract still runs against the complete canonical payload and the
historical leaderboard rows are untouched.
"""

import copy

import pytest

from backend.scripts.pokemon_explore_rankings_publisher import (
    LEGACY_CONTRACT_KEYS_NOT_PERSISTED_IN_LATEST,
    project_latest_rankings_payload,
)


def _target(name="ascendedHeroes"):
    return {
        "canonical_key": name,
        "set_id": "75cd439d-aaa2-41cb-86f3-2fefa5b26e29",
        "target_id": "t-1",
        "id": "s-1",
        "name": "Ascended Heroes",
        "slug": name,
        "overallRipV7": {"rank": 3, "absoluteScore": 71.2},
        "financialRipV3": {"rank": 5, "absoluteScore": 64.0},
        "publicRipContractV7": {"overallRip": {"rank": 3}, "financialRip": {"components": {}}},
        "publicRipContractV6": {"overallRip": {"rank": 4}},
        "publicRipContractV5": {"overallRip": {"rank": 6}},
        "publicRipContractV4": {"overallRip": {"rank": 9}},
        "overallRipV6": {"rank": 4},
        "overallRipV5": {"rank": 6},
        "rip": {"rank": 9},
        "ripCore": {"rank": 8},
        "financial_rip_v3_payload": {"score": 64.0},
        "openingExperience": {"status": "ok"},
        "universalSetDesirability": {"score": 12.0},
    }


def _payload():
    return {
        "targets": [_target("ascendedHeroes"), _target("shroudedFable")],
        "default_target": {"canonical_key": "ascendedHeroes"},
        "meta": {"ripWeightsConfig": {"overallRip": {"version": "v7"}}},
    }


def test_superseded_public_contracts_are_not_persisted_in_latest():
    projected = project_latest_rankings_payload(_payload())
    for target in projected["targets"]:
        for key in ("publicRipContractV4", "publicRipContractV5", "publicRipContractV6"):
            assert key not in target, f"{key} must not be persisted into the _latest rankings row"


def test_canonical_and_movement_fields_survive_the_projection():
    """Everything publication validation, movement and the UI actually read."""
    projected = project_latest_rankings_payload(_payload())
    for target in projected["targets"]:
        # Publication validation (_score_contract_problems) requires this.
        assert target["publicRipContractV7"] == {"overallRip": {"rank": 3}, "financialRip": {"components": {}}}
        # attach_daily_rip_rank_movements requires these plus a stable id.
        assert target["overallRipV7"]["rank"] == 3
        assert target["financialRipV3"]["rank"] == 5
        assert target["set_id"] == "75cd439d-aaa2-41cb-86f3-2fefa5b26e29"
        # Identity/routing fields the set route and sitemap resolve on.
        assert target["canonical_key"]
        assert target["slug"]
        assert target["name"]
        # Explicitly NOT slimmed in this pass (§7, §8, §22).
        assert target["financial_rip_v3_payload"] == {"score": 64.0}
        assert target["openingExperience"] == {"status": "ok"}
        assert target["universalSetDesirability"] == {"score": 12.0}
        assert target["overallRipV6"] == {"rank": 4}
        assert target["overallRipV5"] == {"rank": 6}
        assert target["rip"] == {"rank": 9}
        assert target["ripCore"] == {"rank": 8}


def test_projection_removes_exactly_the_declared_keys_and_nothing_else():
    original = _payload()
    projected = project_latest_rankings_payload(copy.deepcopy(original))

    before = set(original["targets"][0].keys())
    after = set(projected["targets"][0].keys())
    assert before - after == set(LEGACY_CONTRACT_KEYS_NOT_PERSISTED_IN_LATEST)
    assert after - before == set(), "the projection must never ADD keys"


def test_projection_does_not_mutate_the_caller_payload():
    """The complete payload is still what validation and history see."""
    original = _payload()
    snapshot_before = copy.deepcopy(original)
    project_latest_rankings_payload(original)
    assert original == snapshot_before, "projection must not destructively mutate its input"


def test_meta_and_default_target_are_preserved():
    projected = project_latest_rankings_payload(_payload())
    assert projected["meta"] == {"ripWeightsConfig": {"overallRip": {"version": "v7"}}}
    assert projected["default_target"] == {"canonical_key": "ascendedHeroes"}


@pytest.mark.parametrize("payload", [{}, {"targets": []}, {"targets": None}])
def test_projection_tolerates_degenerate_payloads(payload):
    assert project_latest_rankings_payload(payload) is not None
