"""Deterministic research-only condition labels for sold-listing titles."""
from __future__ import annotations

import re
from typing import Any

CLASSIFIER_VERSION = "pkmnprices_sold_title_condition_v1"

_RULES = {
    "NM": ((r"\bnear[ -]?mint\b", "near mint", "HIGH"), (r"\bnm\b", "nm", "MEDIUM")),
    "LP": ((r"\blight(?:ly)?[ -]?play(?:ed)?\b", "lightly played", "HIGH"), (r"\blp\b", "lp", "MEDIUM")),
    "MP": ((r"\bmoderat(?:e|ely)[ -]?play(?:ed)?\b", "moderately played", "HIGH"), (r"\bmp\b", "mp", "MEDIUM")),
    "HP": ((r"\bheav(?:y|ily)[ -]?play(?:ed)?\b", "heavily played", "HIGH"), (r"\bhp\b", "hp", "MEDIUM")),
    "DAMAGED": (
        (r"\bdamaged\b", "damaged", "HIGH"), (r"\bdmg\b", "dmg", "MEDIUM"),
        (r"\b(?:creased?|torn|water[ -]?damaged?)\b", "physical damage cue", "MEDIUM"),
    ),
}


def classify_sold_title(title: Any) -> dict[str, Any]:
    text = str(title or "")
    found: dict[str, list[tuple[str, str]]] = {}
    for label, rules in _RULES.items():
        hits = [(token, confidence) for pattern, token, confidence in rules if re.search(pattern, text, re.I)]
        if hits:
            found[label] = hits
    evidence = sorted({token for hits in found.values() for token, _ in hits})
    if len(found) > 1:
        return {
            "condition_label": "AMBIGUOUS", "confidence": "LOW",
            "evidence_tokens": evidence, "classifier_version": CLASSIFIER_VERSION,
            "ambiguity_reason": "CONFLICTING_CONDITION_LABELS:" + ",".join(sorted(found)),
        }
    if not found:
        return {
            "condition_label": "UNLABELED", "confidence": "NONE",
            "evidence_tokens": [], "classifier_version": CLASSIFIER_VERSION,
            "ambiguity_reason": None,
        }
    label = next(iter(found))
    confidence = "HIGH" if any(value == "HIGH" for _, value in found[label]) else "MEDIUM"
    return {
        "condition_label": label, "confidence": confidence,
        "evidence_tokens": evidence, "classifier_version": CLASSIFIER_VERSION,
        "ambiguity_reason": None,
    }


def classification_record(sold_evidence_id: str, title: Any, *, classified_at: str) -> dict[str, Any]:
    """Build a separate persistence row without changing raw sold evidence."""
    result = classify_sold_title(title)
    return {
        "sold_evidence_id": str(sold_evidence_id),
        **result,
        "classified_at": classified_at,
    }
