"""The strict price-separation contract: PRICE IS OUTCOME ONLY.

Price (market_price, log_market_price, market_price_rank_in_universe,
canonical_set_value, top10_value, other_market_aggregate) may appear ONLY as a
dependent/outcome variable inside this harness's model-evaluation functions
(incremental_models.py, raw_correlations.py). It must never appear inside:

  - Collector component construction (Subject Appeal, Playability, D, F, ...)
  - normalization / thresholds / weight selection for any Collector component
  - candidate/formula selection for any Collector research pass
  - missing-value imputation for any Collector component

This module provides a runtime guard other harness code calls to prove it never
crosses that line, plus a config-auditing helper for scoring code elsewhere in the
repo (Collector builders) to self-certify against.
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping

from backend.research.market_validation.schema import PRICE_FIELDS, SET_PRICE_FIELDS

ALL_PRICE_FIELDS = PRICE_FIELDS | SET_PRICE_FIELDS


class PriceContaminationError(ValueError):
    """Raised when a price field is detected inside a predictor/config context."""


def assert_no_price_in_predictor_keys(predictor_keys: Iterable[str]) -> None:
    """Call this wherever a harness function accepts a list of predictor/feature
    names for MODEL CONSTRUCTION (not evaluation) -- e.g. before building an
    incremental model's design matrix from anything that isn't the outcome slot.
    """
    offending = sorted(set(predictor_keys) & ALL_PRICE_FIELDS)
    if offending:
        raise PriceContaminationError(
            f"Price field(s) {offending} found among predictor keys. Price is "
            "outcome-only in this harness; it may never be used as a predictor, "
            "control, or construction input for a Collector component."
        )


def assert_scoring_config_price_free(scoring_config: Mapping[str, Any], context: str = "") -> None:
    """Audits a Collector scoring_config_json-shaped mapping for any price-shaped
    key or nested value. This is the same style of self-certification the frozen
    V6 model already carries (price_policy='excluded' on the model-run row) --
    this helper lets other harness/research code assert that programmatically
    rather than trusting a label.
    """
    forbidden_substrings = ("price", "market_value", "set_value")

    def _walk(node: Any, path: str) -> None:
        if isinstance(node, Mapping):
            for key, value in node.items():
                key_lower = str(key).lower()
                if any(s in key_lower for s in forbidden_substrings) and key_lower not in {
                    "price_policy",  # the existing, legitimate self-declaration field (holds "excluded")
                }:
                    raise PriceContaminationError(
                        f"{context}: scoring_config key {path}.{key!r} looks price-shaped."
                    )
                _walk(value, f"{path}.{key}")
        elif isinstance(node, (list, tuple)):
            for i, item in enumerate(node):
                _walk(item, f"{path}[{i}]")

    _walk(scoring_config, "scoring_config")


def strip_price_fields(record: Mapping[str, Any]) -> dict:
    """Return a copy of a card/set record with every price-outcome field removed --
    the defensive default for any function that builds a predictor design matrix,
    so a caller cannot accidentally pass outcome fields through as features even if
    they forget to call assert_no_price_in_predictor_keys explicitly."""
    return {k: v for k, v in record.items() if k not in ALL_PRICE_FIELDS}
