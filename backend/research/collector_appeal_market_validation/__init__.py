"""Collector Appeal market-validation research harness (never production scoring)."""

from .stats import (
    ComponentSpec,
    DEFAULT_CONTROLS,
    compare_components,
    descriptive_relationships,
    grouped_leave_set_out_cv,
    incremental_lift,
    prediction_metrics,
    run_component_suite,
)

__all__ = [
    "ComponentSpec",
    "DEFAULT_CONTROLS",
    "compare_components",
    "descriptive_relationships",
    "grouped_leave_set_out_cv",
    "incremental_lift",
    "prediction_metrics",
    "run_component_suite",
]
