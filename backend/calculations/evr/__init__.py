"""EVR derived metrics layer.

This package exposes the derived decision-metrics layer that transforms
simulation output into user-facing product intelligence.

Primary entry point: derived_metrics.compute_all_derived_metrics
"""

from .derived_metrics import (
    compute_pack_decision_metrics,
    compute_chase_dependency_metrics,
    compute_pack_scores_for_set_records,
    compute_all_derived_metrics,
    simulate_session,
    derive_session_metrics,
    simulate_packs_until_hit,
    derive_packs_to_hit_metrics,
    PackSimulationSummary,
    build_pack_simulation_summary,
    print_derived_metrics_summary,
)
from .hit_value_metrics import compute_hit_value_metrics, compute_simulated_set_value

__all__ = [
    "compute_pack_decision_metrics",
    "compute_chase_dependency_metrics",
    "compute_pack_scores_for_set_records",
    "compute_all_derived_metrics",
    "simulate_session",
    "derive_session_metrics",
    "simulate_packs_until_hit",
    "derive_packs_to_hit_metrics",
    "PackSimulationSummary",
    "build_pack_simulation_summary",
    "print_derived_metrics_summary",
    "compute_hit_value_metrics",
    "compute_simulated_set_value",
]
