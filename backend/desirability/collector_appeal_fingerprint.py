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
* **No product name or product status.** ``metric_name`` and ``product_status``
  are recorded in the identity block but excluded from the hash: renaming a
  metric or promoting it out of ``internal_candidate`` does not change a single
  computed number, and hashing them would mark every row stale for a relabelling.

FORMULA IDENTITY IS NOT SOURCE IDENTITY
---------------------------------------
This hash answers "under what RULES was this computed?" It cannot answer "from
WHICH ROW?" - and conflating the two is how a diagnostics block certifying
``hit_policy_version = ..._v2_coverage_cleanup`` came to be proposed for rows
actually built under ``..._v1``. The certificate was true about the rules and
silent about the inputs, so nothing contradicted it.

The source identity is built separately, per row, by
``component_source.build_source_identity``, and an invariant asserts the selected
row's ACTUAL versions match the versions this fingerprint represents. Both are
stored. Neither is sufficient alone.

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
from backend.desirability.card_links import (
    CARD_DESIRABILITY_LINK_SOURCE_VERSION,
    CARD_LINK_AGGREGATION_POLICY_VERSION,
    CARD_SUBJECT_ASSEMBLY_VERSION,
)
from backend.desirability.collector_appeal import (
    CA7_FORMULA_VERSION,
    CA7_PRODUCTION_LAMBDA,
    COLLECTOR_APPEAL_CA7_VERSION,
    COLLECTOR_APPEAL_DIAGNOSTICS_KEY,
    COLLECTOR_APPEAL_DUAL_PATH_WEIGHT,
    COLLECTOR_APPEAL_FREQUENCY_WEIGHT,
    COLLECTOR_APPEAL_HEADROOM_GAIN,
    COLLECTOR_APPEAL_METRIC_NAME,
    COLLECTOR_APPEAL_PRODUCT_STATUS,
    COLLECTOR_APPEAL_V2_DIAGNOSTICS_KEY,
    COLLECTOR_APPEAL_V2_FORMULA_EXPRESSION,
    COLLECTOR_APPEAL_V2_FORMULA_VERSION,
    COLLECTOR_APPEAL_V2_VERSION,
    COLLECTOR_APPEAL_V3_DIAGNOSTICS_KEY,
    COLLECTOR_APPEAL_V3_FORMULA_VERSION,
    COLLECTOR_APPEAL_V3_VERSION,
    COLLECTOR_APPEAL_V3_WEIGHTS,
    DUAL_PATH_DEPTH_VERSION,
    MISSING_DATA_POLICY,
    MISSING_DATA_POLICY_VERSION,
    ROUNDING_POLICY,
    ROUNDING_POLICY_VERSION,
)
from backend.desirability.desirable_outcome_frequency import (
    DESIRABLE_OUTCOME_FREQUENCY_COVERAGE_POLICY_VERSION,
    DESIRABLE_OUTCOME_FREQUENCY_VERSION,
    MINIMUM_COVERED_DEMAND_SHARE,
)
from backend.desirability.component_source import (
    COMPONENT_SOURCE_CONTRACT_VERSION,
    EXPECTED_COMPOSITE_SCORING_VERSION,
    EXPECTED_HIT_POLICY_VERSION,
    EXPECTED_SCORING_VERSION,
)
from backend.desirability.composite import COMPOSITE_SCORING_VERSION
from backend.desirability.factorized_opening_appeal import (
    D_FACTOR_VERSION,
    SUBJECT_DEMAND_AGGREGATION_VERSION,
)
from backend.desirability.opening_appeal import (
    ACCESS_TRANSFORM_VERSION,
    DEMAND_BASELINE,
    EASY_PROBABILITY,
    ELITE_PROBABILITY,
    SCARCITY_TRANSFORM_VERSION,
    SUBJECT_CONSTRUCTION_VERSION,
)
from backend.desirability.pull_model import (
    PULL_MODEL_LOADER_VERSION,
    PULL_PROBABILITY_MAPPING_VERSION,
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

# SCHEMA v3. v1 assumed a function of D and P only (one `lambda`). v2 added the
# Desirable Outcome Frequency F alongside a headroom gain. The canonical formula
# is now a BALANCED WEIGHTED SUM of D, H and P with three independent weights and
# no headroom factor at all - a different shape again, with no slot in v2 for a
# desirability WEIGHT (v2's D was the base, not a weighted term). Bumping the
# schema is what makes every row computed under an older shape identifiably
# stale rather than merely differently-hashed.
FINGERPRINT_SCHEMA_VERSION = "collector_appeal_fingerprint_v3_balanced_d_h_p"
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
        # The CANONICAL formula, not a legacy one. A fingerprint that still named
        # V2 while the service computed the balanced sum would certify the wrong
        # mathematics, and nothing downstream could detect the discrepancy.
        "formula": "COLLECTOR_APPEAL_V3",
        "formula_version": COLLECTOR_APPEAL_V3_FORMULA_VERSION,
        "collector_appeal_version": COLLECTOR_APPEAL_V3_VERSION,
        # Every constant capable of moving the final score. Read from the
        # authoritative table so editing a weight at its source moves the hash.
        "weights": dict(COLLECTOR_APPEAL_V3_WEIGHTS),
        # The superseded identities, recorded so a stored row written under
        # either remains identifiable. Neither describes what is computed.
        "legacy_collector_appeal_v2": {
            "version": COLLECTOR_APPEAL_V2_VERSION,
            "formula_version": COLLECTOR_APPEAL_V2_FORMULA_VERSION,
            "formula_expression": COLLECTOR_APPEAL_V2_FORMULA_EXPRESSION,
            "frequency_weight": COLLECTOR_APPEAL_FREQUENCY_WEIGHT,
            "dual_path_weight": COLLECTOR_APPEAL_DUAL_PATH_WEIGHT,
            "headroom_gain": COLLECTOR_APPEAL_HEADROOM_GAIN,
            "status": "superseded_by_collector_appeal_v3",
        },
        "legacy_ca7": {
            "version": COLLECTOR_APPEAL_CA7_VERSION,
            "formula_version": CA7_FORMULA_VERSION,
            "formula_expression": "CA7 = D + lambda * P * (1 - D)",
            "lambda": CA7_PRODUCTION_LAMBDA,
            "status": "superseded_by_collector_appeal_v3",
        },
        "dependencies": {
            # --- the three constructs ------------------------------------
            "desirability_version": UNIVERSAL_SET_DESIRABILITY_VERSION,
            # F is a new scoring input, so every rule that can move it belongs
            # in the hash: the union math, the eligibility it inherits, and the
            # coverage floor that decides whether F exists at all.
            "desirable_outcome_frequency_version": DESIRABLE_OUTCOME_FREQUENCY_VERSION,
            "desirable_outcome_frequency_coverage_policy_version": (
                DESIRABLE_OUTCOME_FREQUENCY_COVERAGE_POLICY_VERSION
            ),
            "desirable_outcome_frequency_minimum_covered_demand_share": (
                MINIMUM_COVERED_DEMAND_SHARE
            ),
            "desirability_eligibility_version": UNIVERSAL_ELIGIBILITY_POLICY_VERSION,
            "dual_path_version": DUAL_PATH_DEPTH_VERSION,
            "collector_appeal_module_version": COLLECTOR_APPEAL_V3_VERSION,
            # The slot-aware union is F's core arithmetic: whether probabilities
            # add within a slot or multiply across slots changes every F.
            "slot_aware_union_version": SUBJECT_CONSTRUCTION_VERSION,
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
            # Every step between "a printed card exists" and "subject s carries
            # demand share q_s" is a scoring decision that can move CA7 without
            # touching the formula. Each was previously invisible to the hash:
            # the fingerprint described the mathematics and said nothing about
            # how its inputs were assembled.
            "subject_demand_source_version": COMPOSITE_SCORING_VERSION,
            "subject_weighting_version": D_FACTOR_VERSION,
            "subject_construction_version": SUBJECT_CONSTRUCTION_VERSION,
            "subject_demand_aggregation_version": SUBJECT_DEMAND_AGGREGATION_VERSION,
            "card_link_source_version": CARD_DESIRABILITY_LINK_SOURCE_VERSION,
            "card_link_aggregation_version": CARD_LINK_AGGREGATION_POLICY_VERSION,
            "card_subject_assembly_version": CARD_SUBJECT_ASSEMBLY_VERSION,
            # --- pull model ------------------------------------------------
            # P is a function of MODELED probabilities. How they are read and how
            # a "1 in N" denominator becomes a probability are as material to the
            # result as the lambda is.
            "pull_model_loader_version": PULL_MODEL_LOADER_VERSION,
            "pull_probability_mapping_version": PULL_PROBABILITY_MAPPING_VERSION,
            # --- component source contract ---------------------------------
            # WHICH row the calculation is allowed to read. A change here means
            # the same formula is being applied to a different set of inputs, so
            # stored rows computed under the old contract are stale.
            "component_source_contract_version": COMPONENT_SOURCE_CONTRACT_VERSION,
            "component_source_scoring_version": EXPECTED_SCORING_VERSION,
            "component_source_hit_policy_version": EXPECTED_HIT_POLICY_VERSION,
            "component_source_composite_scoring_version": EXPECTED_COMPOSITE_SCORING_VERSION,
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
        # Product identity first: anything reading this block must be able to see
        # WHAT metric it is before it sees any number. These are excluded from
        # the hash (see the module docstring).
        "metric_name": COLLECTOR_APPEAL_METRIC_NAME,
        "product_status": COLLECTOR_APPEAL_PRODUCT_STATUS,
        "diagnostics_key": COLLECTOR_APPEAL_V3_DIAGNOSTICS_KEY,
        "formula": resolved["formula"],
        "formula_version": resolved["formula_version"],
        # The scoring constants, surfaced next to the formula so an OPERATOR
        # reading a diagnostics block does not have to open the source to know
        # what weighting produced the number. This identity block is internal -
        # it is stored in `diagnostics_json`, never projected into a public RIP
        # contract, and the public payload discloses no weight.
        "weights": resolved.get("weights"),
        # Superseded. Present so a V2-era or CA7-era row remains identifiable; a
        # reader must never mistake either for the formula in force.
        "legacy_collector_appeal_v2": resolved.get("legacy_collector_appeal_v2"),
        "legacy_ca7": resolved.get("legacy_ca7"),
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

    Reads ``diagnostics_json.collector_appeal_v3.fingerprint`` first - the
    CANONICAL namespaced key - and falls back to the superseded
    ``collector_appeal_v2`` and ``collector_appeal_ca7`` blocks so a row stored
    before the balanced-sum change is still FOUND and correctly classified as
    STALE (its fingerprint predates the schema v3 bump, so it cannot match the
    current one). Falling back is what makes an old row visible; it never makes
    an old row current.

    Neither key is the generic ``collector_appeal``, which is reserved for the
    existing public metric (Pure/Universal Desirability). Reading the generic key
    would make this function answer a question about a different construct.

    Returns None when absent.
    """
    diagnostics = row.get("diagnostics_json")
    if not isinstance(diagnostics, Mapping):
        return None
    for key in (
        COLLECTOR_APPEAL_V3_DIAGNOSTICS_KEY,
        COLLECTOR_APPEAL_V2_DIAGNOSTICS_KEY,
        COLLECTOR_APPEAL_DIAGNOSTICS_KEY,
    ):
        block = diagnostics.get(key)
        if not isinstance(block, Mapping):
            continue
        stored = block.get("fingerprint")
        if isinstance(stored, str) and stored:
            return str(stored)
    return None


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
