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
  * publication validation requires `publicRipContractV8` only
    (`_score_contract_problems`);
  * 1D rank movement reads only ids plus `overallRipV8.rank` /
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
    TARGET_KEYS_NOT_PERSISTED_IN_LATEST,
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
        "overallRipV8": {"rank": 3, "absoluteScore": 71.2},
        "financialRipV3": {"rank": 5, "absoluteScore": 64.0},
        "publicRipContractV8": {
            "overallRip": {"rank": 3},
            "financialRip": {"components": {}},
            "collectorAppeal": {
                "components": {
                    "rosterDesirability": {
                        "rank": 5, "tier": "A", "rankedSetCount": 22, "relativeScore": 82.0,
                        "modeledPokemon": [
                            {"name": "Pikachu", "desirabilityScore": 86.6, "speciesRank": 2}
                        ],
                    },
                    "desirableOutcomeFrequency": {
                        "rank": 17, "tier": "F", "rankedSetCount": 22, "relativeScore": 28.0
                    },
                }
            },
        },
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
        collector = target["publicRipContractV8"]["collectorAppeal"]["components"]
        assert collector["rosterDesirability"] == {
            "rank": 5, "tier": "A", "rankedSetCount": 22, "relativeScore": 82.0,
            "modeledPokemon": [
                {"name": "Pikachu", "desirabilityScore": 86.6, "speciesRank": 2}
            ],
        }
        assert collector["desirableOutcomeFrequency"] == {
            "rank": 17, "tier": "F", "rankedSetCount": 22, "relativeScore": 28.0
        }
        # attach_daily_rip_rank_movements requires these plus a stable id.
        assert target["overallRipV8"]["rank"] == 3
        assert target["financialRipV3"]["rank"] == 5
        assert target["set_id"] == "75cd439d-aaa2-41cb-86f3-2fefa5b26e29"
        # Identity/routing fields the set route and sitemap resolve on.
        assert target["canonical_key"]
        assert target["slug"]
        assert target["name"]
        # `financial_rip_v3_payload` was retained by Phase 1 and is removed by
        # Phase 2 - see the Phase 2 block below for the lineage proof. The
        # dedicated assertion lives there; this list covers what still survives.
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
    assert before - after == set(TARGET_KEYS_NOT_PERSISTED_IN_LATEST)
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


# ---------------------------------------------------------------------------
# Phase 2 - the raw Financial RIP V3 calculation-run document.
#
# `financial_rip_v3_payload` is NOT a snake_case alias of `financialRipV3`. It is
# the raw JSONB document from the `calculation_runs` row, and it is the INPUT that
# `_build_financial_rip_v3` consumes to PRODUCE `financialRipV3`:
#
#     calculation_runs.financial_rip_v3_payload   (raw simulation document)
#         -> _build_financial_rip_v3(target)      (score/status/components)
#             -> target["financialRipV3"]
#                 -> _rank_financial_rip_v3       (rank/tier/relativeScore/cohortSize)
#                     -> publicRipContractV8.financialRip
#
# That lineage also explains the 34-vs-22 coverage: 22 targets have a V3 run, and
# the other 12 carry `financialRipV3.status == "unavailable"` with
# `statusReason == "no_financial_rip_v3_payload_on_latest_run"`. The camel object
# is the computed VERDICT and exists for all 34; the snake document is the raw
# INPUT and exists only where a V3 run does.
#
# It is dropped from the persisted `_latest` artifact because nothing reads it there:
#   * the frontend contains ZERO references to `financial_rip_v3_payload`;
#   * `_merge_canonical_rip_contract_into_set_payload` lifts `financialRipV3` into
#     the set page payload but NOT the raw document;
#   * the publisher, publication contract, movement and the snapshot reader never
#     reference it;
#   * the research/audit scripts read `explore_rip_statistics_latest` (a VIEW over
#     the calculation runs), not this table.
#
# The live builder still produces it - `_build_financial_rip_v3` needs it - so only
# the persistence projection changes.
# ---------------------------------------------------------------------------


def test_raw_financial_rip_v3_document_is_not_persisted_in_latest():
    projected = project_latest_rankings_payload(_payload())
    for target in projected["targets"]:
        assert "financial_rip_v3_payload" not in target


def test_the_computed_financial_rip_v3_object_is_retained():
    """The camel object is what Rankings actually renders and sorts on.

    exploreRankingConfig.mjs reads financialRipV3.relativeScore / .rank /
    .cohortSize / .tier straight off the target row, and `cohortSize` has no
    equivalent in publicRipContractV8.financialRip (which spells it
    `rankedSetCount`), so V7 cannot stand in for it.
    """
    projected = project_latest_rankings_payload(_payload())
    for target in projected["targets"]:
        assert target["financialRipV3"] == {"rank": 5, "absoluteScore": 64.0}


def test_unranked_targets_keep_their_unavailable_verdict():
    """The 12 targets with no V3 run must still carry the explicit verdict."""
    unavailable = _target("noRunSet")
    unavailable["financial_rip_v3_payload"] = None
    unavailable["financialRipV3"] = {
        "score": None,
        "status": "unavailable",
        "statusReason": "no_financial_rip_v3_payload_on_latest_run",
    }
    projected = project_latest_rankings_payload({"targets": [unavailable], "meta": {}})
    target = projected["targets"][0]
    assert "financial_rip_v3_payload" not in target
    assert target["financialRipV3"]["status"] == "unavailable"
    assert target["financialRipV3"]["statusReason"] == "no_financial_rip_v3_payload_on_latest_run"


def test_removal_set_is_exactly_the_four_declared_keys():
    original = _payload()
    projected = project_latest_rankings_payload(copy.deepcopy(original))
    removed = set(original["targets"][0]) - set(projected["targets"][0])
    assert removed == {
        "publicRipContractV4",
        "publicRipContractV5",
        "publicRipContractV6",
        "financial_rip_v3_payload",
    }
    assert set(projected["targets"][0]) - set(original["targets"][0]) == set()
