"""Raw relationship metrics: signal vs. outcome, with coverage/breakdown reporting.

Built on backend.research.validation_stats (existing, reused, not reimplemented) --
this module adds the market-validation-specific framing (era/rarity breakdowns,
coverage/missingness accounting) on top of those primitives. A high raw correlation
here is NOT proof of independent collector signal -- see incremental_models.py and
redundancy.py for the controlled/incremental tests that actually test that.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Mapping, Optional, Sequence

from backend.research.validation_stats import (
    bootstrap_correlation_ci,
    paired,
    pearson,
    spearman,
)


def raw_relationship(
    records: Sequence[Mapping[str, Any]],
    signal_key: str,
    outcome_key: str = "log_market_price",
    seed: int = 0,
    bootstrap_draws: int = 1000,
) -> Dict[str, Any]:
    """One signal vs. one outcome: n, Spearman, Pearson, bootstrap CI, coverage."""
    total = len(records)
    xs, ys = paired(records, signal_key, outcome_key)
    n = len(xs)
    result: Dict[str, Any] = {
        "signal": signal_key,
        "outcome": outcome_key,
        "n": n,
        "totalRows": total,
        "coverage": (n / total) if total else None,
        "missingness": 1.0 - (n / total) if total else None,
        "spearman": None,
        "pearson": None,
        "spearmanCi": None,
        "pearsonCi": None,
    }
    if n < 3:
        result["note"] = "n<3, correlation not computed"
        return result
    result["spearman"] = spearman(xs, ys)
    result["pearson"] = pearson(xs, ys)
    result["spearmanCi"] = bootstrap_correlation_ci(xs, ys, method="spearman", seed=seed, draws=bootstrap_draws)
    result["pearsonCi"] = bootstrap_correlation_ci(xs, ys, method="pearson", seed=seed, draws=bootstrap_draws)
    return result


def raw_relationship_by_group(
    records: Sequence[Mapping[str, Any]],
    signal_key: str,
    group_key: str,
    outcome_key: str = "log_market_price",
    seed: int = 0,
    bootstrap_draws: int = 300,
) -> Dict[str, Dict[str, Any]]:
    """Era/rarity breakdown: raw_relationship() computed separately within each
    distinct value of group_key (e.g. era, rarity). Smaller bootstrap_draws default
    since this typically runs once per group and groups are usually small."""
    groups: Dict[Optional[str], List[Mapping[str, Any]]] = {}
    for row in records:
        groups.setdefault(row.get(group_key), []).append(row)
    return {
        str(group): raw_relationship(rows, signal_key, outcome_key, seed=seed, bootstrap_draws=bootstrap_draws)
        for group, rows in groups.items()
    }


def coverage_report(records: Sequence[Mapping[str, Any]], signal_keys: Sequence[str]) -> Dict[str, Dict[str, Any]]:
    """Per-signal coverage/missingness across the whole dataset, independent of any
    particular outcome -- useful for the Phase-11-style source-quality gate before
    a signal is even considered for the incremental-model framework."""
    total = len(records)
    report: Dict[str, Dict[str, Any]] = {}
    for key in signal_keys:
        present = sum(1 for row in records if _finite(row.get(key)) is not None)
        report[key] = {
            "n": present,
            "total": total,
            "coverage": (present / total) if total else None,
            "missingness": 1.0 - (present / total) if total else None,
        }
    return report


def _finite(value: Any) -> Optional[float]:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None
