from backend.scripts import audit_market_explorer_variant_identity as audit_module


def test_stale_selected_price_flagged_when_raw_observations_are_current():
    """Regression fixture modeled on Nintendo Black Star Promos: raw NM
    observations are current on the target date, canonical selected-price
    rows exist but stop 16 days earlier because no selected identity
    reaches the target date. Synthetic ids only -- never real production
    UUIDs."""
    set_id = "set-synthetic-promos"
    canonical_card_id = "canonical-raichu-27"
    stale_variant_id = "variant-old-identity"
    fresh_variant_id = "variant-new-identity"

    # canonical selected-price row still points at the stale (old) identity
    selected_rows = [{
        "canonical_card_id": canonical_card_id,
        "card_variant_id": stale_variant_id,
        "condition_id": "condition-nm",
        "market_price": 5.0,
        "captured_at": "2026-08-17T00:00:00Z",
    }]
    # raw NM observations: stale identity has old data, a DIFFERENT
    # (unlinked) fresh identity has data through the target date -- this
    # models "fresh observations exist on replacement TCGPlayer identities"
    raw_rows = [
        {"card_variant_id": stale_variant_id, "condition_id": "condition-nm",
         "market_price": 5.0, "captured_at": "2026-08-17T00:00:00Z"},
        {"card_variant_id": fresh_variant_id, "condition_id": "condition-nm",
         "market_price": 6.0, "captured_at": "2026-09-02T00:00:00Z"},
    ]

    result = audit_module._compute_canonical_price_identity_drift(
        set_id=set_id,
        canonical_key="nintendo-black-star-promos-synthetic",
        selected_rows=selected_rows,
        raw_observation_rows=raw_rows,
    )

    assert len(result) == 1
    drift = result[0]
    assert drift["setId"] == set_id
    assert drift["canonicalKey"] == "nintendo-black-star-promos-synthetic"
    assert drift["selectedLatestDate"] == "2026-08-17"
    assert drift["rawLatestDate"] == "2026-09-02"
    assert drift["selectedRowCount"] == 1
    assert drift["currentRawIdentityCount"] == 2


def test_no_drift_flagged_when_selected_price_tracks_raw_freshness():
    set_id = "set-synthetic-healthy"
    selected_rows = [{
        "canonical_card_id": "canonical-x",
        "card_variant_id": "variant-x",
        "condition_id": "condition-nm",
        "market_price": 10.0,
        "captured_at": "2026-09-02T00:00:00Z",
    }]
    raw_rows = [{
        "card_variant_id": "variant-x", "condition_id": "condition-nm",
        "market_price": 10.0, "captured_at": "2026-09-02T00:00:00Z",
    }]

    result = audit_module._compute_canonical_price_identity_drift(
        set_id=set_id, canonical_key="healthy-set",
        selected_rows=selected_rows, raw_observation_rows=raw_rows,
    )

    assert result == []


def test_no_drift_flagged_when_no_selected_rows_exist():
    result = audit_module._compute_canonical_price_identity_drift(
        set_id="set-synthetic-empty", canonical_key="empty-set",
        selected_rows=[], raw_observation_rows=[{
            "card_variant_id": "variant-x", "condition_id": "condition-nm",
            "market_price": 1.0, "captured_at": "2026-09-02T00:00:00Z",
        }],
    )

    assert result == []
