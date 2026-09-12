"""Card-level and set-level research dataset contracts.

These are plain dict-shaped contracts (documented via TypedDict), not ORM models --
the harness never reads a database directly; callers assemble rows from whatever
source-of-truth is current (Collector persistence tables, snapshot artifacts,
market-price tables) and pass them in. Fields for signals that do not exist yet
(Artist, Treatment, Scarcity) are declared as Optional so the schema is stable
across V6 -> V7 without a breaking change, and every field that must never be
touched by Collector-construction logic is called out in price_separation.py.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, TypedDict


class CardLevelRecord(TypedDict, total=False):
    # --- identity ---
    canonical_card_id: str
    pokemon_tcg_api_card_id: str
    set_id: str
    set_canonical_key: str
    canonical_subject_identity: Optional[str]  # e.g. "Charizard", "Iono"
    supertype: str  # Pokemon | Trainer | Energy

    # --- outcome (PRICE IS OUTCOME ONLY -- see price_separation.py) ---
    market_price: Optional[float]
    log_market_price: Optional[float]
    market_price_rank_in_universe: Optional[float]
    price_universe_key: Optional[str]  # what rank denominator this rank is computed within

    # --- structural controls (never price-derived) ---
    rarity: Optional[str]
    era: Optional[str]
    release_age_days: Optional[int]
    promo_status: Optional[str]
    variant_identity: Optional[str]  # printing/treatment identity, distinct from Treatment Prestige score

    # --- Collector subcomponents (predictors, kept separate, never pre-combined) ---
    pokemon_subject_appeal: Optional[float]
    trainer_appeal: Optional[float]
    playability_raw_score: Optional[float]
    playability_applied_lift: Optional[float]
    artist_recognition_score: Optional[float]  # None until Artist exists (V7+)
    treatment_prestige_score: Optional[float]  # None until Treatment exists (V7+)
    pull_scarcity_score: Optional[float]  # None until modeled Scarcity exists (V7+)
    final_card_collector_appeal: Optional[float]

    # --- lineage (which model produced the predictors above) ---
    collector_model_version: str
    collector_model_run_id: str


class SetLevelRecord(TypedDict, total=False):
    # --- identity ---
    set_id: str
    set_canonical_key: str
    set_name: str
    era: Optional[str]
    canonical_root_set_id: Optional[str]  # if this set is a subset, points at its canonical root
    is_canonical_root: bool  # False for a subset folded into a root's market universe

    # --- outcome ---
    canonical_set_value: Optional[float]
    top10_value: Optional[float]
    other_market_aggregate: Optional[Dict[str, float]]

    # --- Collector components (kept separate, per component) ---
    d_pokemon: Optional[float]
    d_trainer: Optional[float]
    trainer_lift_points: Optional[float]
    functional_diagnostic: Optional[float]  # never enters D; diagnostic only
    d_final: Optional[float]
    generalized_f: Optional[float]
    final_collector_appeal: Optional[float]
    artist_contribution: Optional[float]  # None until V7
    treatment_contribution: Optional[float]  # None until V7
    scarcity_diagnostic: Optional[float]  # None until V7

    # --- diagnostics ---
    pokemon_group_count: Optional[int]
    pokemon_strength: Optional[float]
    pokemon_breadth: Optional[float]

    # --- lineage ---
    collector_model_version: str
    collector_model_run_id: str


PRICE_FIELDS = {"market_price", "log_market_price", "market_price_rank_in_universe"}
SET_PRICE_FIELDS = {"canonical_set_value", "top10_value", "other_market_aggregate"}


def validate_card_records(records: List[Dict[str, Any]]) -> List[str]:
    """Structural validation only (required identity fields present, no duplicate
    canonical_card_id, log_market_price consistent with market_price where both are
    present). Returns a list of problem descriptions; empty list means the dataset
    is structurally sound. Does not validate business/statistical properties."""
    problems: List[str] = []
    seen_ids = set()
    for i, row in enumerate(records):
        cid = row.get("canonical_card_id")
        if not cid:
            problems.append(f"row {i}: missing canonical_card_id")
            continue
        if cid in seen_ids:
            problems.append(f"row {i}: duplicate canonical_card_id {cid!r}")
        seen_ids.add(cid)
        price = row.get("market_price")
        log_price = row.get("log_market_price")
        if price is not None and log_price is not None:
            import math

            if price > 0 and abs(math.log(price) - log_price) > 1e-6:
                problems.append(f"row {i} ({cid}): log_market_price inconsistent with market_price")
    return problems


def validate_set_records(records: List[Dict[str, Any]]) -> List[str]:
    """Structural validation: unique set_id, and no subset double-counted as an
    independent market alongside its own canonical root (is_canonical_root=False
    rows must declare canonical_root_set_id, and that root should also appear in
    the dataset or be explicitly noted absent by the caller)."""
    problems: List[str] = []
    seen_ids = set()
    ids_present = {row.get("set_id") for row in records}
    for i, row in enumerate(records):
        sid = row.get("set_id")
        if not sid:
            problems.append(f"row {i}: missing set_id")
            continue
        if sid in seen_ids:
            problems.append(f"row {i}: duplicate set_id {sid!r}")
        seen_ids.add(sid)
        if row.get("is_canonical_root") is False and not row.get("canonical_root_set_id"):
            problems.append(f"row {i} ({sid}): subset must declare canonical_root_set_id")
        root = row.get("canonical_root_set_id")
        if root and root not in ids_present and root != sid:
            problems.append(f"row {i} ({sid}): canonical_root_set_id {root!r} not present in dataset (informational)")
    return problems
