"""Grouped, set-aware cross-validation.

Cards from the same set are structurally similar (shared era, shared rarity mix,
shared Collector-model inputs) -- a random card-level split would let near-
duplicate structure leak between train and validation, inflating apparent OOS
performance. Every fold here holds out whole sets, never individual cards.
"""
from __future__ import annotations

import random
from typing import Any, Dict, List, Mapping, Sequence, Tuple


def leave_whole_set_out_folds(
    records: Sequence[Mapping[str, Any]], set_key: str = "set_id"
) -> List[Tuple[List[int], List[int]]]:
    """One fold per distinct set: that set's rows are the validation fold, every
    other row is the training fold. Returns (train_indices, val_indices) pairs.
    Deterministic (no randomness) -- iterates sets in the order they were first
    seen in `records`.
    """
    sets_in_order: List[Any] = []
    seen = set()
    indices_by_set: Dict[Any, List[int]] = {}
    for i, row in enumerate(records):
        key = row.get(set_key)
        if key not in seen:
            seen.add(key)
            sets_in_order.append(key)
        indices_by_set.setdefault(key, []).append(i)

    all_indices = list(range(len(records)))
    folds: List[Tuple[List[int], List[int]]] = []
    for key in sets_in_order:
        val_idx = indices_by_set[key]
        val_set = set(val_idx)
        train_idx = [i for i in all_indices if i not in val_set]
        folds.append((train_idx, val_idx))
    return folds


def grouped_kfold_by_set(
    records: Sequence[Mapping[str, Any]], k: int, set_key: str = "set_id", seed: int = 0
) -> List[Tuple[List[int], List[int]]]:
    """K-fold CV where whole sets (never individual cards) are assigned to folds.
    Sets are shuffled deterministically (seeded) before being distributed round-
    robin across the k folds, so fold sizes stay balanced without ever splitting
    a set's cards across folds.
    """
    if k < 2:
        raise ValueError("k must be >= 2 for grouped K-fold.")
    sets_in_order: List[Any] = []
    seen = set()
    indices_by_set: Dict[Any, List[int]] = {}
    for i, row in enumerate(records):
        key = row.get(set_key)
        if key not in seen:
            seen.add(key)
            sets_in_order.append(key)
        indices_by_set.setdefault(key, []).append(i)

    rng = random.Random(seed)
    shuffled_sets = list(sets_in_order)
    rng.shuffle(shuffled_sets)

    fold_of_set: Dict[Any, int] = {}
    for i, key in enumerate(shuffled_sets):
        fold_of_set[key] = i % k

    all_indices = list(range(len(records)))
    folds: List[Tuple[List[int], List[int]]] = []
    for fold_id in range(k):
        val_idx = [i for i in all_indices if fold_of_set[records[i].get(set_key)] == fold_id]
        train_idx = [i for i in all_indices if fold_of_set[records[i].get(set_key)] != fold_id]
        if val_idx:
            folds.append((train_idx, val_idx))
    return folds


def era_held_out_folds(
    records: Sequence[Mapping[str, Any]], era_key: str = "era"
) -> List[Tuple[List[int], List[int]]]:
    """One fold per distinct era: that era's rows are held out entirely. This is a
    stricter, more informative robustness check than set-level CV -- it asks
    whether a model trained on other eras generalizes to an unseen release period,
    not just an unseen set within the same era.
    """
    eras_in_order: List[Any] = []
    seen = set()
    indices_by_era: Dict[Any, List[int]] = {}
    for i, row in enumerate(records):
        key = row.get(era_key)
        if key not in seen:
            seen.add(key)
            eras_in_order.append(key)
        indices_by_era.setdefault(key, []).append(i)

    all_indices = list(range(len(records)))
    folds: List[Tuple[List[int], List[int]]] = []
    for key in eras_in_order:
        val_idx = indices_by_era[key]
        val_set = set(val_idx)
        train_idx = [i for i in all_indices if i not in val_set]
        folds.append((train_idx, val_idx))
    return folds


def assert_no_set_leakage(records: Sequence[Mapping[str, Any]], fold: Tuple[List[int], List[int]], set_key: str = "set_id") -> None:
    """Guard: proves a given (train, val) fold never lets the same set appear on
    both sides."""
    train_idx, val_idx = fold
    train_sets = {records[i].get(set_key) for i in train_idx}
    val_sets = {records[i].get(set_key) for i in val_idx}
    overlap = train_sets & val_sets
    if overlap:
        raise ValueError(f"Set leakage across fold: {overlap} appear in both train and validation.")
