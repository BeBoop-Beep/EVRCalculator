from datetime import datetime, timezone

from backend.db.services.market_activity_projection_repository import (
    _candidate_contract,
    _collection_record_contract,
    _snapshot_contract,
    _sold_record_contract,
)
from backend.domain.pokemon.market_activity import (
    evaluate_supply_snapshot,
    resolve_exact_identity,
)


VARIANT = "9874f528-8009-43af-bd45-74095b43410f"


def test_live_sold_adapter_preserves_strict_identity_and_grade_qualifier_fields():
    candidate = _candidate_contract({
        "id": VARIANT,
        "edition": None,
        "printing_type": "holo",
        "special_type": None,
    })
    record = _sold_record_contract({
        "provider_card_id": 16146,
        "provider_listing_id": 176931907,
        "price": "930.00",
        "currency": "USD",
        "sold_at": "2026-09-28",
        "ingested_at": "2026-09-30T03:24:37Z",
        "collected_at": "2026-09-30T03:24:37Z",
        "provider_variant": "Holofoil",
        "attribution": "exact",
        "grader": "CGC",
        "grade": "10",
        "grade_qualifier": "Pristine",
        "graded": True,
    })

    assert candidate == {
        "id": VARIANT,
        "edition": None,
        "printingType": "holo",
        "specialType": None,
    }
    assert record["gradeQualifier"] == "Pristine"
    assert "qualifier" not in record

    identity = resolve_exact_identity(
        attribution=record["attribution"],
        provider_variant=record["providerVariant"],
        candidates=[candidate],
        candidate_scope="FULL_CARD_VARIANT_SET",
        currency=record["currency"],
    )
    assert identity.publishable is True
    assert identity.card_variant_id == VARIANT


def test_live_sync_adapter_marks_only_successful_sync_as_collection_evidence():
    assert _collection_record_contract(
        {"last_success_at": "2026-09-30T03:24:37Z"}, 16146
    ) == {
        "collected": True,
        "providerCardId": "16146",
        "lastSuccessAt": "2026-09-30T03:24:37Z",
    }
    assert _collection_record_contract({"last_success_at": None}, 16146) is None


def test_live_supply_adapter_preserves_observation_state_for_domain_evaluation():
    snapshot = _snapshot_contract(
        {
            "id": "b2a947ff-4071-40c3-8858-609311e5bfcc",
            "observation_state": "OBSERVED",
            "observed_at": "2026-09-29T22:08:11Z",
            "has_more": True,
            "source_payload": {"bounded_depth": True},
        },
        "COMPLETE",
        [{
            "item_price": "49.99",
            "shipping_price": "0.00",
            "quantity": 2,
            "provider_snapshot_at": "2026-09-29T21:58:09Z",
            "listing_updated_at": "2026-09-29T17:51:36Z",
        }],
    )

    assert snapshot["observationState"] == "OBSERVED"
    result = evaluate_supply_snapshot(
        snapshot,
        evaluated_at=datetime(2026, 9, 29, 22, 8, 11, tzinfo=timezone.utc),
    )
    assert result["state"] == "FRESH"
    assert result["capturedListingCount"] == 1
    assert result["capturedQuantity"]["value"] == 2
    assert result["depth"] == "LOWER_BOUND"
    assert result["lowestAsk"]["price"]["amount"] == "49.99"
