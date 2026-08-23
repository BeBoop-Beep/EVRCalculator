"""Tier B: per-pack decomposition recording for the research re-simulation.

WHY THIS EXISTS
---------------
The authoritative simulation records value at RARITY grain
(``simulation_pull_summary``, which reconciles to the published mean exactly) but
not at CARD grain. The only per-card table in the database,
``simulation_input_cards.ev_contribution``, is the ANALYTIC model
``Price / Effective_Pull_Rate`` - measured at $5.80/pack against the simulator's
$8.53/pack on prismaticEvolutions, a 47% divergence. It is a different quantity,
not a lossy version of the same one, so Parts 6-7 cannot use it.

Nor may a card's contribution be reconstructed as ``P(card) * price``: the
simulator draws from a pack-state model with a bounded without-replacement
exclusion across the three variable slots, plus two special-pack entry paths.
Any closed form would be a SECOND model of the same thing, which is exactly what
the brief forbids. So the simulator is asked directly.

WHAT IS RECORDED, AND WHY IDS RATHER THAN VALUES
------------------------------------------------
Per pack, the recorder stores the ids of the sampling ENTITIES that were drawn -
never their prices. An entity is a ``(source_row_index, price_column)`` pair,
because one card is two economically distinct draws: it can be pulled from the
normal pools at ``Price ($)`` or from the reverse pool at
``Reverse Variant Price ($)``, and collapsing those would attribute reverse-slot
money to a card's normal printing.

Storing ids is what makes Parts 18 and 19 cheap AND exact::

    X'[p] = price'[ entities_drawn_in_pack_p ].sum()

A rarity ablation, a top-card ablation and a -25% chase shock are then each one
gather and one segmented sum over the SAME sampled paths that produced the
baseline. Every counterfactual is therefore perfectly paired with its baseline -
common random numbers - so the reported delta is the effect of the price change
and contains no resampling noise whatsoever. Re-simulating per scenario would
have buried a $0.05 ablation effect under $0.10 of Monte Carlo error.

STORAGE
-------
CSR-style: one flat ``int32`` entity buffer plus per-pack offsets. Normal packs
contribute a fixed number of draws (4 commons + 3 uncommons + 3 slots for a
Scarlet & Violet pack); special packs contribute a variable number, which is why
offsets are carried rather than assuming a rectangle. At 1,000,000 packs this is
roughly 40 MB, held in memory for the duration of one set's analysis and never
persisted at pack grain.

NOTHING HERE RUNS IN PRODUCTION
-------------------------------
``make_simulate_pack_fn_v2`` takes ``research_recorder=None`` by default and the
production caller never passes one. With ``None`` the sampling path and its RNG
consumption are bit-identical to today; ``test_recorder_does_not_perturb_sampling``
asserts that against a seeded run.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np

#: Rows appended to the flat buffer before it is grown. Growth doubles, so the
#: amortized cost is linear and the initial guess only affects small runs.
_INITIAL_FLAT_CAPACITY = 1 << 20

#: Packs per chunk when re-deriving pack values from a price vector. Bounds peak
#: memory during counterfactual evaluation independently of run size.
DEFAULT_REVALUATION_CHUNK = 100_000


@dataclass(frozen=True)
class SamplingEntity:
    """One distinct thing the simulator can draw and be paid for."""

    entity_id: int
    source_row_index: Optional[int]
    price_column: str
    price: float
    rarity_key: str
    card_name: Optional[str]
    card_number: Optional[str]

    def as_payload(self) -> Dict[str, Any]:
        return {
            "entityId": self.entity_id,
            "sourceRowIndex": self.source_row_index,
            "priceColumn": self.price_column,
            "price": self.price,
            "rarityKey": self.rarity_key,
            "cardName": self.card_name,
            "cardNumber": self.card_number,
        }


class PackDecompositionRecorder:
    """Collects, per pack, which sampling entities were drawn.

    Simulator-facing surface is deliberately tiny: ``register_pool`` once per
    pool at build time, ``open_pack`` / ``add`` / ``close_pack`` in the hot loop.
    The recorder knows nothing about pack states, slots, rarities-as-tokens or
    god-pack strategies, and must not learn.
    """

    def __init__(self, *, expected_packs: Optional[int] = None) -> None:
        self._entities: List[SamplingEntity] = []
        self._entity_index: Dict[Tuple[Optional[int], str], int] = {}
        capacity = _INITIAL_FLAT_CAPACITY
        if expected_packs:
            # 10 draws per Scarlet & Violet pack is the common case; overshooting
            # slightly is cheaper than several doublings of a 40 MB buffer.
            capacity = max(capacity, int(expected_packs) * 10)
        self._flat = np.empty(capacity, dtype=np.int32)
        self._flat_size = 0
        self._offsets: List[int] = [0]
        self._pack_open = False

    # -- build time ---------------------------------------------------------

    def register_pool(
        self,
        *,
        price_column: str,
        prices: np.ndarray,
        source_row_indices: Optional[np.ndarray],
        card_names: Optional[np.ndarray],
        rarities: Optional[np.ndarray],
        card_numbers: Optional[np.ndarray] = None,
    ) -> np.ndarray:
        """Map each pool position to a global entity id.

        Returns an ``int32`` array aligned with ``prices``, which the pool then
        carries so the hot loop can translate a sampled POSITION into an entity
        with one array lookup and no dict access.

        Pools overlap by construction - the same source row appears in the rare
        base pool and in a hit token pool - so an entity already seen is reused,
        which is what makes the resulting counts per-CARD rather than per-pool.
        """
        size = int(prices.size)
        ids = np.empty(size, dtype=np.int32)
        for position in range(size):
            raw_source = None if source_row_indices is None else source_row_indices[position]
            source = None if raw_source is None else int(raw_source)
            key = (source, price_column)
            existing = self._entity_index.get(key)
            if existing is None:
                existing = len(self._entities)
                self._entity_index[key] = existing
                self._entities.append(
                    SamplingEntity(
                        entity_id=existing,
                        source_row_index=source,
                        price_column=price_column,
                        price=float(prices[position]),
                        rarity_key=_text(rarities[position]) if rarities is not None else "unknown",
                        card_name=_optional_text(card_names[position]) if card_names is not None else None,
                        card_number=(
                            _optional_text(card_numbers[position]) if card_numbers is not None else None
                        ),
                    )
                )
            ids[position] = existing
        return ids

    def register_row(
        self,
        *,
        source_row_index: Optional[int],
        price_column: str,
        price: float,
        rarity_key: str,
        card_name: Optional[str] = None,
        card_number: Optional[str] = None,
    ) -> int:
        """Register (or look up) a single row not reached through a pool.

        The special-pack paths resolve rows straight off the source DataFrame
        rather than through an ``_ArrayPool``, so they register one row at a time.
        Special packs are ~0.2% of packs, so the dict lookup here never touches
        the hot path.
        """
        key = (None if source_row_index is None else int(source_row_index), price_column)
        existing = self._entity_index.get(key)
        if existing is not None:
            return existing
        entity_id = len(self._entities)
        self._entity_index[key] = entity_id
        self._entities.append(
            SamplingEntity(
                entity_id=entity_id,
                source_row_index=None if source_row_index is None else int(source_row_index),
                price_column=price_column,
                price=float(price),
                rarity_key=str(rarity_key),
                card_name=card_name,
                card_number=card_number,
            )
        )
        return entity_id

    # -- hot path -----------------------------------------------------------

    def open_pack(self) -> None:
        self._pack_open = True

    def add(self, entity_ids: np.ndarray | Sequence[int] | int) -> None:
        """Record one draw, or a block of draws, for the pack in progress."""
        block = np.atleast_1d(np.asarray(entity_ids, dtype=np.int32))
        needed = self._flat_size + block.size
        if needed > self._flat.size:
            grown = np.empty(max(needed, self._flat.size * 2), dtype=np.int32)
            grown[: self._flat_size] = self._flat[: self._flat_size]
            self._flat = grown
        self._flat[self._flat_size : needed] = block
        self._flat_size = needed

    def close_pack(self) -> None:
        self._offsets.append(self._flat_size)
        self._pack_open = False

    # -- results ------------------------------------------------------------

    @property
    def pack_count(self) -> int:
        return len(self._offsets) - 1

    @property
    def entities(self) -> Tuple[SamplingEntity, ...]:
        return tuple(self._entities)

    def finalize(self) -> "PackDecomposition":
        if self._pack_open:
            raise RuntimeError("recorder finalized with a pack still open")
        return PackDecomposition(
            entities=tuple(self._entities),
            flat=self._flat[: self._flat_size].copy(),
            offsets=np.asarray(self._offsets, dtype=np.int64),
        )


def _text(value: Any) -> str:
    return "unknown" if value is None else str(value)


def _optional_text(value: Any) -> Optional[str]:
    return None if value is None else str(value)


@dataclass(frozen=True)
class PackDecomposition:
    """A finished Tier B run: who was drawn, in which pack.

    This object is the whole reason Tier B exists. From it, without any further
    simulation:

      * expected copies per pack, per card      -> Part 6
      * EV contribution and share, per card     -> Parts 6, 7
      * the pack value vector under ANY price   -> Parts 18, 19
      * per-pack maximum single-card value      -> Part 10
      * per-pack rarity indicators              -> Part 9
    """

    entities: Tuple[SamplingEntity, ...]
    flat: np.ndarray
    offsets: np.ndarray

    @property
    def pack_count(self) -> int:
        return int(self.offsets.size - 1)

    @property
    def entity_count(self) -> int:
        return len(self.entities)

    def price_vector(self) -> np.ndarray:
        return np.array([entity.price for entity in self.entities], dtype=np.float64)

    def rarity_keys(self) -> np.ndarray:
        return np.array([entity.rarity_key for entity in self.entities], dtype=object)

    def pull_counts(self) -> np.ndarray:
        """Total times each entity was drawn across the whole run."""
        return np.bincount(self.flat, minlength=self.entity_count).astype(np.int64)

    def pack_lengths(self) -> np.ndarray:
        return np.diff(self.offsets)

    def pack_values(
        self,
        prices: Optional[np.ndarray] = None,
        *,
        chunk: int = DEFAULT_REVALUATION_CHUNK,
    ) -> np.ndarray:
        """Re-derive the per-pack total under an arbitrary price vector.

        ``prices=None`` reproduces the run's own outcome vector, which is the
        self-check the caller uses to prove the recorder saw every draw: the
        result must equal the simulator's returned values elementwise.

        Chunked over packs so peak memory is bounded by ``chunk`` rather than by
        the run size. ``np.bincount`` with weights is used instead of
        ``np.add.reduceat`` because reduceat mishandles zero-length groups, and a
        pack with no recorded draws is a real possibility (a fully $0 special
        pack) that must total 0.0 rather than silently inherit a neighbour.
        """
        values = prices if prices is not None else self.price_vector()
        values = np.asarray(values, dtype=np.float64)
        if values.size != self.entity_count:
            raise ValueError(
                f"price vector has {values.size} entries; run registered {self.entity_count} entities"
            )

        total_packs = self.pack_count
        out = np.zeros(total_packs, dtype=np.float64)
        lengths = self.pack_lengths()
        step = max(1, int(chunk))
        for start in range(0, total_packs, step):
            stop = min(start + step, total_packs)
            begin = int(self.offsets[start])
            end = int(self.offsets[stop])
            if end == begin:
                continue
            local = np.repeat(
                np.arange(stop - start, dtype=np.int64), lengths[start:stop]
            )
            out[start:stop] = np.bincount(
                local,
                weights=values[self.flat[begin:end]],
                minlength=stop - start,
            )
        return out

    def pack_max_entity_value(
        self,
        prices: Optional[np.ndarray] = None,
        *,
        chunk: int = DEFAULT_REVALUATION_CHUNK,
    ) -> np.ndarray:
        """Part 10: the most valuable SINGLE card in each pack.

        Distinct from the pack total: "did this pack contain a card worth at
        least the price of the pack" is not "was this pack worth its price".
        Four $4 commons are not a hit.
        """
        values = prices if prices is not None else self.price_vector()
        values = np.asarray(values, dtype=np.float64)
        total_packs = self.pack_count
        out = np.zeros(total_packs, dtype=np.float64)
        lengths = self.pack_lengths()
        step = max(1, int(chunk))
        for start in range(0, total_packs, step):
            stop = min(start + step, total_packs)
            begin = int(self.offsets[start])
            end = int(self.offsets[stop])
            if end == begin:
                continue
            local = np.repeat(
                np.arange(stop - start, dtype=np.int64), lengths[start:stop]
            )
            np.maximum.at(out[start:stop], local, values[self.flat[begin:end]])
        return out

    def pack_entity_presence(
        self,
        entity_mask: np.ndarray,
        *,
        chunk: int = DEFAULT_REVALUATION_CHUNK,
    ) -> np.ndarray:
        """Boolean per pack: did this pack contain ANY entity in ``entity_mask``?

        Part 9's collective hit frequency. Counted directly off the sampled
        paths, so mutually exclusive slot outcomes, the without-replacement
        exclusion and the special-pack entry paths are all honoured exactly -
        no summing of individual card odds, which would be wrong here because
        the events are not independent.
        """
        mask = np.asarray(entity_mask, dtype=bool)
        if mask.size != self.entity_count:
            raise ValueError("entity mask length must equal the registered entity count")
        total_packs = self.pack_count
        out = np.zeros(total_packs, dtype=bool)
        lengths = self.pack_lengths()
        step = max(1, int(chunk))
        for start in range(0, total_packs, step):
            stop = min(start + step, total_packs)
            begin = int(self.offsets[start])
            end = int(self.offsets[stop])
            if end == begin:
                continue
            local = np.repeat(
                np.arange(stop - start, dtype=np.int64), lengths[start:stop]
            )
            hit = mask[self.flat[begin:end]]
            if hit.any():
                np.logical_or.at(out[start:stop], local[hit], True)
        return out
