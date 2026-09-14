from __future__ import annotations

import math

import pytest

from backend.research.market_validation.price_separation import (
    PriceContaminationError,
    assert_no_price_in_predictor_keys,
    assert_scoring_config_price_free,
    strip_price_fields,
)
from backend.research.market_validation.schema import validate_card_records, validate_set_records


class TestCardSchemaValidation:
    def test_valid_records_have_no_problems(self, synthetic_card_records):
        problems = validate_card_records(synthetic_card_records)
        assert problems == []

    def test_duplicate_canonical_card_id_is_flagged(self, synthetic_card_records):
        records = list(synthetic_card_records) + [dict(synthetic_card_records[0])]
        problems = validate_card_records(records)
        assert any("duplicate" in p for p in problems)

    def test_missing_canonical_card_id_is_flagged(self):
        problems = validate_card_records([{"market_price": 5.0}])
        assert any("missing canonical_card_id" in p for p in problems)

    def test_inconsistent_log_price_is_flagged(self):
        problems = validate_card_records(
            [{"canonical_card_id": "x", "market_price": 10.0, "log_market_price": 999.0}]
        )
        assert any("inconsistent" in p for p in problems)

    def test_consistent_log_price_is_not_flagged(self):
        problems = validate_card_records(
            [{"canonical_card_id": "x", "market_price": 10.0, "log_market_price": math.log(10.0)}]
        )
        assert problems == []


class TestSetSchemaValidation:
    def test_valid_set_records_have_no_problems(self):
        records = [
            {"set_id": "root", "is_canonical_root": True},
            {"set_id": "sub", "is_canonical_root": False, "canonical_root_set_id": "root"},
        ]
        assert validate_set_records(records) == []

    def test_subset_without_root_reference_is_flagged(self):
        records = [{"set_id": "sub", "is_canonical_root": False}]
        problems = validate_set_records(records)
        assert any("canonical_root_set_id" in p for p in problems)

    def test_duplicate_set_id_is_flagged(self):
        records = [{"set_id": "a"}, {"set_id": "a"}]
        assert any("duplicate" in p for p in validate_set_records(records))


class TestPriceSeparationContract:
    def test_price_field_in_predictor_keys_raises(self):
        with pytest.raises(PriceContaminationError):
            assert_no_price_in_predictor_keys(["pokemon_subject_appeal", "market_price"])

    def test_clean_predictor_keys_pass(self):
        assert_no_price_in_predictor_keys(["pokemon_subject_appeal", "trainer_appeal"])

    def test_price_shaped_scoring_config_key_raises(self):
        with pytest.raises(PriceContaminationError):
            assert_scoring_config_price_free({"weights": {"market_price_weight": 0.1}})

    def test_legitimate_price_policy_field_does_not_raise(self):
        assert_scoring_config_price_free({"price_policy": "excluded"})

    def test_nested_price_field_is_caught(self):
        with pytest.raises(PriceContaminationError):
            assert_scoring_config_price_free({"a": {"b": [{"set_value_anchor": 1}]}})

    def test_strip_price_fields_removes_all_price_keys(self):
        record = {"pokemon_subject_appeal": 80, "market_price": 12.0, "log_market_price": 2.5}
        stripped = strip_price_fields(record)
        assert "market_price" not in stripped
        assert "log_market_price" not in stripped
        assert stripped["pokemon_subject_appeal"] == 80
