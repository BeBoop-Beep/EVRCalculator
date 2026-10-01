from backend.scripts.research_treatment_panel_recovery_v2 import (
    evaluate_ladders,
    provider_row_matches_local,
    provider_variant_identity,
)


def test_provider_variant_identity_is_conservative():
    assert provider_variant_identity("Normal") == (None, "non-holo", None)
    assert provider_variant_identity("Holofoil") == (None, "holo", None)
    assert provider_variant_identity("Reverse Holofoil") == (None, "reverse-holo", None)
    assert provider_variant_identity("1st Edition Holofoil") == ("first-edition", "holo", None)
    assert provider_variant_identity("Master Ball Reverse Holofoil") == (
        None,
        "reverse-holo",
        "master-ball",
    )


def test_plain_holo_does_not_borrow_special_treatment():
    plain = {"edition": None, "printing_type": "holo", "special_type": None}
    master = {"edition": None, "printing_type": "holo", "special_type": "master-ball"}
    assert provider_row_matches_local("Holofoil", plain, "Prismatic Evolutions")
    assert not provider_row_matches_local("Master Ball Holofoil", plain, "Prismatic Evolutions")
    assert provider_row_matches_local("Master Ball Holofoil", master, "Prismatic Evolutions")


def _cohort(tier=1):
    return {
        "fullyMappedLadders": [
            {
                "identity": "pokemon:test",
                "set": "Test Set",
                "era": "Test Era",
                "tier": tier,
                "treatments": ["unknown|non-holo|unknown", "unknown|reverse-holo|unknown"],
                "cardIds": ["card-1"],
                "variantIds": ["normal", "reverse"],
                "round24Status": "HISTORY_BLOCKED",
                "editionFinishMetadata": [
                    {"id": "normal", "edition": None, "printing_type": "non-holo", "special_type": None},
                    {"id": "reverse", "edition": None, "printing_type": "reverse-holo", "special_type": None},
                ],
            }
        ]
    }


def _history(days):
    rows = []
    for day in range(1, days + 1):
        stamp = f"2026-01-{((day - 1) % 28) + 1:02d}-{day:03d}"
        # evaluate_ladders treats the date as an opaque exact key; unique strings
        # keep this unit test independent of calendar construction.
        rows.append({"date": stamp, "variant": "Normal"})
        rows.append({"date": stamp, "variant": "Reverse Holofoil"})
    return {"card-1": rows}


def test_round24_strong_gate_is_90_exact_shared_dates():
    result = evaluate_ladders(_cohort(tier=1), _history(90))
    assert result["statusCounts"] == {"PANEL_READY_STRONG": 1}
    assert result["ladders"][0]["sharedDateCount"] == 90


def test_round24_tier1_moderate_gate_is_30_exact_shared_dates():
    result = evaluate_ladders(_cohort(tier=1), _history(30))
    assert result["statusCounts"] == {"PANEL_READY_MODERATE": 1}


def test_non_tier1_does_not_use_30_day_moderate_exception():
    result = evaluate_ladders(_cohort(tier=2), _history(30))
    assert result["statusCounts"] == {"HISTORY_BLOCKED": 1}


def test_missing_one_variant_remains_history_blocked():
    rows = [{"date": f"2026-01-{((day - 1) % 28) + 1:02d}-{day:03d}", "variant": "Normal"} for day in range(1, 100)]
    result = evaluate_ladders(_cohort(tier=1), {"card-1": rows})
    assert result["statusCounts"] == {"HISTORY_BLOCKED": 1}
    assert result["ladders"][0]["sharedDateCount"] == 0
