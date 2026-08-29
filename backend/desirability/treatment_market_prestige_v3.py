"""Research-only helpers for Treatment Market Prestige V3.

V3 estimates observational market associations for decomposed treatment
components.  It deliberately does not remove Exact Pull Scarcity and exposes
no production score or resolver.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from typing import Any, Iterable, Mapping, Sequence

import numpy as np

METHODOLOGY_VERSION = "treatment_market_prestige_v3_round1"
TAXONOMY_VERSION = "pokemon_card_treatment_taxonomy_v3_decomposed"
SEED = 20260829

TREATMENT_COMPONENT_CLASSIFICATION = {
    "rarity_designation": {"class": "A", "role": "treatment_component"},
    "printing_finish": {"class": "A", "role": "treatment_component"},
    "special_treatment": {"class": "A", "role": "treatment_component"},
    "edition_status": {"class": "A", "role": "treatment_component"},
    "mechanic_or_card_form": {"class": "B", "role": "control"},
    "pokemon_identity_or_demand": {"class": "B", "role": "control"},
    "set": {"class": "B", "role": "control"},
    "promo_status": {
        "class": "C", "role": "excluded_ambiguous",
        "reason": "Promo can denote distribution channel, set membership, or rarity rather than a consistent physical treatment.",
    },
}


def normalize_label(value: Any) -> str | None:
    """Normalize an observed label without inventing an unknown taxonomy."""
    if value is None:
        return None
    text = re.sub(r"[^a-z0-9]+", "_", str(value).strip().lower()).strip("_")
    return text or None


def mechanic_flags(subtypes: Iterable[Any]) -> tuple[str, ...]:
    """Return explicit form/mechanic controls; these never enter contribution."""
    supported = {
        "ex", "gx", "v", "vmax", "vstar", "mega", "break", "level_up",
        "radiant", "tag_team", "restored", "stage_1", "stage_2", "basic",
        "supporter", "item", "stadium", "pokemon_tool", "ace_spec",
    }
    values = {normalize_label(value) for value in (subtypes or [])}
    return tuple(sorted(value for value in values if value in supported))


def stable_json_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def positive_log(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return math.log(number) if math.isfinite(number) and number > 0 else None


def category_counts(rows: Sequence[Mapping[str, Any]], field: str) -> list[dict[str, Any]]:
    groups: dict[str, list[Mapping[str, Any]]] = {}
    for row in rows:
        groups.setdefault(str(row.get(field) or "__unmapped__"), []).append(row)
    return [
        {
            "value": value, "rows": len(group),
            "sets": len({row.get("set_id") for row in group}),
            "eras": len({row.get("era_id") for row in group}),
            "species": len({row.get("species_id") for row in group if row.get("species_id")}),
        }
        for value, group in sorted(groups.items(), key=lambda item: (-len(item[1]), item[0]))
    ]


def residualize_fixed_effects(
    matrix: np.ndarray, groups: Sequence[Sequence[Any]], *, tolerance: float = 1e-10, max_iter: int = 200
) -> np.ndarray:
    """Alternating projections for one or more categorical fixed effects."""
    result = np.asarray(matrix, dtype=float).copy()
    if result.ndim == 1:
        result = result[:, None]
    encoded = []
    for values in groups:
        _, inverse = np.unique(np.asarray(values, dtype=str), return_inverse=True)
        encoded.append(inverse)
    for _ in range(max_iter):
        before = result.copy()
        for inverse in encoded:
            counts = np.bincount(inverse).astype(float)
            for column in range(result.shape[1]):
                sums = np.bincount(inverse, weights=result[:, column])
                result[:, column] -= (sums / counts)[inverse]
        if np.max(np.abs(result - before)) < tolerance:
            break
    return result


def treatment_contribution(row: Mapping[str, Any], coefficients: Mapping[str, float]) -> float:
    """Sum only fitted treatment components; controls are intentionally absent."""
    total = 0.0
    for field in ("rarity_designation", "printing_finish", "special_treatment", "edition_status"):
        total += float(coefficients.get(f"{field}:{row.get(field) or '__none__'}", 0.0))
    return total


def centered_contributions(rows: Sequence[Mapping[str, Any]], coefficients: Mapping[str, float]) -> list[float]:
    """Center treatment-only log contributions within era for comparability."""
    raw = np.asarray([treatment_contribution(row, coefficients) for row in rows])
    result = raw.copy()
    by_era: dict[str, list[int]] = {}
    for index, row in enumerate(rows):
        by_era.setdefault(str(row.get("era_id")), []).append(index)
    for indexes in by_era.values():
        result[indexes] -= float(np.mean(raw[indexes]))
    return result.tolist()


def support_status(rows: Sequence[Mapping[str, Any]], field: str, *, min_rows: int = 25, min_sets: int = 2) -> dict[str, bool]:
    counts = Counter(str(row.get(field) or "__none__") for row in rows)
    sets: dict[str, set[Any]] = {}
    for row in rows:
        sets.setdefault(str(row.get(field) or "__none__"), set()).add(row.get("set_id"))
    return {key: count >= min_rows and len(sets[key]) >= min_sets for key, count in counts.items()}
