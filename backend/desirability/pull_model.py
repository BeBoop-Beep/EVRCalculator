"""The modeled pull-probability policy: where pack odds come from and what they mean.

WHY THIS MODULE EXISTS
----------------------
Collector Appeal's Dual-Path Depth (P) is a function of modeled pull
probabilities. Those probabilities are not measured; they are DERIVED from a
snapshot payload by a specific set of rules:

  * which table the pack model is read from;
  * which ``group`` wins when a rarity appears more than once;
  * how a "1 in N" denominator becomes a probability;
  * what counts as the mutually-exclusive slot a card competes in.

Every one of those rules can change the computed P - and therefore every stored
Collector Appeal score - without touching the CA7 formula, the lambda, or any
desirability input. Before this module the rules lived as literals inside a
study script's loader, so the formula fingerprint could not see them: the pack
model could be re-derived under new rules and every stored row would still
certify itself as current.

The constants here are the SOURCE OF TRUTH, not a description of it.
``build_opening_appeal_study.load_pull_rate_model`` imports and uses them, so a
change to the policy moves the loader and the fingerprint together. A parallel
copy would drift, and drift in a fingerprint dependency is worse than no
fingerprint at all - it is a false certificate.
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Dict, Mapping, Optional

# The loader contract: which table, which columns, which payload keys.
#
# Bump this when the READ changes shape - a different source table, a different
# payload key, a different column - because the same rules against a different
# source are different inputs.
PULL_MODEL_LOADER_VERSION = "pull_model_loader_v1_set_page_snapshot_latest"

# The mapping contract: how a snapshot row becomes (probability, slot_group).
#
# Bump this when the ARITHMETIC or the grouping rule changes. Kept separate from
# the loader version because the two fail differently: a loader change means we
# read different rows, a mapping change means we read the same rows and compute
# different numbers from them.
PULL_PROBABILITY_MAPPING_VERSION = "pull_probability_mapping_v1_reciprocal_denominator"

PULL_MODEL_SOURCE_TABLE = "pokemon_set_page_snapshot_latest"
PULL_MODEL_SOURCE_COLUMNS = "set_id,payload_json"

# The payload keys the loader accepts, in precedence order. Both spellings exist
# in production snapshots; accepting either is part of the contract, not a
# convenience, so it is pinned here.
PULL_MODEL_PAYLOAD_KEYS = ("pull_rate_assumptions", "pullRateAssumptions")

# When one rarity is described by more than one row, the lower priority wins.
# ``hit_rarity_model`` is the purpose-built hit model and beats the generic
# ``pack_structure`` fallback; anything unrecognized loses to both.
PULL_MODEL_GROUP_PRIORITY: Dict[str, int] = {"hit_rarity_model": 0, "pack_structure": 1}
PULL_MODEL_UNKNOWN_GROUP_PRIORITY = 9

# The field a card's mutually-exclusive slot is read from, in precedence order.
# Cards sharing a slot have their probabilities ADDED, never combined by an
# independence formula, so what counts as "the same slot" is a scoring decision.
PULL_MODEL_SLOT_FIELDS = ("slot_label", "group")
PULL_MODEL_UNKNOWN_SLOT = "unknown"


def probability_from_denominator(denominator: Any) -> Optional[float]:
    """``P(specific card) = 1 / N`` from a "1 in N" odds denominator.

    Returns None - never 0.0 - for a missing, non-finite or non-positive
    denominator. A zero here would silently claim "this card cannot be pulled",
    which is a measurement, not an absence.
    """
    try:
        value = float(denominator)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(value) or value <= 0:
        return None
    return 1.0 / value


def group_priority(group: Any) -> int:
    """Precedence of a snapshot row's ``group``. Lower wins."""
    return PULL_MODEL_GROUP_PRIORITY.get(str(group or ""), PULL_MODEL_UNKNOWN_GROUP_PRIORITY)


def slot_group_of(entry: Mapping[str, Any]) -> str:
    """The mutually-exclusive slot a snapshot row's cards compete in."""
    for field in PULL_MODEL_SLOT_FIELDS:
        value = entry.get(field)
        if value:
            return str(value)
    return PULL_MODEL_UNKNOWN_SLOT


def pull_model_policy() -> Dict[str, Any]:
    """The full policy, for the fingerprint and for the source identity block."""
    return {
        "loader_version": PULL_MODEL_LOADER_VERSION,
        "mapping_version": PULL_PROBABILITY_MAPPING_VERSION,
        "source_table": PULL_MODEL_SOURCE_TABLE,
        "payload_keys": list(PULL_MODEL_PAYLOAD_KEYS),
        "group_priority": dict(PULL_MODEL_GROUP_PRIORITY),
        "unknown_group_priority": PULL_MODEL_UNKNOWN_GROUP_PRIORITY,
        "slot_fields": list(PULL_MODEL_SLOT_FIELDS),
        "probability_rule": "1 / specific_card_odds_denominator",
        "missing_denominator_returns": "None",
    }


def build_pull_model_manifest(pull_model: Mapping[str, Mapping[str, Mapping[str, Any]]]) -> Dict[str, Any]:
    """A deterministic hash of the pull model a plan was actually built from.

    The policy version says HOW probabilities were derived; this says WHICH ones
    were in hand. Both are required: the rules can hold still while the snapshot
    underneath them moves, and that moves every P.
    """
    digest_input = []
    for set_id in sorted(pull_model, key=str):
        rarities = pull_model[set_id] or {}
        digest_input.append(
            {
                "set_id": str(set_id),
                "rarities": [
                    {
                        "rarity_key": str(key),
                        "probability": _normalize_number((rarities[key] or {}).get("probability")),
                        "slot_group": str((rarities[key] or {}).get("slot_group")),
                    }
                    for key in sorted(rarities, key=str)
                ],
            }
        )
    blob = json.dumps(digest_input, sort_keys=True, separators=(",", ":"))
    return {
        "modeled_set_count": len(digest_input),
        "manifest_hash": hashlib.sha256(blob.encode("utf-8")).hexdigest(),
        "algorithm": "sha256",
        "policy_version": PULL_MODEL_LOADER_VERSION,
        "mapping_version": PULL_PROBABILITY_MAPPING_VERSION,
    }


def _normalize_number(value: Any) -> Optional[str]:
    try:
        return repr(round(float(value), 12))
    except (TypeError, ValueError):
        return None
