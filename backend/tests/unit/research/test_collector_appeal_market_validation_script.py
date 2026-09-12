import pytest

from backend.scripts.research_collector_appeal_market_validation import (
    INPUT_CONTRACT_VERSION,
    build_waiting_report,
    merge_frozen_appeal,
    validate_frozen_input,
)


def _payload(*, status="frozen", price_excluded=True, cross_bucket=False):
    return {
        "contractVersion": INPUT_CONTRACT_VERSION,
        "freeze": {
            "status": status,
            "modelVersion": "collector_v6_corrected",
            "formulaFingerprint": "abc123",
            "priceInputExcluded": price_excluded,
        },
        "components": [
            {
                "name": "pokemon_subject",
                "scoreKey": "pokemon_subject",
                "subjectTypes": ["pokemon"],
                "role": "candidate",
            },
            {
                "name": "final_card_appeal",
                "scoreKey": "final_card_appeal",
                "subjectTypes": ["pokemon", "trainer"],
                "role": "final",
                "crossBucketComparable": cross_bucket,
            },
        ],
        "rows": [],
    }


def test_validation_input_must_be_explicitly_frozen_and_price_independent():
    with pytest.raises(ValueError, match="explicitly be frozen"):
        validate_frozen_input(_payload(status="building", cross_bucket=True))
    with pytest.raises(ValueError, match="priceInputExcluded"):
        validate_frozen_input(_payload(price_excluded=False, cross_bucket=True))


def test_pooled_final_component_requires_cross_bucket_freeze():
    with pytest.raises(ValueError, match="cross-bucket comparability"):
        validate_frozen_input(_payload(cross_bucket=False))
    specs = validate_frozen_input(_payload(cross_bucket=True))
    assert specs[-1].cross_bucket_comparable is True


def test_merge_is_exact_canonical_id_only_and_keeps_bucket_label():
    payload = _payload(cross_bucket=True)
    payload["rows"] = [
        {
            "canonical_card_id": "card-1",
            "subject_type": "pokemon",
            "scores": {"pokemon_subject": 82.0, "final_card_appeal": 84.0},
        },
        {
            "canonical_card_id": "not-in-market",
            "subject_type": "trainer",
            "scores": {"final_card_appeal": 70.0},
        },
    ]
    specs = validate_frozen_input(payload)
    market = [
        {"card_id": "card-1", "log_price": 2.0, "pull_scarcity": 1.2},
        {"card_id": "card-2", "log_price": 1.0, "pull_scarcity": 1.0},
    ]
    merged, diagnostics = merge_frozen_appeal(market, payload, specs)
    assert len(merged) == 1
    assert merged[0]["subject_type"] == "pokemon"
    assert merged[0]["appeal::pokemon_subject"] == 82.0
    assert diagnostics["marketRowsWithoutAppealRow"] == 1
    assert diagnostics["appealRowsOutsideMarketCohort"] == 1
    assert diagnostics["joinKey"] == "canonical card id exact match"


def test_default_waiting_report_proves_no_model_evaluation():
    report = build_waiting_report({"cohortFingerprint": "market123", "counts": {"modeledRows": 10}})
    assert report["status"] == "READY_AWAITING_FROZEN_V6"
    assert report["evaluationPerformed"] is False
    assert report["guardrails"]["readsCurrentCollectorPointer"] is False
    assert report["guardrails"]["tunesCollectorAppeal"] is False
