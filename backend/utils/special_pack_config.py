from __future__ import annotations

from numbers import Integral
from typing import Iterator, Mapping, Tuple


WITH_REPLACEMENT = "with_replacement"
WITHOUT_REPLACEMENT = "without_replacement"


def parse_rarity_bucket_spec(qty_spec: object) -> Tuple[int, bool]:
    """Parse one rarity bucket spec into (count, use_replacement).

    Accepted config shapes:
    - int shorthand: 3
    - dict form: {"count": 3, "replacement": "with_replacement"|"without_replacement"}

    Returns:
        (count, use_replacement)
    """
    if isinstance(qty_spec, Integral):
        return int(qty_spec), True

    if not isinstance(qty_spec, dict):
        raise ValueError(
            f"Invalid rarity config format: {qty_spec}. "
            "Expected int or dict with 'count' and optional 'replacement' keys."
        )

    count = int(qty_spec.get("count", 1))
    replacement_mode = str(qty_spec.get("replacement", WITH_REPLACEMENT)).strip().lower()

    if replacement_mode not in {WITH_REPLACEMENT, WITHOUT_REPLACEMENT}:
        raise ValueError(
            f"Invalid replacement mode '{replacement_mode}'. "
            f"Expected '{WITH_REPLACEMENT}' or '{WITHOUT_REPLACEMENT}'."
        )

    return count, replacement_mode == WITH_REPLACEMENT


def iter_rarity_bucket_rules(rarity_rules: Mapping[str, object]) -> Iterator[Tuple[str, int, bool]]:
    """Yield normalized rarity bucket rules as (rarity, count, use_replacement)."""
    for rarity, qty_spec in rarity_rules.items():
        count, use_replacement = parse_rarity_bucket_spec(qty_spec)
        yield str(rarity), count, use_replacement
