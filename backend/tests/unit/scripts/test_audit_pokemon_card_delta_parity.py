"""Regression tests for shared selected-variant ownership in the Cards vs
Movers vs Top Chase parity audit.

Production has legitimate cases where multiple canonical checklist cards
share one selected card_variant_id+condition_id (see PR #166's fan-out fix
in pokemon_snapshot_builders.py). Market identity (variant+condition+window)
is therefore one-to-MANY with canonical identity, not one-to-one. These
tests pin the audit's handling of that relationship: it must collect every
legitimate owner per market identity per surface (not silently overwrite one
with another based on row order), it must still catch a genuine relabeling
divergence, and it must treat Top Chase as a subset surface rather than
requiring it to enumerate every owner Cards/Movers carry.
"""

from backend.scripts.audit_pokemon_card_delta_parity import audit_payloads


SHARED_VARIANT_ID = "variant-shared-1"
SHARED_CONDITION_ID = "condition-nm"


def _movement(*, current_price=100.0, change_amount=10.0, change_percent=11.11):
    return {
        "cardVariantId": SHARED_VARIANT_ID,
        "conditionId": SHARED_CONDITION_ID,
        "targetStartDate": "2026-08-27",
        "startDate": "2026-08-27",
        "endDate": "2026-09-03",
        "startSourceDate": "2026-08-27",
        "endSourceDate": "2026-09-03",
        "currentPrice": current_price,
        "changeAmount": change_amount,
        "changePercent": change_percent,
    }


def _card_entry(canonical_card_id):
    return {
        "id": canonical_card_id,
        "canonicalCardId": canonical_card_id,
        "cardVariantId": SHARED_VARIANT_ID,
        "conditionId": SHARED_CONDITION_ID,
        "movement7d": _movement(),
        "movement30d": _movement(),
    }


def _cards_payload(canonical_card_ids):
    return [_card_entry(card_id) for card_id in canonical_card_ids]


def _mover_entry(canonical_card_id):
    return {
        "canonicalCardId": canonical_card_id,
        "cardVariantId": SHARED_VARIANT_ID,
        "conditionId": SHARED_CONDITION_ID,
        **_movement(),
    }


def _dashboard_payload(mover_card_ids_7d, mover_card_ids_30d, *, top_chase_card_ids=()):
    return {
        "marketMoversByWindow": {
            "7D": {"all": [_mover_entry(card_id) for card_id in mover_card_ids_7d]},
            "30D": {"all": [_mover_entry(card_id) for card_id in mover_card_ids_30d]},
        },
        "topChaseCards": [
            {
                "canonicalCardId": card_id,
                "cardVariantId": SHARED_VARIANT_ID,
                "conditionId": SHARED_CONDITION_ID,
                "marketDeltaWindows": {
                    "7D": _movement(),
                    "30D": _movement(),
                },
            }
            for card_id in top_chase_card_ids
        ],
    }


def test_shared_variant_same_owners_reverse_order_passes_cards_vs_movers():
    """Two canonical cards (A, B) legitimately share one variant+condition
    on both Cards and Movers. Movers enumerates them in the REVERSE order
    Cards does. This must not be flagged as an identity mismatch — the
    owner SETS are identical, only row order differs."""
    mismatches = audit_payloads(
        _cards_payload(["card-a", "card-b"]),
        _dashboard_payload(
            mover_card_ids_7d=["card-b", "card-a"],
            mover_card_ids_30d=["card-b", "card-a"],
        ),
        set_id="set-1",
    )
    identity_mismatches = [m for m in mismatches if m["type"] == "identity mismatch"]
    assert identity_mismatches == []


def test_shared_variant_owner_divergence_between_cards_and_movers_fails():
    """Cards owners {A,B}, Movers owners {A,C} for the SAME market identity
    is a genuine relabeling/divergence and must be caught by the full
    Cards-vs-Movers comparison."""
    mismatches = audit_payloads(
        _cards_payload(["card-a", "card-b"]),
        _dashboard_payload(
            mover_card_ids_7d=["card-a", "card-c"],
            mover_card_ids_30d=["card-a", "card-c"],
        ),
        set_id="set-1",
    )
    identity_mismatches = [
        m for m in mismatches
        if m["type"] == "identity mismatch" and m["leftSurface"] == "cards" and m["rightSurface"] == "movers"
    ]
    assert len(identity_mismatches) == 2  # one per window (7D, 30D)
    for mismatch in identity_mismatches:
        assert mismatch["left"] == ["card-a", "card-b"]
        assert mismatch["right"] == ["card-a", "card-c"]


def test_top_chase_legitimate_subset_of_shared_owners_passes():
    """Top Chase is a subset surface: it legitimately need not carry every
    canonical owner Cards/Movers carry for a shared market identity. Cards
    has {A,B}; Top Chase only surfaces A (the chase-worthy one). This must
    not be flagged."""
    mismatches = audit_payloads(
        _cards_payload(["card-a", "card-b"]),
        _dashboard_payload(
            mover_card_ids_7d=["card-a", "card-b"],
            mover_card_ids_30d=["card-a", "card-b"],
            top_chase_card_ids=["card-a"],
        ),
        set_id="set-1",
    )
    identity_mismatches = [
        m for m in mismatches
        if m["type"] == "identity mismatch" and m["rightSurface"] == "top_chase"
    ]
    assert identity_mismatches == []


def test_top_chase_relabeled_owner_not_present_in_cards_fails():
    """Top Chase surfacing a canonical id that is NOT among Cards' legitimate
    owners for this market identity is a real relabeling and must fail, even
    though Top Chase is a subset surface — a subset must still be a genuine
    subset, not an arbitrary substitution."""
    mismatches = audit_payloads(
        _cards_payload(["card-a", "card-b"]),
        _dashboard_payload(
            mover_card_ids_7d=["card-a", "card-b"],
            mover_card_ids_30d=["card-a", "card-b"],
            top_chase_card_ids=["card-c"],
        ),
        set_id="set-1",
    )
    identity_mismatches = [
        m for m in mismatches
        if m["type"] == "identity mismatch"
        and m["leftSurface"] == "cards" and m["rightSurface"] == "top_chase"
    ]
    assert len(identity_mismatches) == 2  # one per window (7D, 30D)
    for mismatch in identity_mismatches:
        assert mismatch["left"] == ["card-a", "card-b"]
        assert mismatch["right"] == ["card-c"]


def test_single_owner_variant_unaffected_by_shared_variant_handling():
    """Existing one-canonical-card-per-variant behavior is unchanged: no
    false positives and a genuine single-owner relabeling still fails."""
    ok_mismatches = audit_payloads(
        _cards_payload(["card-x"]),
        _dashboard_payload(
            mover_card_ids_7d=["card-x"],
            mover_card_ids_30d=["card-x"],
            top_chase_card_ids=["card-x"],
        ),
        set_id="set-1",
    )
    assert [m for m in ok_mismatches if m["type"] == "identity mismatch"] == []

    relabeled_mismatches = audit_payloads(
        _cards_payload(["card-x"]),
        _dashboard_payload(
            mover_card_ids_7d=["card-y"],
            mover_card_ids_30d=["card-y"],
        ),
        set_id="set-1",
    )
    identity_mismatches = [m for m in relabeled_mismatches if m["type"] == "identity mismatch"]
    assert len(identity_mismatches) == 2
    for mismatch in identity_mismatches:
        assert mismatch["left"] == ["card-x"]
        assert mismatch["right"] == ["card-y"]
