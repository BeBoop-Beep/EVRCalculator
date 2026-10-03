import numpy as np

from backend.scripts.research_treatment_set_relative_hierarchy_v2 import (
    DOUBLE,
    FRESH_EXPECTED_BY_SET,
    FRESH_TARGET_FINGERPRINT,
    SIR,
    ULTRA,
    design,
    fit,
    fresh_coverage,
    set_levels,
)


def _row(set_name, high, low, y, scarcity=0.0, artist=0.0):
    return {
        "set_name": set_name,
        "high_treatment": high,
        "low_treatment": low,
        "mean_log_ratio": y,
        "scarcity_log_ratio": scarcity,
        "artist_delta": artist,
    }


def test_dynamic_set_specific_design_recovers_levels():
    set_order = [
        "Perfect Order",
        "Phantasmal Flames",
        "Pitch Black",
        "Obsidian Flames",
        "Scarlet and Violet 151",
    ]
    rows = []
    for i, set_name in enumerate(set_order):
        ur = 0.2 + i * 0.05
        sir = 1.0 + i * 0.1
        rows += [
            _row(set_name, ULTRA, DOUBLE, ur),
            _row(set_name, SIR, DOUBLE, sir),
            _row(set_name, SIR, ULTRA, sir - ur),
        ]
    rows[0]["scarcity_log_ratio"] = 1.0
    rows[0]["mean_log_ratio"] += 0.4
    rows[4]["artist_delta"] = 100.0
    rows[4]["mean_log_ratio"] += 0.3

    beta, rank, condition = fit(rows, set_order)
    assert rank == len(set_order) * 2 + 2
    assert condition < 30
    levels = set_levels(beta, set_order)
    for i, set_name in enumerate(set_order):
        assert np.isclose(levels[set_name][ULTRA], 0.2 + i * 0.05)
        assert np.isclose(levels[set_name][SIR], 1.0 + i * 0.1)
    assert np.isclose(beta[-2], 0.4)
    assert np.isclose(beta[-1], 0.3)


def test_dynamic_design_width_tracks_included_sets():
    set_order = ["Perfect Order", "Pitch Black", "Destined Rivals"]
    X, y = design([_row(set_order[0], ULTRA, DOUBLE, 0.0)], set_order)
    assert X.shape == (1, len(set_order) * 2 + 2)
    assert y.shape == (1,)


def _fresh_panel():
    triads = []
    triad_results = []
    panels = {}
    serial = 0
    for set_name, count in FRESH_EXPECTED_BY_SET.items():
        era_name = "Mega Evolution" if set_name == "Pitch Black" else "Scarlet and Violet"
        for i in range(count):
            subject = f"subject:{set_name}:{i}"
            cards = []
            for rarity in (DOUBLE, ULTRA, SIR):
                serial += 1
                cid = f"card-{serial}"
                cards.append({
                    "canonical_card_id": cid,
                    "rarity": rarity,
                    "set_name": set_name,
                    "era_name": era_name,
                    "subject_key": subject,
                    "modeled_probability": 0.01,
                })
                panels[cid] = {"history": [{"date": "2026-09-01", "price": 1.0}]}
            triads.append({
                "set_name": set_name,
                "era_name": era_name,
                "subject_key": subject,
                "cards": cards,
            })
            triad_results.append({
                "set_name": set_name,
                "era_name": era_name,
                "subject_key": subject,
                "ready": True,
            })
    return {
        "status": "COMPLETE",
        "production_writes": 0,
        "target": {
            "fingerprint": FRESH_TARGET_FINGERPRINT,
            "triad_count": 56,
            "card_count": 168,
            "by_set": dict(FRESH_EXPECTED_BY_SET),
            "triads": triads,
        },
        "triad_results": triad_results,
        "panels": panels,
    }


def test_fresh_coverage_gate_passes_frozen_full_panel():
    result = fresh_coverage(_fresh_panel())
    assert result["pass"] is True
    assert result["ready_triads"] == 56
    assert result["pitch_black_ready"] == 4
    assert result["qualifying_sv_sets"] == 9
    assert result["fresh_cards_returned"] == 168


def test_fresh_coverage_gate_enforces_pitch_black_minimum():
    panel = _fresh_panel()
    disabled = 0
    for row in panel["triad_results"]:
        if row["set_name"] == "Pitch Black" and disabled < 2:
            row["ready"] = False
            disabled += 1
    result = fresh_coverage(panel)
    assert result["ready_triads"] == 54
    assert result["pitch_black_ready"] == 2
    assert result["pass"] is False
