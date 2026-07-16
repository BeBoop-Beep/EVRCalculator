"""Product-support classification, the rankability guard, and the RIP
missing-pillar policy.

These tests encode the finding that motivated the work: the 36 unscoreable sets
in production are not broken booster sets, they are products the model was never
built for. The distinction is load-bearing in two directions - it stops someone
"fixing" rarity data that is already correct, and it stops a fixed-contents
product ever being ranked as the least appealing thing in the catalogue.
"""

from __future__ import annotations

import pytest

from backend.desirability.product_support import (
    UNSUPPORTED_FIXED_PRODUCT,
    UNSUPPORTED_MCDONALDS_COLLECTION,
    UNSUPPORTED_POP_SERIES,
    UNSUPPORTED_PROMO_PRODUCT,
    UNSUPPORTED_TRAINER_KIT,
    VALID_BOOSTER_SET,
    classify_product_support,
)
from backend.desirability.rankability import (
    UnrankableRowError,
    availability,
    filter_rankable,
    is_rankable,
    rank_rankable_rows,
    rankable_score,
)
from backend.desirability.weighted_rip import compute_financial_rip, compute_weighted_rip
from backend.scripts.build_pokemon_set_desirability_component_scores import build_metric_status


# ---------------------------------------------------------------------------
# Product classification - real examples from the affected production cohort
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "canonical_key,set_name,expected_type",
    [
        # All 8 promo sets in the affected cohort.
        ("swshBlackStarPromos", "SWSH Black Star Promos", UNSUPPORTED_PROMO_PRODUCT),
        ("xyBlackStarPromos", "XY Black Star Promos", UNSUPPORTED_PROMO_PRODUCT),
        ("smBlackStarPromos", "SM Black Star Promos", UNSUPPORTED_PROMO_PRODUCT),
        ("wizardsBlackStarPromos", "Wizards Black Star Promos", UNSUPPORTED_PROMO_PRODUCT),
        ("nintendoBlackStarPromos", "Nintendo Black Star Promos", UNSUPPORTED_PROMO_PRODUCT),
        ("bwBlackStarPromos", "BW Black Star Promos", UNSUPPORTED_PROMO_PRODUCT),
        ("dpBlackStarPromos", "DP Black Star Promos", UNSUPPORTED_PROMO_PRODUCT),
        ("hgssBlackStarPromos", "HGSS Black Star Promos", UNSUPPORTED_PROMO_PRODUCT),
        # All 4 Trainer Kits.
        ("exTrainerKitLatias", "EX Trainer Kit Latias", UNSUPPORTED_TRAINER_KIT),
        ("exTrainerKitLatios", "EX Trainer Kit Latios", UNSUPPORTED_TRAINER_KIT),
        ("exTrainerKit2Plusle", "EX Trainer Kit 2 Plusle", UNSUPPORTED_TRAINER_KIT),
        ("exTrainerKit2Minun", "EX Trainer Kit 2 Minun", UNSUPPORTED_TRAINER_KIT),
        # McDonald's.
        ("mcdonaldSCollection2011", "McDonald's Collection 2011", UNSUPPORTED_MCDONALDS_COLLECTION),
        ("mcdonaldSCollection2022", "McDonald's Collection 2022", UNSUPPORTED_MCDONALDS_COLLECTION),
        # POP Series.
        ("popSeries1", "POP Series 1", UNSUPPORTED_POP_SERIES),
        ("popSeries9", "POP Series 9", UNSUPPORTED_POP_SERIES),
        # Fixed products with no shared pattern.
        ("bestOfGame", "Best of Game", UNSUPPORTED_FIXED_PRODUCT),
        ("kalosStarterSet", "Kalos Starter Set", UNSUPPORTED_FIXED_PRODUCT),
        ("pokMonFutsalCollection", "Pokémon Futsal Collection", UNSUPPORTED_FIXED_PRODUCT),
        ("pokMonRumble", "Pokémon Rumble", UNSUPPORTED_FIXED_PRODUCT),
        ("southernIslands", "Southern Islands", UNSUPPORTED_FIXED_PRODUCT),
    ],
)
def test_affected_cohort_classifies_as_unsupported_product(canonical_key, set_name, expected_type):
    result = classify_product_support(set_canonical_key=canonical_key, set_name=set_name)
    assert result["product_support_type"] == expected_type
    assert result["supported"] is False
    assert result["product_support_reason"]


@pytest.mark.parametrize(
    "canonical_key,set_name",
    [
        ("ascendedHeroes", "Ascended Heroes"),
        ("baseSet", "Base Set"),
        ("evolvingSkies", "Evolving Skies"),
        ("surgingSparks", "Surging Sparks"),
        ("teamRocketReturns", "Team Rocket Returns"),
        # Adjacent names that must NOT trip the unsupported patterns.
        ("championsPath", "Champion's Path"),
        ("hiddenFates", "Hidden Fates"),
        ("popularVote", "Popular Vote"),
    ],
)
def test_real_booster_sets_stay_supported(canonical_key, set_name):
    result = classify_product_support(set_canonical_key=canonical_key, set_name=set_name)
    assert result["product_support_type"] == VALID_BOOSTER_SET
    assert result["supported"] is True


def test_popular_vote_is_not_mistaken_for_pop_series():
    """``popSeries`` is anchored to the start of the key; ``popularVote`` must not match.

    Guards the one plausible false positive in the pattern set: an unanchored
    'pop' rule would silently exclude a real booster set from the model.
    """
    assert classify_product_support(set_canonical_key="popularVote", set_name="Popular Vote")["supported"] is True


def test_unknown_new_set_defaults_to_supported():
    """An unrecognised set must be treated as a booster set, not excluded.

    Defaulting to unsupported would let a classifier that has simply never heard
    of a set silently remove it from every ranking.
    """
    result = classify_product_support(set_canonical_key="someFutureSet2027", set_name="Some Future Set")
    assert result["supported"] is True
    assert result["matched_on"] == "default_supported"


def test_classifier_never_consults_scores_or_counts():
    """Product support is metadata-only.

    Inferring "unsupported" from a zero score would make the classifier agree
    with the scorer by construction, and would reclassify a genuinely broken
    booster set as 'out of model' the moment its data regressed.
    """
    import inspect

    signature = inspect.signature(classify_product_support)
    assert set(signature.parameters) == {"set_canonical_key", "set_name", "set_series"}


# ---------------------------------------------------------------------------
# build_metric_status - the misdiagnosis this replaces
# ---------------------------------------------------------------------------

def _audit(*, canonical=27, unknown_rarity=0, hit_like=0, linked_hits=0):
    return {
        "canonical_card_count": canonical,
        "unknown_rarity_count": unknown_rarity,
        "hit_like_card_count": hit_like,
        "pokemon_linked_hit_count": linked_hits,
    }


def test_trainer_kit_is_unsupported_product_not_missing_rarity():
    """The exact production misdiagnosis: EX Trainer Kit Latias has full rarity
    data and resolved subject links, and was still reported as missing rarity."""
    status = build_metric_status(
        _audit(canonical=22, unknown_rarity=0, hit_like=0),
        {"canonical_key": "exTrainerKitLatias", "name": "EX Trainer Kit Latias"},
    )
    assert status["metric_status"] == "unsupported_product_type"
    assert status["product_support_type"] == UNSUPPORTED_TRAINER_KIT
    assert status["rankable"] is False
    assert "rarity" not in (status["availability_reason"] or "").lower()


def test_promo_with_full_rarity_coverage_is_unsupported_not_data_defect():
    """SWSH Black Star Promos: 304 cards, 151 subjects, rarity fully mapped."""
    status = build_metric_status(
        _audit(canonical=304, unknown_rarity=0, hit_like=0),
        {"canonical_key": "swshBlackStarPromos", "name": "SWSH Black Star Promos"},
    )
    assert status["metric_status"] == "unsupported_product_type"
    assert status["product_support_type"] == UNSUPPORTED_PROMO_PRODUCT
    assert status["rarity_coverage_pct"] == 100.0
    assert status["rankable"] is False


def test_supported_booster_with_no_hit_ladder_is_a_data_defect_not_unsupported():
    """The mirror case: a supported booster set with no hit-eligible card is a
    real defect and must stay loudly broken rather than be quietly excluded."""
    status = build_metric_status(
        _audit(canonical=200, unknown_rarity=0, hit_like=0),
        {"canonical_key": "evolvingSkies", "name": "Evolving Skies"},
    )
    assert status["metric_status"] == "unavailable_no_eligible_hit_structure"
    assert status["product_support_type"] == VALID_BOOSTER_SET
    assert status["rankable"] is False


def test_supported_booster_missing_rarity_mapping_is_distinguished():
    status = build_metric_status(
        _audit(canonical=200, unknown_rarity=200, hit_like=0),
        {"canonical_key": "evolvingSkies", "name": "Evolving Skies"},
    )
    assert status["metric_status"] == "unavailable_missing_rarity_mapping"
    assert status["rankable"] is False


def test_supported_booster_missing_subject_links_is_distinguished():
    status = build_metric_status(
        _audit(canonical=200, unknown_rarity=0, hit_like=40, linked_hits=0),
        {"canonical_key": "evolvingSkies", "name": "Evolving Skies"},
    )
    assert status["metric_status"] == "unavailable_missing_subject_links"
    assert status["rankable"] is False


def test_fully_covered_booster_is_valid_and_rankable():
    status = build_metric_status(
        _audit(canonical=200, unknown_rarity=0, hit_like=40, linked_hits=40),
        {"canonical_key": "evolvingSkies", "name": "Evolving Skies"},
    )
    assert status["metric_status"] == "valid"
    assert status["rankable"] is True


# ---------------------------------------------------------------------------
# The rankability guard
# ---------------------------------------------------------------------------

def _row(set_id, canonical_key, score, *, diagnostics=None):
    return {
        "set_id": set_id,
        "set_name": canonical_key,
        "set_canonical_key": canonical_key,
        "set_desirability_score": score,
        "diagnostics_json": diagnostics if diagnostics is not None else {},
    }


def test_unrankable_row_yields_none_never_zero():
    """The whole point of the guard: None means unavailable, 0.0 means worst."""
    row = _row("s1", "exTrainerKitLatias", 0.0)
    assert rankable_score(row) is None
    assert rankable_score(row) != 0.0


def test_genuine_zero_on_a_covered_set_stays_rankable():
    """A fully-covered booster set that honestly scores 0.0 keeps its rank.

    Filtering on ``score == 0`` instead of on status would discard exactly this
    row - the one honest zero we must keep.
    """
    row = _row("s2", "evolvingSkies", 0.0, diagnostics={"metric_status": "valid", "rankable": True})
    assert is_rankable(row) is True
    assert rankable_score(row) == 0.0


def test_partial_set_is_rankable_and_keeps_its_coverage_warning():
    row = _row(
        "s3",
        "someSet",
        41.2,
        diagnostics={
            "metric_status": "partial",
            "rankable": True,
            "availability_reason": "Coverage below 80%: rarity=72.00%, subject links=95.00%",
            "rarity_coverage_pct": 72.0,
        },
    )
    info = availability(row)
    assert info["rankable"] is True
    assert info["metric_status"] == "partial"
    assert info["rarity_coverage_pct"] == 72.0
    assert rankable_score(row) == 41.2


def test_guard_works_on_unmigrated_production_rows_via_product_fallback():
    """Every production row today has NO metric_status. The guard must still be
    correct, so closing the trap does not depend on first running a rebuild."""
    row = _row("s4", "mcdonaldSCollection2019", 0.0, diagnostics={})
    info = availability(row)
    assert info["rankable"] is False
    assert info["source"] == "product_support_fallback"
    assert info["product_support_type"] == UNSUPPORTED_MCDONALDS_COLLECTION
    assert rankable_score(row) is None


def test_unmigrated_booster_row_stays_rankable_via_fallback():
    row = _row("s5", "evolvingSkies", 63.4, diagnostics={})
    assert is_rankable(row) is True
    assert rankable_score(row) == 63.4


def test_rank_rankable_rows_refuses_to_rank_an_unrankable_row():
    """The trap closes at the accessor: a future consumer that forgets to filter
    fails loudly in tests rather than quietly ranking promos as worst."""
    rows = [_row("s1", "evolvingSkies", 50.0), _row("s2", "swshBlackStarPromos", 0.0)]
    with pytest.raises(UnrankableRowError) as excinfo:
        rank_rankable_rows(rows)
    assert "swshBlackStarPromos" in str(excinfo.value) or "s2" in str(excinfo.value)


def test_filter_then_rank_excludes_unavailable_and_preserves_valid_order():
    rows = [
        _row("s1", "evolvingSkies", 50.0),
        _row("s2", "swshBlackStarPromos", 0.0),
        _row("s3", "surgingSparks", 70.0),
        _row("s4", "baseSet", 0.0, diagnostics={"metric_status": "valid", "rankable": True}),
    ]
    ranked = rank_rankable_rows(filter_rankable(rows))
    assert [row["set_id"] for row in ranked] == ["s3", "s1", "s4"]
    assert ranked[0]["rank"] == 1
    # The genuine zero is ranked last but IS ranked; the promo is absent entirely.
    assert ranked[-1]["set_id"] == "s4"
    assert "s2" not in {row["set_id"] for row in ranked}


# ---------------------------------------------------------------------------
# RIP missing-pillar policy
# ---------------------------------------------------------------------------

def test_missing_desirability_makes_canonical_rip_unavailable():
    result = compute_weighted_rip(
        {"profit": 80.0, "safety": 70.0, "stability": 60.0, "desirability": None}
    )
    assert result["score"] is None
    assert result["status"] == "incomplete_missing_desirability"
    assert result["rankable"] is False
    assert result["missingPillars"] == ["desirability"]


def test_missing_desirability_does_not_renormalize_financial_pillars():
    """The behaviour the policy exists to prevent.

    Renormalizing would have produced 0.58/0.20/0.12 -> /0.90 = a canonical-
    looking 74.44 that sorts against real four-pillar scores.
    """
    result = compute_weighted_rip(
        {"profit": 80.0, "safety": 70.0, "stability": 60.0, "desirability": None}
    )
    assert result["score"] is None
    assert result["effectiveWeights"] == {}
    assert result["components"] == {}


def test_financial_only_numbers_remain_available_but_separately_labelled():
    result = compute_weighted_rip(
        {"profit": 80.0, "safety": 70.0, "stability": 60.0, "desirability": None}
    )
    financial = result["financialOnly"]
    assert financial["score"] is not None
    assert financial["version"] == "financial_rip_v2"
    assert "not comparable" in financial["label"].lower()
    # It must never be presented as, or mistaken for, the canonical RIP.
    assert result["score"] is None


def test_unsupported_promo_with_simulation_data_cannot_get_a_canonical_rip():
    """THE FUTURE CASE.

    Today no promo product has simulation rows, so nothing exercises this path.
    The day one does, it must not receive a renormalized canonical RIP that lets
    it out-rank real booster sets because its fourth pillar is absent.
    """
    promo_row = _row("promo-1", "swshBlackStarPromos", 0.0)
    assert is_rankable(promo_row) is False

    # Collector Appeal is unavailable precisely because the product is unsupported.
    collector_appeal = rankable_score(promo_row)
    assert collector_appeal is None

    result = compute_weighted_rip(
        {
            "profit": 95.0,        # a strong simulated financial profile
            "safety": 90.0,
            "stability": 88.0,
            "desirability": collector_appeal,
        }
    )
    assert result["score"] is None, "an unsupported promo must not receive a canonical RIP score"
    assert result["rankable"] is False
    assert result["status"] == "incomplete_missing_desirability"
    # And it must not be ranked in the canonical cohort.
    assert result.get("rank") is None


def test_explicit_financial_only_request_is_still_valid_and_renormalized():
    """Excluding desirability on purpose is not a missing pillar."""
    result = compute_financial_rip({"profit": 80.0, "safety": 70.0, "stability": 60.0})
    assert result["score"] is not None
    assert result["version"] == "financial_rip_v2"
    assert result["desirabilityIncluded"] is False


def test_zero_configured_desirability_weight_is_not_a_missing_pillar():
    result = compute_weighted_rip(
        {"profit": 80.0, "safety": 70.0, "stability": 60.0, "desirability": None},
        weights={"desirability": 0.0},
    )
    assert result["score"] is not None
    assert result.get("status") != "incomplete_missing_desirability"


def test_complete_four_pillar_rip_is_unchanged():
    result = compute_weighted_rip(
        {"profit": 80.0, "safety": 70.0, "stability": 60.0, "desirability": 50.0}
    )
    expected = 0.58 * 80.0 + 0.20 * 70.0 + 0.12 * 60.0 + 0.10 * 50.0
    assert result["score"] == pytest.approx(expected, abs=1e-6)
    assert result["desirabilityIncluded"] is True
    assert result.get("status") is None


def test_genuine_zero_desirability_still_produces_a_canonical_rip():
    """A real 0.0 Collector Appeal is data, not absence: RIP stays available."""
    result = compute_weighted_rip(
        {"profit": 80.0, "safety": 70.0, "stability": 60.0, "desirability": 0.0}
    )
    assert result["score"] is not None
    assert result["desirabilityIncluded"] is True
