from __future__ import annotations

import pytest

from backend.scripts.research_treatment_panel_recovery_v2 import (
    build_panel_readiness,
    choose_variant,
    panel_status,
    provider_variant_name,
    validate_history_rows,
    _active_b5_runs,
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


class _Result:
    def __init__(self, data):
        self.data = data


class _RunQuery:
    def __init__(self, rows):
        self.rows = rows

    def select(self, *_args, **_kwargs):
        return self

    def order(self, *_args, **_kwargs):
        return self

    def limit(self, count):
        self.rows = self.rows[:count]
        return self

    def execute(self):
        return _Result(self.rows)


class _RunDb:
    def __init__(self, rows):
        self.rows = rows

    def table(self, name):
        assert name == "pkmnprices_sold_runs_v1"
        return _RunQuery(list(self.rows))


def test_active_b5_detection_ignores_superseded_orphan_receipts():
    rows = [
        {
            "run_id": "new-terminal",
            "status": "PARTIAL",
            "started_at": "2026-10-01T18:52:00+00:00",
            "finished_at": "2026-10-01T18:53:00+00:00",
            "selector_version": "bucket_b5_gap_then_governed_7d_movers_v2",
        },
        {
            "run_id": "old-orphan",
            "status": "RUNNING",
            "started_at": "2026-10-01T18:07:00+00:00",
            "finished_at": None,
            "selector_version": "bucket_b5_gap_then_governed_7d_movers_v2",
        },
    ]
    assert _active_b5_runs(_RunDb(rows)) == []


def test_active_b5_detection_keeps_latest_live_selector():
    rows = [
        {
            "run_id": "new-live",
            "status": "RUNNING",
            "started_at": "2026-10-01T19:30:00+00:00",
            "finished_at": None,
            "selector_version": "bucket_b5_gap_then_governed_7d_movers_v2",
        },
        {
            "run_id": "old-terminal",
            "status": "PARTIAL",
            "started_at": "2026-10-01T19:15:00+00:00",
            "finished_at": "2026-10-01T19:16:00+00:00",
            "selector_version": "bucket_b5_gap_then_governed_7d_movers_v2",
        },
    ]
    assert [row["run_id"] for row in _active_b5_runs(_RunDb(rows))] == ["new-live"]
