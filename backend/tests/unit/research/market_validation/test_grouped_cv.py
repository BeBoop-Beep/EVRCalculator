from __future__ import annotations

import pytest

from backend.research.market_validation.grouped_cv import (
    assert_no_set_leakage,
    era_held_out_folds,
    grouped_kfold_by_set,
    leave_whole_set_out_folds,
)


class TestLeaveWholeSetOut:
    def test_one_fold_per_distinct_set(self, synthetic_card_records):
        n_sets = len({r["set_id"] for r in synthetic_card_records})
        folds = leave_whole_set_out_folds(synthetic_card_records)
        assert len(folds) == n_sets

    def test_no_set_leakage_in_any_fold(self, synthetic_card_records):
        folds = leave_whole_set_out_folds(synthetic_card_records)
        for fold in folds:
            assert_no_set_leakage(synthetic_card_records, fold)

    def test_val_fold_contains_only_its_own_set(self, synthetic_card_records):
        folds = leave_whole_set_out_folds(synthetic_card_records)
        for train_idx, val_idx in folds:
            val_sets = {synthetic_card_records[i]["set_id"] for i in val_idx}
            assert len(val_sets) == 1

    def test_train_plus_val_covers_everything_exactly_once(self, synthetic_card_records):
        folds = leave_whole_set_out_folds(synthetic_card_records)
        train_idx, val_idx = folds[0]
        assert set(train_idx) | set(val_idx) == set(range(len(synthetic_card_records)))
        assert set(train_idx) & set(val_idx) == set()


class TestGroupedKFold:
    def test_no_set_leakage_across_folds(self, synthetic_card_records):
        folds = grouped_kfold_by_set(synthetic_card_records, k=4, seed=1)
        for fold in folds:
            assert_no_set_leakage(synthetic_card_records, fold)

    def test_deterministic_given_seed(self, synthetic_card_records):
        folds_a = grouped_kfold_by_set(synthetic_card_records, k=4, seed=7)
        folds_b = grouped_kfold_by_set(synthetic_card_records, k=4, seed=7)
        assert folds_a == folds_b

    def test_different_seeds_can_differ(self, synthetic_card_records):
        folds_a = grouped_kfold_by_set(synthetic_card_records, k=4, seed=1)
        folds_b = grouped_kfold_by_set(synthetic_card_records, k=4, seed=999)
        assert folds_a != folds_b

    def test_rejects_k_below_2(self, synthetic_card_records):
        with pytest.raises(ValueError):
            grouped_kfold_by_set(synthetic_card_records, k=1)


class TestEraHeldOut:
    def test_one_fold_per_era_no_leakage(self, synthetic_card_records):
        folds = era_held_out_folds(synthetic_card_records, era_key="era")
        n_eras = len({r["era"] for r in synthetic_card_records})
        assert len(folds) == n_eras
        for fold in folds:
            train_idx, val_idx = fold
            train_eras = {synthetic_card_records[i]["era"] for i in train_idx}
            val_eras = {synthetic_card_records[i]["era"] for i in val_idx}
            assert not (train_eras & val_eras)


class TestLeakageGuard:
    def test_raises_on_synthetic_leaking_fold(self, synthetic_card_records):
        bad_fold = ([0, 1, 2], [0, 3, 4])  # index 0's set appears on both sides
        with pytest.raises(ValueError, match="leakage"):
            assert_no_set_leakage(synthetic_card_records, bad_fold)
