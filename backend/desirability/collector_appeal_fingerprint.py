"""Deterministic Collector Appeal formula fingerprint.

WHAT THIS IS FOR
----------------
A stored Collector Appeal score is only meaningful next to the assumptions that
produced it. Change the lambda, the accessibility anchors, the hit-eligibility
policy, or how a printed rarity resolves to a key, and the same inputs produce a
different number - while the stored row looks untouched. Staleness keyed on
``set_id`` + config + trend snapshots cannot see any of that: those keys describe
the DATA, and this describes the FORMULA.

The fingerprint is a SHA-256 over a canonical representation of every assumption
capable of changing a computed Collector Appeal result. A row whose fingerprint
differs from the current one was computed under different rules and is stale, no
matter how fresh its data is.

WHAT IS DELIBERATELY NOT IN IT
------------------------------
* **No git commit SHA.** Source-control identity is not scoring identity. A
  commit that edits a docstring would invalidate every row; a commit that edits a
  constant via config would not. The fingerprint is built from the scoring
  assumptions themselves, so it moves when and only when the mathematics moves.
  ``source_control_ref`` may be recorded ALONGSIDE the fingerprint as provenance,
  and is excluded from the hash.
* **No timestamps, paths, hostnames, environment or run IDs.** Those are volatile:
  including any of them would make every run produce a new fingerprint and mark
  every row permanently stale, which is the same as having no fingerprint at all.
* **No database access.** Fingerprinting reads module constants only. It must be
  callable in a unit test with no network and no credentials.
* **No price or market input**, consistent with the construct.

DETERMINISM
-----------
``canonical_representation`` sorts keys recursively and serializes with fixed
separators, so dict insertion order, input ordering and interpreter hash
randomization cannot move the hash. Floats are normalized via ``repr`` so 0.5 and
0.50 agree.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, Mapping, Optional

from backend.calculations.utils.rarity_classification import RARITY_NORMALIZATION_VERSION
from backend.desirability.collector_appeal import (
    CA7_FORMULA,
    CA7_FORMULA_VERSION,
    CA7_PRODUCTION_LAMBDA,
    COLLECTOR_APPEAL_VERSION,
    DUAL_PATH_DEPTH_VERSION,
    MISSING_DATA_POLICY,
    MISSING_DATA_POLICY_VERSION,
    ROUNDING_POLICY,
    ROUNDING_POLICY_VERSION,
)
from backend.desirability.composite import COMPOSITE_SCORING_VERSION
from backend.desirability.factorized_opening_appeal import D_FACTOR_VERSION
from backend.desirability.opening_appeal import (
    ACCESS_TRANSFORM_VERSION,
    DEMAND_BASELINE,
    EASY_PROBABILITY,
    ELITE_PROBABILITY,
    SCARCITY_TRANSFORM_VERSION,
)
from backend.desirability.product_support import PRODUCT_SUPPORT_VERSION
from backend.desirability.rankability import RANKABILITY_VERSION
from backend.desirability.rarity_buckets import HIT_BUCKETS, HIT_POLICY_VERSION
from backend.desirability.rarity_overrides import RARITY_OVERRIDE_VERSION
from backend.desirability.scoring_config import (
    UNIVERSAL_ELIGIBILITY_POLICY_VERSION,
    UNIVERSAL_SET_DESIRABILITY_VERSION,
)
from backend.desirability.set_components import SCORING_VERSION as SET_COMPONENTS_SCORING_VERSION

FINGERPRINT_SCHEMA_VERSION = "collector_appeal_fingerprint_v1"
FINGERPRINT_HASH_ALGORITHM = "sha256"

# Fingerprint status codes.
FINGERPRINT_CURRENT = "current"
FINGERPRINT_STALE = "stale"
FINGERPRINT_MISSING = "missing"


def collect_assumptions() -> Dict[str, Any]:
    """Every material assumption behind a Collector Appeal score.

    Read LIVE from the defining modules rather than duplicated here, so editing a
    constant at its source moves the fingerprint automatically. A parallel copy
    would drift and quietly certify stale rows as current.
    """
    return {
        "schema_version": FINGERPRINT_SCHEMA_VERSION,
        "formula": CA7_FORMULA,
        "formula_expression": "CA7 = D + lambda * P * (1 - D)",
        "formula_version": CA7_FORMULA_VERSION,
        "lambda": CA7_PRODUCTION_LAMBDA,
        "dependencies": {
            # --- the two constructs -------------------------------------
            "desirability_version": UNIVERSAL_SET_DESIRABILITY_VERSION,
            "desirability_eligibility_version": UNIVERSAL_ELIGIBILITY_POLICY_VERSION,
            "dual_path_version": DUAL_PATH_DEPTH_VERSION,
            "collector_appeal_module_version": COLLECTOR_APPEAL_VERSION,
            # --- transforms + their anchor constants ---------------------
            # Both the transform SHAPE and the anchor VALUES are included: a
            # recalibrated anchor changes every score without changing any
            # version string, so versions alone would not be sufficient.
            "access_transform_version": ACCESS_TRANSFORM_VERSION,
            "scarcity_transform_version": SCARCITY_TRANSFORM_VERSION,
            "easy_probability_anchor": EASY_PROBABILITY,
            "elite_probability_anchor": ELITE_PROBABILITY,
            "demand_baseline": DEMAND_BASELINE,
            # --- eligibility + rarity ------------------------------------
            "hit_eligibility_version": HIT_POLICY_VERSION,
            "hit_buckets": sorted(HIT_BUCKETS),
            "rarity_mapping_version": RARITY_NORMALIZATION_VERSION,
            "rarity_override_version": RARITY_OVERRIDE_VERSION,
            # --- subjects -------------------------------------------------
            "subject_demand_source_version": COMPOSITE_SCORING_VERSION,
            "subject_weighting_version": D_FACTOR_VERSION,
            # --- product policy -------------------------------------------
            "product_classifier_version": PRODUCT_SUPPORT_VERSION,
            "rankability_contract_version": RANKABILITY_VERSION,
            # set_components' SCORING_VERSION encodes the 40/25/20/15 component
            # weights, which include the special-pack chase-appeal policy.
            "set_components_version": SET_COMPONENTS_SCORING_VERSION,
            # --- policies -------------------------------------------------
            "missing_data_policy_version": MISSING_DATA_POLICY_VERSION,
            "missing_data_policy": dict(MISSING_DATA_POLICY),
            "rounding_policy_version": ROUNDING_POLICY_VERSION,
            "rounding_policy": dict(ROUNDING_POLICY),
        },
    }


def _canonicalize(value: Any) -> Any:
    """Recursively normalize into a deterministically comparable structure."""
    if isinstance(value, Mapping):
        return {str(key): _canonicalize(value[key]) for key in sorted(value, key=str)}
    if isinstance(value, (list, tuple)):
        # Order is preserved for sequences: it can be semantically meaningful
        # (slot weights). Callers that intend a SET must sort before passing.
        return [_canonicalize(item) for item in value]
    if isinstance(value, frozenset) or isinstance(value, set):
        return sorted(_canonicalize(item) for item in value)
    if isinstance(value, bool):
        return value
    if isinstance(value, float):
        # repr normalizes 0.50 -> '0.5', so an equivalent literal cannot fork the
        # hash, while a genuinely different value still does.
        return repr(float(value))
    return value


def canonical_representation(assumptions: Optional[Mapping[str, Any]] = None) -> str:
    """The exact string that gets hashed. Stable across runs and machines."""
    payload = _canonicalize(assumptions if assumptions is not None else collect_assumptions())
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def fingerprint_assumptions(assumptions: Optional[Mapping[str, Any]] = None) -> str:
    """SHA-256 of the canonical representation. No I/O, no clock, no environment."""
    digest = hashlib.sha256(canonical_representation(assumptions).encode("utf-8"))
    return digest.hexdigest()


def build_collector_appeal_identity(
    assumptions: Optional[Mapping[str, Any]] = None,
    *,
    source_control_ref: Optional[str] = None,
) -> Dict[str, Any]:
    """The human-readable metadata AND the hash, ready to store in diagnostics.

    ``source_control_ref`` is provenance only and is EXCLUDED from the hash - see
    the module docstring on why a commit SHA must not be the scoring identity.
    """
    resolved = dict(assumptions) if assumptions is not None else collect_assumptions()
    identity: Dict[str, Any] = {
        "formula": resolved["formula"],
        "lambda": resolved["lambda"],
        "formula_version": resolved["formula_version"],
        "formula_expression": resolved.get("formula_expression"),
        "fingerprint": fingerprint_assumptions(resolved),
        "fingerprint_algorithm": FINGERPRINT_HASH_ALGORITHM,
        "fingerprint_schema_version": resolved["schema_version"],
        "dependencies": dict(resolved["dependencies"]),
    }
    if source_control_ref:
        identity["source_control_ref"] = str(source_control_ref)
        identity["source_control_ref_note"] = (
            "Provenance only. Excluded from the fingerprint: source-control "
            "identity is not scoring identity."
        )
    return identity


def current_fingerprint() -> str:
    """The fingerprint of the assumptions this build would compute under."""
    return fingerprint_assumptions()


# ---------------------------------------------------------------------------
# Staleness
# ---------------------------------------------------------------------------

def read_row_fingerprint(row: Mapping[str, Any]) -> Optional[str]:
    """Pull a stored fingerprint out of a component row's diagnostics.

    Reads the nested ``diagnostics_json.collector_appeal.fingerprint`` shape.
    Returns None when absent - which is every production row today, since
    Collector Appeal has never been persisted.
    """
    diagnostics = row.get("diagnostics_json")
    if not isinstance(diagnostics, Mapping):
        return None
    block = diagnostics.get("collector_appeal")
    if not isinstance(block, Mapping):
        return None
    stored = block.get("fingerprint")
    return str(stored) if isinstance(stored, str) and stored else None


def fingerprint_status(row: Mapping[str, Any], *, expected: Optional[str] = None) -> str:
    """Classify one row as ``current`` / ``stale`` / ``missing``.

    ``missing`` and ``stale`` are kept distinct on purpose: "never computed" and
    "computed under different rules" are different facts and call for different
    responses. Collapsing them into one "needs rebuild" flag would hide the fact
    that a formula changed underneath existing rows.
    """
    stored = read_row_fingerprint(row)
    if stored is None:
        return FINGERPRINT_MISSING
    return FINGERPRINT_CURRENT if stored == (expected or current_fingerprint()) else FINGERPRINT_STALE


def is_row_stale(row: Mapping[str, Any], *, expected: Optional[str] = None) -> bool:
    """True when the row must be recomputed. Missing counts as stale."""
    return fingerprint_status(row, expected=expected) != FINGERPRINT_CURRENT
