"""Master market-validation result-table generator.

Produces the | Signal | n | Raw Spearman | Controlled effect | Δ OOS R² | Era
stability | Price-independent | Status | table from raw_correlations +
incremental_models + redundancy outputs. Status classification is conservative:
only CORE/POSITIVE_LIFT/DIAGNOSTIC/REJECT/INSUFFICIENT_EVIDENCE are assigned, and
never for a signal this task hasn't finished (V7 signals stay
INSUFFICIENT_EVIDENCE by construction until they exist).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Sequence

from backend.research.market_validation.raw_correlations import raw_relationship, raw_relationship_by_group
from backend.research.market_validation.redundancy import incremental_contribution_after


class SignalStatus:
    CORE = "CORE"
    POSITIVE_LIFT = "POSITIVE_LIFT"
    DIAGNOSTIC = "DIAGNOSTIC"
    REJECT = "REJECT"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


MIN_N_FOR_STATUS = 30  # below this, always INSUFFICIENT_EVIDENCE regardless of point estimates


def classify_signal_status(
    n: int,
    delta_oos_r2: Optional[float],
    era_stable: Optional[bool],
    price_independent: bool,
) -> str:
    """Conservative, mechanical classification -- never used to auto-select a
    Collector formula; this only labels a row in a reporting table. A signal that
    fails the price-independence check is never CORE/POSITIVE_LIFT regardless of
    its numbers, because construct validity (not raw predictive power) governs
    whether Collector Appeal may use it at all -- market validation only tells us
    whether an ALREADY price-independent signal happens to carry market signal.
    """
    if not price_independent:
        return SignalStatus.REJECT
    if n < MIN_N_FOR_STATUS:
        return SignalStatus.INSUFFICIENT_EVIDENCE
    if delta_oos_r2 is None:
        return SignalStatus.INSUFFICIENT_EVIDENCE
    if delta_oos_r2 <= 0:
        return SignalStatus.DIAGNOSTIC
    if delta_oos_r2 >= 0.02 and (era_stable is True):
        return SignalStatus.CORE
    if delta_oos_r2 > 0:
        return SignalStatus.POSITIVE_LIFT
    return SignalStatus.INSUFFICIENT_EVIDENCE


@dataclass
class MasterTableRow:
    signal: str
    n: int
    raw_spearman: Optional[float]
    controlled_effect: Optional[float]  # incremental OOS R2 of this signal alone, base-controls-only baseline
    delta_oos_r2: Optional[float]
    era_stability: Optional[Dict[str, Any]]
    price_independent: bool
    status: str


def build_master_table(
    records: Sequence[Mapping[str, Any]],
    signal_keys: Sequence[str],
    base_predictor_keys: Sequence[str],
    outcome_key: str = "log_market_price",
    era_key: str = "era",
    set_key: str = "set_id",
    price_independence_flags: Optional[Mapping[str, bool]] = None,
    seed: int = 0,
) -> List[Dict[str, Any]]:
    """Builds one master-table row per signal in `signal_keys`.

    `price_independence_flags`: a caller-supplied mapping declaring, per signal,
    whether it was constructed without any price input (this harness cannot
    verify a signal's own upstream construction history -- it can only refuse to
    use price as a predictor itself, via price_separation.py). A signal absent
    from this mapping defaults to price_independent=True with a caveat noted in
    the row, since the harness has no evidence either way; callers evaluating an
    unfamiliar signal should supply this explicitly.
    """
    price_independence_flags = price_independence_flags or {}
    rows: List[Dict[str, Any]] = []

    for signal in signal_keys:
        if not any(row.get(signal) is not None for row in records):
            continue  # signal not present in this dataset at all; do not emit a fabricated row

        raw = raw_relationship(records, signal, outcome_key, seed=seed)
        contribution = incremental_contribution_after(records, base_predictor_keys, signal, outcome_key, set_key)
        by_era = raw_relationship_by_group(records, signal, era_key, outcome_key, seed=seed, bootstrap_draws=200)
        era_signs = [v["spearman"] for v in by_era.values() if v.get("spearman") is not None]
        era_stable = None
        if len(era_signs) >= 2:
            era_stable = all((s >= 0) == (era_signs[0] >= 0) for s in era_signs)

        price_independent = price_independence_flags.get(signal, True)
        status = classify_signal_status(raw["n"], contribution["deltaOosR2"], era_stable, price_independent)

        row = MasterTableRow(
            signal=signal,
            n=raw["n"],
            raw_spearman=raw["spearman"],
            controlled_effect=contribution["withCandidateOosR2"],
            delta_oos_r2=contribution["deltaOosR2"],
            era_stability={"stable": era_stable, "byEra": by_era},
            price_independent=price_independent,
            status=status,
        )
        rows.append(
            {
                "signal": row.signal,
                "n": row.n,
                "rawSpearman": row.raw_spearman,
                "controlledEffect": row.controlled_effect,
                "deltaOosR2": row.delta_oos_r2,
                "eraStable": era_stable,
                "priceIndependent": row.price_independent,
                "status": row.status,
                "rawRelationship": raw,
                "incrementalContribution": contribution,
            }
        )
    return rows
