"""How a printed card becomes a demand-carrying subject.

WHY THIS MODULE EXISTS
----------------------
Between "a card exists in a set" and "this subject has demand q_s" sits a chain
of decisions that no version string previously covered:

  * which table links a card to a Pokemon reference, and at what weight;
  * how a card with SEVERAL links (a tag-team, a duo card) resolves to one
    appeal number and one primary subject;
  * which composite demand score is joined in.

Change any of these and Dual-Path Depth moves, because the demand shares that
weight it move. Change the link table's contents and the same code produces a
different answer from the same formula.

Like ``pull_model``, this module OWNS the policy rather than describing it:
``build_opening_appeal_study.load_appeal_by_card`` imports and uses
:func:`aggregate_card_appeal`, so the rule and its version cannot drift apart.
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

# Where card -> Pokemon-reference links are read from.
CARD_DESIRABILITY_LINK_SOURCE_VERSION = "card_desirability_link_source_v1_pokemon_card_desirability_links"
CARD_DESIRABILITY_LINK_TABLE = "pokemon_card_desirability_links"
CARD_DESIRABILITY_LINK_COLUMNS = "pokemon_canonical_card_id,pokemon_reference_id,contribution_weight"

# How multiple links on one card collapse to one appeal value and one subject.
#
# The rule: contribution-weighted MEAN of the linked references' composite
# desirability, with the HEAVIEST-weighted link naming the primary subject.
# Bump this when either half changes - "weighted mean + heaviest primary" and
# "max + first primary" produce different numbers from identical rows.
CARD_LINK_AGGREGATION_POLICY_VERSION = "card_link_aggregation_v1_weighted_mean_heaviest_primary"

# How assembled cards are grouped into subjects for the dual-path calculation.
#
# The subject key is ``ref:<primary_reference_id>``, so two printings of the
# same Pokemon are ONE subject with two cards - which is precisely the structure
# Dual-Path Depth measures. Keying on card name instead would make every
# printing its own subject and force P toward the single-printing bound of 0.25.
CARD_SUBJECT_ASSEMBLY_VERSION = "card_subject_assembly_v1_primary_reference_key"
CARD_SUBJECT_KEY_PREFIX = "ref:"

# A link with no positive weight contributes nothing rather than defaulting to
# an equal share: an explicit zero is a statement, not a gap.
CARD_LINK_DEFAULT_WEIGHT = 1.0
CARD_LINK_MIN_WEIGHT_EXCLUSIVE = 0.0


def subject_key_for(reference_id: Any) -> str:
    """The canonical subject key for a Pokemon reference."""
    return f"{CARD_SUBJECT_KEY_PREFIX}{reference_id}"


def aggregate_card_appeal(
    links: Iterable[Mapping[str, Any]],
    scores_by_reference: Mapping[int, Mapping[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Collapse one card's links into ``{appeal, primary_reference_id, primary_species}``.

    Returns None - never a zero-appeal row - when the card has no usable link.
    An unlinked card is unknown, not unappealing, and the two must not be stored
    as the same fact.
    """
    weighted: List[Tuple[float, float, int]] = []
    for link in links:
        try:
            reference_id = int(link.get("pokemon_reference_id"))
        except (TypeError, ValueError):
            continue
        score = _as_float((scores_by_reference.get(reference_id) or {}).get("desirability_score"))
        if score is None:
            continue
        weight = _as_float(link.get("contribution_weight"))
        weight = CARD_LINK_DEFAULT_WEIGHT if weight is None else weight
        if weight <= CARD_LINK_MIN_WEIGHT_EXCLUSIVE:
            continue
        weighted.append((score, weight, reference_id))

    total = sum(weight for _score, weight, _ref in weighted)
    if total <= 0:
        return None
    primary = max(weighted, key=lambda item: item[1])
    return {
        "appeal": sum(score * weight for score, weight, _ref in weighted) / total,
        "primary_reference_id": primary[2],
        "primary_species": (scores_by_reference.get(primary[2]) or {}).get("pokemon_name"),
    }


def card_link_policy() -> Dict[str, Any]:
    """The full policy, for the fingerprint and the source identity block."""
    return {
        "link_source_version": CARD_DESIRABILITY_LINK_SOURCE_VERSION,
        "link_table": CARD_DESIRABILITY_LINK_TABLE,
        "aggregation_policy_version": CARD_LINK_AGGREGATION_POLICY_VERSION,
        "subject_assembly_version": CARD_SUBJECT_ASSEMBLY_VERSION,
        "subject_key_prefix": CARD_SUBJECT_KEY_PREFIX,
        "default_weight": CARD_LINK_DEFAULT_WEIGHT,
        "aggregation_rule": "contribution-weighted mean; heaviest link names the primary subject",
        "unlinked_card_returns": "None",
    }


def build_card_input_manifest(subjects_by_set: Mapping[str, Any]) -> Dict[str, Any]:
    """A deterministic hash of the card inputs Dual-Path Depth was computed from.

    Hashes the assembled subjects and their per-card pull probabilities - the
    exact values P consumed - rather than the raw card rows, so the manifest
    covers the assembly as well as the source.
    """
    digest_input = []
    for set_id in sorted(subjects_by_set, key=str):
        subjects = subjects_by_set[set_id] or []
        digest_input.append(
            {
                "set_id": str(set_id),
                "subjects": sorted(
                    (
                        {
                            "subject_key": str(subject.get("subject_key")),
                            "subject_demand": _normalize_number(subject.get("subject_demand")),
                            "cards": sorted(
                                (
                                    {
                                        "card_name": str(card.get("card_name")),
                                        "rarity": str(card.get("rarity")),
                                        "pull_probability": _normalize_number(card.get("pull_probability")),
                                        "slot_group": str(card.get("slot_group")),
                                    }
                                    for card in (subject.get("cards") or [])
                                ),
                                key=lambda card: (card["card_name"], str(card["pull_probability"])),
                            ),
                        }
                        for subject in subjects
                    ),
                    key=lambda subject: subject["subject_key"],
                ),
            }
        )
    blob = json.dumps(digest_input, sort_keys=True, separators=(",", ":"))
    return {
        "set_count": len(digest_input),
        "subject_count": sum(len(entry["subjects"]) for entry in digest_input),
        "manifest_hash": hashlib.sha256(blob.encode("utf-8")).hexdigest(),
        "algorithm": "sha256",
        "assembly_version": CARD_SUBJECT_ASSEMBLY_VERSION,
        "link_source_version": CARD_DESIRABILITY_LINK_SOURCE_VERSION,
    }


def _as_float(value: Any) -> Optional[float]:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _normalize_number(value: Any) -> Optional[str]:
    parsed = _as_float(value)
    return None if parsed is None else repr(round(parsed, 12))
