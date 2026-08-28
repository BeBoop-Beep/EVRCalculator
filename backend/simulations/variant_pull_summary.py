"""Lightweight exact-card-variant observation for production V2 simulations.

The recorder implements the same tiny observer surface as the research CSR
recorder, but retains only run-level copy and pack-presence counters.  It never
draws randomness and never participates in a sampling decision.
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Dict, Optional, Sequence, Tuple

import numpy as np
import pandas as pd


BASE_PRICE_COLUMN = "Price ($)"
REVERSE_PRICE_COLUMN = "Reverse Variant Price ($)"
MODEL_SOURCE = "monte_carlo_exact_variant_frequency_v1"
MODEL_VERSION = "exact_variant_pull_frequency_v1"


def _text(value: Any) -> Optional[str]:
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    return text or None


class VariantPullSummaryRecorder:
    """Count exact variant copies and pack presence with O(variant-count) memory."""

    def __init__(self, source_df: pd.DataFrame) -> None:
        self._rows: Dict[int, Dict[str, Any]] = {}
        for position, (row_index, row) in enumerate(source_df.iterrows()):
            source = row.get("__source_row_index__", row_index)
            if source is not None and not pd.isna(source):
                self._rows[int(source)] = row.to_dict()
        self._entity_index: Dict[Tuple[Optional[int], str], int] = {}
        self._entity_variants: list[Optional[str]] = []
        self._variant_metadata: Dict[str, Dict[str, Any]] = {}
        self._copy_counts: Counter[str] = Counter()
        self._presence_counts: Counter[str] = Counter()
        self._pack_variants: set[str] = set()
        self._pack_open = False
        self._pack_count = 0

    def _metadata(self, source: Optional[int], price_column: str, price: float) -> Dict[str, Any]:
        row = self._rows.get(int(source)) if source is not None else None
        row = row or {}
        reverse = price_column == REVERSE_PRICE_COLUMN
        variant_id = _text(row.get("reverse_variant_id" if reverse else "card_variant_id"))
        return {
            "cardId": _text(row.get("card_id")),
            "cardVariantId": variant_id,
            "conditionId": _text(row.get("reverse_condition_id" if reverse else "condition_id")),
            "printingType": _text(row.get("reverse_printing_type" if reverse else "printing_type")),
            "specialType": _text(row.get("Special Type") or row.get("special_type")),
            "priceUsed": float(price),
            "priceSource": _text(row.get("reverse_price_source" if reverse else "price_source")),
            "priceCapturedAt": _text(row.get("reverse_captured_at" if reverse else "captured_at")),
            "modelSource": MODEL_SOURCE,
            "modelVersion": MODEL_VERSION,
        }

    def _register(self, source: Optional[int], price_column: str, price: float) -> int:
        key = (source, price_column)
        existing = self._entity_index.get(key)
        if existing is not None:
            return existing
        entity_id = len(self._entity_variants)
        metadata = self._metadata(source, price_column, price)
        variant_id = metadata.get("cardVariantId")
        self._entity_index[key] = entity_id
        self._entity_variants.append(variant_id)
        if variant_id:
            self._variant_metadata.setdefault(variant_id, metadata)
        return entity_id

    def register_pool(self, *, price_column: str, prices: np.ndarray,
                      source_row_indices: Optional[np.ndarray], **_kwargs: Any) -> np.ndarray:
        ids = np.empty(int(prices.size), dtype=np.int32)
        for position in range(int(prices.size)):
            raw = None if source_row_indices is None else source_row_indices[position]
            source = None if raw is None else int(raw)
            ids[position] = self._register(source, price_column, float(prices[position]))
        return ids

    def register_row(self, *, source_row_index: Optional[int], price_column: str,
                     price: float, **_kwargs: Any) -> int:
        source = None if source_row_index is None else int(source_row_index)
        return self._register(source, price_column, float(price))

    def open_pack(self) -> None:
        self._pack_open = True
        self._pack_variants.clear()

    def add(self, entity_ids: np.ndarray | Sequence[int] | int) -> None:
        for raw_id in np.atleast_1d(np.asarray(entity_ids, dtype=np.int32)):
            variant_id = self._entity_variants[int(raw_id)]
            if variant_id:
                self._copy_counts[variant_id] += 1
                self._pack_variants.add(variant_id)

    def close_pack(self) -> None:
        self._presence_counts.update(self._pack_variants)
        self._pack_count += 1
        self._pack_open = False

    def finalize(self) -> list[dict[str, Any]]:
        if self._pack_open:
            raise RuntimeError("variant summary finalized with a pack still open")
        rows = []
        for variant_id, metadata in self._variant_metadata.items():
            presence = int(self._presence_counts[variant_id])
            probability = presence / self._pack_count if presence and self._pack_count else None
            rows.append({
                **metadata,
                "pullCount": int(self._copy_counts[variant_id]),
                "packPresenceCount": presence,
                "simulationCount": self._pack_count,
                "modeledProbability": probability,
                "effectivePullRate": (1.0 / probability) if probability else None,
                "status": "modeled" if probability else "insufficient_observed_pulls",
            })
        return rows
