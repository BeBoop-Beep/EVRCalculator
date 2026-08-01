"""The newly-onboarded-set gap in the CA7 pull model.

``load_pull_rate_model`` reads ``pokemon_set_page_snapshot_latest`` - the table
the set-page snapshot build WRITES. That read is therefore self-referential: a
set's pull model only becomes visible one full rebuild after its own row is
first written. An established set never shows it; a newly onboarded set has no
prior row at all, so CA7 reported ``dual_path_depth_unavailable_no_pull_model``
on its first build for a set whose simulation had already produced a complete
pack model (observed on Pitch Black, me5).

These tests pin the recovery and, just as importantly, pin that it stays out of
the way when it is not needed.
"""

import pytest

from backend.db.services import collector_appeal_service as service
from backend.db.services.collector_appeal_service import REASON_NO_PULL_MODEL
from backend.desirability import collector_appeal_inputs as inputs
from backend.desirability.collector_appeal_inputs import (
    pull_model_rarities_from_payload,
)
from backend.desirability.pull_model import (
    PULL_MODEL_FALLBACK_SOURCE,
    PULL_MODEL_LOADER_VERSION,
    pull_model_policy,
)

# Pitch Black's real pull-rate rows, as persisted in the set-page snapshot.
PITCH_BLACK_ROWS = [
    {"rarity": "common", "group": "pack_structure", "slot_label": "Base pack composition",
     "specific_card_odds_denominator": 9.25, "card_count": 37},
    {"rarity": "double rare", "group": "hit_rarity_model", "slot_label": "Rare slot model",
     "specific_card_odds_denominator": 48, "card_count": 10},
    {"rarity": "special illustration rare", "group": "hit_rarity_model",
     "slot_label": "Reverse slot model", "specific_card_odds_denominator": 480, "card_count": 6},
]


def _payload(rows, key="pull_rate_assumptions"):
    return {key: {"rows": list(rows)}}


# ---------------------------------------------------------------------------
# The shared mapping rule
# ---------------------------------------------------------------------------

def test_both_sources_map_rows_by_one_shared_rule():
    rarities = pull_model_rarities_from_payload(_payload(PITCH_BLACK_ROWS))
    assert sorted(rarities) == ["common", "double_rare", "special_illustration_rare"]
    assert rarities["double_rare"]["probability"] == pytest.approx(1 / 48)
    assert rarities["double_rare"]["slot_group"] == "Rare slot model"


def test_the_camelcase_payload_key_is_accepted_too():
    rarities = pull_model_rarities_from_payload(
        _payload(PITCH_BLACK_ROWS, key="pullRateAssumptions")
    )
    assert len(rarities) == 3


@pytest.mark.parametrize(
    "row",
    [
        {"rarity": "common", "specific_card_odds_denominator": 0},
        {"rarity": "common", "specific_card_odds_denominator": -3},
        {"rarity": "common", "specific_card_odds_denominator": None},
        {"rarity": "", "specific_card_odds_denominator": 10},
    ],
)
def test_unusable_rows_are_dropped_not_zeroed(row):
    # A zero probability would assert "this card cannot be pulled", which is a
    # measurement. Absence is the honest answer.
    assert pull_model_rarities_from_payload(_payload([row])) == {}


def test_a_payload_with_no_assumptions_yields_no_model():
    assert pull_model_rarities_from_payload({}) == {}
    assert pull_model_rarities_from_payload({"pull_rate_assumptions": None}) == {}


# ---------------------------------------------------------------------------
# The live fallback
# ---------------------------------------------------------------------------

def test_the_fallback_resolves_a_set_the_snapshot_does_not_carry(monkeypatch):
    monkeypatch.setattr(
        "backend.db.services.explore_page_service.get_explore_page_payload",
        lambda _t, _i: _payload(PITCH_BLACK_ROWS),
    )
    resolved = inputs.load_pull_rate_model_for_sets(["set-new"])
    assert sorted(resolved["set-new"]) == ["common", "double_rare", "special_illustration_rare"]


def test_the_fallback_is_a_no_op_when_nothing_is_missing(monkeypatch):
    called = []
    monkeypatch.setattr(
        "backend.db.services.explore_page_service.get_explore_page_payload",
        lambda _t, _i: called.append(_i) or _payload(PITCH_BLACK_ROWS),
    )
    assert inputs.load_pull_rate_model_for_sets([]) == {}
    assert called == [], "steady state must not touch the live source at all"


def test_a_set_with_no_simulation_stays_absent_rather_than_failing(monkeypatch):
    def _raise(_t, _i):
        raise RuntimeError("no simulation data found for this target")

    monkeypatch.setattr(
        "backend.db.services.explore_page_service.get_explore_page_payload", _raise
    )
    # A genuine absence must not take the bundle down, and must not invent a model.
    assert inputs.load_pull_rate_model_for_sets(["set-nosim"]) == {}


def test_a_set_with_no_pull_rate_mapping_stays_absent(monkeypatch):
    monkeypatch.setattr(
        "backend.db.services.explore_page_service.get_explore_page_payload",
        lambda _t, _i: {"pull_rate_assumptions": None},
    )
    assert inputs.load_pull_rate_model_for_sets(["set-nomapping"]) == {}


# ---------------------------------------------------------------------------
# Bundle integration
# ---------------------------------------------------------------------------

def _stub_bundle(monkeypatch, *, snapshot_model, fallback_model, coverage_status="full", subjects=None):
    seen = {}

    monkeypatch.setattr(
        service,
        "get_universal_desirability_bundle",
        lambda: {
            "payloads": {
                "set-established": {"set_name": "Established", "score": 80.0,
                                    "coverage": {"status": coverage_status}},
                "set-new": {"set_name": "Pitch Black", "score": 79.9,
                            "coverage": {"status": coverage_status}},
            }
        },
    )
    monkeypatch.setattr(service, "load_pull_rate_model", lambda _c: dict(snapshot_model))

    def _fallback(set_ids):
        seen["requested"] = list(set_ids)
        return {k: v for k, v in fallback_model.items() if k in set_ids}

    monkeypatch.setattr(service, "load_pull_rate_model_for_sets", _fallback)
    monkeypatch.setattr(service, "build_subject_index", lambda _c, _s, _p: subjects or {})
    return seen


def test_sets_without_full_coverage_are_never_probed(monkeypatch):
    # The bundle spans the whole catalog; most sets are vintage, have no
    # simulation, and fail on coverage long before the pull-model branch.
    # Probing the live source for them would be the N+1 this service forbids.
    seen = _stub_bundle(
        monkeypatch,
        snapshot_model={},
        fallback_model={"set-new": {"common": {"probability": 0.1, "slot_group": "s"}}},
        coverage_status="partial",
    )
    service._build_bundle()
    assert "requested" not in seen


def test_only_the_unmodeled_set_is_sent_to_the_fallback(monkeypatch):
    seen = _stub_bundle(
        monkeypatch,
        snapshot_model={"set-established": {"common": {"probability": 0.1, "slot_group": "s"}}},
        fallback_model={"set-new": {"common": {"probability": 0.1, "slot_group": "s"}}},
    )
    bundle = service._build_bundle()
    assert seen["requested"] == ["set-new"], "an already-modeled set must never be recomputed"
    assert bundle["coverage"]["modeledSetCount"] == 2


def test_a_recovered_set_no_longer_reports_no_pull_model(monkeypatch):
    _stub_bundle(
        monkeypatch,
        snapshot_model={"set-established": {"common": {"probability": 0.1, "slot_group": "s"}}},
        fallback_model={"set-new": {"common": {"probability": 0.1, "slot_group": "s"}}},
    )
    payload = service._build_bundle()["payloads"]["set-new"]
    assert payload["coverage"]["pullModelAvailable"] is True
    assert REASON_NO_PULL_MODEL not in payload["coverage"]["reasons"]


def test_first_build_live_model_produces_dual_path_and_canonical_ca7(monkeypatch):
    """A newly onboarded set needs no prior set-page snapshot to produce CA7."""
    subject = [{
        "subject_key": "ref:new", "subject_name": "New Pokemon",
        "subject_demand": 90.0, "appeal_excess": 40.0,
        "cards": [
            {"canonical_card_id": "easy", "card_name": "New Pokemon",
             "pull_probability": 0.10, "rarity": "Double Rare", "card_number": "1",
             "printed_number": "1", "rarity_priority": 3, "slot_group": "rare"},
            {"canonical_card_id": "rare", "card_name": "New Pokemon ex",
             "pull_probability": 0.001, "rarity": "Special Illustration Rare", "card_number": "2",
             "printed_number": "2", "rarity_priority": 8, "slot_group": "reverse"},
        ],
    }]
    _stub_bundle(
        monkeypatch, snapshot_model={},
        fallback_model={"set-new": {"double_rare": {"probability": 0.10, "slot_group": "rare"},
                                    "special_illustration_rare": {"probability": 0.001, "slot_group": "reverse"}}},
        subjects={"set-new": subject},
    )
    payload = service._build_bundle()["payloads"]["set-new"]
    assert payload["status"] == "available"
    assert payload["dualPathDepth"]["rawValue"] > 0
    assert payload["collectorAppeal"]["rawValue"] > 0
    from backend.desirability.weighted_rip import compute_overall_rip
    overall = compute_overall_rip(
        {"profit": 70.0, "safety": 65.0, "stability": 60.0},
        payload["collectorAppeal"]["score"],
    )
    assert overall["rankable"] is True
    assert overall["score"] > 0


def test_a_set_the_fallback_cannot_resolve_still_reports_no_pull_model(monkeypatch):
    # The fix must not paper over a real absence.
    _stub_bundle(
        monkeypatch,
        snapshot_model={"set-established": {"common": {"probability": 0.1, "slot_group": "s"}}},
        fallback_model={},
    )
    payload = service._build_bundle()["payloads"]["set-new"]
    assert payload["coverage"]["pullModelAvailable"] is False
    assert payload["coverage"]["reasons"] == [REASON_NO_PULL_MODEL]


def test_the_fallback_cannot_override_a_materialized_model(monkeypatch):
    snapshot = {"set-established": {"common": {"probability": 0.5, "slot_group": "snapshot"}},
                "set-new": {"common": {"probability": 0.5, "slot_group": "snapshot"}}}
    seen = _stub_bundle(
        monkeypatch,
        snapshot_model=snapshot,
        fallback_model={"set-new": {"common": {"probability": 0.9, "slot_group": "live"}}},
    )
    service._build_bundle()
    assert "requested" not in seen, "nothing is missing, so the live source is never consulted"


# ---------------------------------------------------------------------------
# Policy identity
# ---------------------------------------------------------------------------

def test_the_loader_version_records_the_added_source():
    assert PULL_MODEL_LOADER_VERSION.startswith("pull_model_loader_v2")
    policy = pull_model_policy()
    assert policy["loader_version"] == PULL_MODEL_LOADER_VERSION
    # The fingerprint must be able to see the fallback; an invisible source is
    # exactly the drift this module exists to prevent.
    assert policy["fallback_source"] == PULL_MODEL_FALLBACK_SOURCE
