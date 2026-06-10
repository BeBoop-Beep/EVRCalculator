from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Dict, Optional

import pandas as pd

from backend.calculations.utils.rarity_classification import (
    is_excluded_from_chase_metrics,
    is_hit_rarity,
    normalize_rarity_key,
)


def _coerce_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if pd.isna(parsed):
        return None
    return parsed


def _coerce_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _first_present(row: Mapping[str, Any], *field_names: str) -> Any:
    for field_name in field_names:
        if field_name in row and row.get(field_name) not in (None, ""):
            return row.get(field_name)
    return None


def compute_hit_value_metrics(
    *,
    rarity_pull_counts: Mapping[str, Any],
    rarity_value_totals: Mapping[str, Any],
    packs_simulated: int,
    config: Any,
) -> Dict[str, Any]:
    """Compute hit-only realized value metrics from simulation rarity counters.

    The current simulation output tracks pulled card events by rarity, not exact
    per-pack hit membership for every engine path. Therefore ``hit_pull_rate`` is
    persisted as hit cards pulled per simulated pack. Pattern overlays are
    excluded from all hit-only totals.
    """
    hit_cards_pulled = 0
    total_hit_value = 0.0

    for rarity, raw_count in (rarity_pull_counts or {}).items():
        rarity_text = str(rarity or "").strip()
        if not rarity_text:
            continue
        if not is_hit_rarity(rarity_text, config):
            continue
        if is_excluded_from_chase_metrics(rarity_text, config):
            continue

        count = _coerce_int(raw_count)
        if count <= 0:
            continue

        total_value = _coerce_float((rarity_value_totals or {}).get(rarity))
        if total_value is None:
            total_value = 0.0

        hit_cards_pulled += count
        total_hit_value += float(total_value)

    average_hit_value = (total_hit_value / hit_cards_pulled) if hit_cards_pulled > 0 else None
    hit_ev_per_pack = (total_hit_value / packs_simulated) if packs_simulated > 0 else None
    hit_pull_rate = (hit_cards_pulled / packs_simulated) if packs_simulated > 0 else None

    return {
        "total_value_hit_cards_pulled": float(total_hit_value),
        "average_hit_value": average_hit_value,
        "hit_ev_per_pack": hit_ev_per_pack,
        "hit_pull_rate": hit_pull_rate,
        "hit_cards_pulled": int(hit_cards_pulled),
    }


def _row_pattern_rank(row: Mapping[str, Any]) -> int:
    special_type = str(_first_present(row, "Special Type", "special_type") or "")
    pattern_key = str(_first_present(row, "pattern_key") or normalize_rarity_key(special_type))
    if pattern_key in {"poke_ball_pattern", "pokeball_pattern", "master_ball_pattern", "masterball_pattern"}:
        return 1

    text_blob = " ".join(
        str(_first_present(row, field) or "")
        for field in ("printing_type", "printing", "edition", "variant")
    ).lower()
    if any(token in text_blob for token in ("reverse", "foil", "parallel", "stamped")):
        return 1
    return 0


def _fallback_unique_card_key(row: Mapping[str, Any], set_id: str) -> str:
    name = normalize_rarity_key(_first_present(row, "Card Name", "card_name") or "")
    number = normalize_rarity_key(_first_present(row, "Card Number", "card_number") or "")
    rarity = normalize_rarity_key(_first_present(row, "Rarity", "rarity", "rarity_raw") or "")
    return f"{set_id}:{number}:{name}:{rarity}"


def compute_simulated_set_value(
    dataframe: pd.DataFrame,
    *,
    config: Any,
    set_id: str,
) -> Dict[str, Any]:
    """Compute one-copy simulated set value from the priced simulation universe.

    This is the current "simulated set value" until a future canonical
    unique_cards table can provide checklist-perfect identity and pricing.
    Variant/pattern rows are collapsed by canonical card id when available.
    """
    _ = config
    if not isinstance(dataframe, pd.DataFrame) or dataframe.empty:
        return {"simulated_set_value": 0.0, "simulated_set_value_card_count": 0}

    rows_by_identity: Dict[str, tuple[int, float]] = {}

    for row in dataframe.to_dict(orient="records"):
        price = _coerce_float(
            _first_present(row, "base_price", "Price ($)", "market_price", "price_used")
        )
        if price is None:
            continue

        identity = _first_present(row, "canonical_card_id", "card_id")
        if identity is None:
            identity = _fallback_unique_card_key(row, set_id)
        identity_key = str(identity).strip()
        if not identity_key:
            identity_key = _fallback_unique_card_key(row, set_id)

        rank = _row_pattern_rank(row)
        previous = rows_by_identity.get(identity_key)
        if previous is None or rank < previous[0]:
            rows_by_identity[identity_key] = (rank, float(price))

    return {
        "simulated_set_value": float(sum(price for _, price in rows_by_identity.values())),
        "simulated_set_value_card_count": int(len(rows_by_identity)),
    }
