from __future__ import annotations

import pytest

from backend.scripts.research_treatment_panel_recovery_v2 import (
    build_panel_readiness,
    choose_variant,
    panel_status,
    provider_variant_name,
    validate_history_rows,
)


def test_provider_variant_mapping_is_exact_and_fail_closed():
    assert provider_variant_name("non-holo") == "Normal"
    assert provider_variant_name("holo") == "Holofoil"
    assert provider_variant_name("reverse-holo") == "Reverse Holofoil"
    with pytest.raises(RuntimeError):
        provider_variant_name("holo", special_type="master_ball")


def test_choose_variant_prefers_normal_for_common_and_holo_for_premium():
    common = {"id": "c-common", "rarity": "Common"}
    premium = {"id": "c-premium", "rarity": "Special Illustration Rare"}
    variants = [
        {"id": "v-common-normal", "canonical_card_id": "c-common", "printing_type": "non-holo", "special_type": None},
        {"id": "v-common-reverse", "canonical_card_id": "c-common", "printing_type": "reverse-holo", "special_type": None},
        {"id": "v-premium-holo", "canonical_card_id": "c-premium", "printing_type": "holo", "special_type": None},
    ]
    assert choose_variant(common, variants)["id"] == "v-common-normal"
    assert choose_variant(premium, variants)["id"] == "v-premium-holo"


def test_history_validation_rejects_wrong_condition_or_variant():
    good = [{
        "date": "2026-09-01", "source": "tcgplayer", "currency": "USD",
        "condition": "Near Mint", "variant": "Holofoil", "avg": 10, "low": 9, "high": 11,
    }]
    assert validate_history_rows(good, variant="Holofoil")[0]["avg"] == 10
    bad = [{**good[0], "condition": "Lightly Played"}]
    with pytest.raises(RuntimeError):
        validate_history_rows(bad, variant="Holofoil")
    bad = [{**good[0], "variant": "Reverse Holofoil"}]
    with pytest.raises(RuntimeError):
        validate_history_rows(bad, variant="Holofoil")


def test_round24_status_thresholds_are_preserved():
    assert panel_status(1, 90) == "PANEL_READY_STRONG"
    assert panel_status(1, 30) == "PANEL_READY_MODERATE"
    assert panel_status(2, 89) == "HISTORY_BLOCKED"
    assert panel_status(2, 90) == "PANEL_READY_MODERATE"


def test_panel_readiness_requires_two_identities_in_two_sets():
    sample = [
        {"family": "a <> b", "set": "Set 1", "era": "Era", "identity": "i1", "tier": 2, "cardIds": ["a1", "b1"]},
        {"family": "a <> b", "set": "Set 1", "era": "Era", "identity": "i2", "tier": 2, "cardIds": ["a2", "b2"]},
        {"family": "a <> b", "set": "Set 2", "era": "Era", "identity": "i3", "tier": 2, "cardIds": ["a3", "b3"]},
        {"family": "a <> b", "set": "Set 2", "era": "Era", "identity": "i4", "tier": 2, "cardIds": ["a4", "b4"]},
    ]
    history = {}
    dates = [f"2026-06-{(n % 30)+1:02d}-{n//30}" for n in range(90)]
    for card in ["a1","b1","a2","b2","a3","b3","a4","b4"]:
        history[card] = [{"date": d} for d in dates]
    report = build_panel_readiness(sample, history)
    assert report["anyEraHierarchyGatePass"] is True
    gate = report["eraFamilyGates"][0]
    assert gate["passingSetCount"] == 2


def test_panel_readiness_does_not_forward_fill_missing_dates():
    sample = [{"family": "a <> b", "set": "Set 1", "era": "Era", "identity": "i1", "tier": 2, "cardIds": ["a","b"]}]
    history = {
        "a": [{"date": "2026-01-01"}, {"date": "2026-01-02"}],
        "b": [{"date": "2026-01-02"}, {"date": "2026-01-03"}],
    }
    report = build_panel_readiness(sample, history)
    assert report["identities"][0]["sharedDateCount"] == 1
    assert report["identities"][0]["firstSharedDate"] == "2026-01-02"
