"""Condition-title classifier V3 with canonical-card HP disambiguation.

V1 treated every standalone "HP" token as Heavily Played.
V2 suppressed any numeric HP-looking pair, which fixed Pokemon stat collisions but
could also suppress true condition shorthand when card numbers sit next to "HP"
(e.g. "HP 103/110" or "#6/102 HP").

V3 keeps V1/V2 frozen and uses trusted canonical Pokemon card HP metadata to
suppress an HP token only when the adjacent numeric value exactly matches the
canonical card's printed HP. No match (or no canonical HP) means "HP" remains a
condition cue.
"""
from __future__ import annotations

import re
from typing import Any

CLASSIFIER_VERSION = "pkmnprices_sold_title_condition_v3"

_RULES = {
    "NM": (
        (r"\bnear[ -]?mint\b", "near mint", "HIGH"),
        (r"\bnm\b", "nm", "MEDIUM"),
    ),
    "LP": (
        (r"\blight(?:ly)?[ -]?play(?:ed)?\b", "lightly played", "HIGH"),
        (r"\blp\b", "lp", "MEDIUM"),
    ),
    "MP": (
        (r"\bmoderat(?:e|ely)[ -]?play(?:ed)?\b", "moderately played", "HIGH"),
        (r"\bmp\b", "mp", "MEDIUM"),
    ),
    "HP": (
        (r"\bheav(?:y|ily)[ -]?play(?:ed)?\b", "heavily played", "HIGH"),
        (r"\bhp\b", "hp", "MEDIUM"),
    ),
    "DAMAGED": (
        (r"\bdamaged\b", "damaged", "HIGH"),
        (r"\bdmg\b", "dmg", "MEDIUM"),
        (r"\b(?:creased?|torn|water[ -]?damaged?)\b", "physical damage cue", "MEDIUM"),
    ),
}

_HP_TOKEN_RE = re.compile(r"\bhp\b", re.I)
_LEFT_HP_VALUE_RE = re.compile(r"(?:^|[^0-9/])(\d{2,3})\s*$")
_RIGHT_HP_VALUE_RE = re.compile(r"^\s*(\d{2,3})(?![0-9/])")


def _canonical_hp_text(canonical_hp: Any) -> str | None:
    value = str(canonical_hp or "").strip()
    if not re.fullmatch(r"\d{2,3}", value):
        return None
    return value


def resolve_hp_stat_tokens(title: Any, canonical_hp: Any) -> dict[str, Any]:
    """Return a masked title plus an auditable canonical-HP resolution receipt."""
    text = str(title or "")
    canonical = _canonical_hp_text(canonical_hp)
    if canonical is None:
        return {
            "masked_title": text,
            "canonical_hp": None,
            "suppressed_hp_stat_count": 0,
            "suppressed_spans": [],
        }

    chars = list(text)
    suppressed_spans: list[dict[str, Any]] = []

    for match in _HP_TOKEN_RE.finditer(text):
        left = text[: match.start()]
        right = text[match.end() :]

        left_match = _LEFT_HP_VALUE_RE.search(left)
        right_match = _RIGHT_HP_VALUE_RE.match(right)

        left_value = left_match.group(1) if left_match else None
        right_value = right_match.group(1) if right_match else None

        matched_value = None
        direction = None
        if left_value == canonical:
            matched_value = left_value
            direction = "VALUE_HP"
        elif right_value == canonical:
            matched_value = right_value
            direction = "HP_VALUE"

        if matched_value is None:
            continue

        # Mask only the HP token. Leaving the number in place cannot create a
        # condition cue and avoids accidentally erasing neighboring card-number text.
        for index in range(match.start(), match.end()):
            chars[index] = " "
        suppressed_spans.append(
            {
                "start": match.start(),
                "end": match.end(),
                "canonical_hp": canonical,
                "matched_value": matched_value,
                "direction": direction,
            }
        )

    return {
        "masked_title": "".join(chars),
        "canonical_hp": canonical,
        "suppressed_hp_stat_count": len(suppressed_spans),
        "suppressed_spans": suppressed_spans,
    }


def classify_sold_title_v3(title: Any, *, canonical_hp: Any = None) -> dict[str, Any]:
    text = str(title or "")
    hp_resolution = resolve_hp_stat_tokens(text, canonical_hp)
    hp_condition_text = hp_resolution["masked_title"]

    found: dict[str, list[tuple[str, str]]] = {}
    for label, rules in _RULES.items():
        search_text = hp_condition_text if label == "HP" else text
        hits = [
            (token, confidence)
            for pattern, token, confidence in rules
            if re.search(pattern, search_text, re.I)
        ]
        if hits:
            found[label] = hits

    evidence = sorted({token for hits in found.values() for token, _ in hits})
    if len(found) > 1:
        return {
            "condition_label": "AMBIGUOUS",
            "confidence": "LOW",
            "evidence_tokens": evidence,
            "classifier_version": CLASSIFIER_VERSION,
            "ambiguity_reason": "CONFLICTING_CONDITION_LABELS:" + ",".join(sorted(found)),
        }

    if not found:
        return {
            "condition_label": "UNLABELED",
            "confidence": "NONE",
            "evidence_tokens": [],
            "classifier_version": CLASSIFIER_VERSION,
            "ambiguity_reason": None,
        }

    label = next(iter(found))
    confidence = (
        "HIGH"
        if any(value == "HIGH" for _, value in found[label])
        else "MEDIUM"
    )
    return {
        "condition_label": label,
        "confidence": confidence,
        "evidence_tokens": evidence,
        "classifier_version": CLASSIFIER_VERSION,
        "ambiguity_reason": None,
    }


def classification_record_v3(
    sold_evidence_id: str,
    title: Any,
    *,
    canonical_hp: Any = None,
    classified_at: str,
) -> dict[str, Any]:
    result = classify_sold_title_v3(title, canonical_hp=canonical_hp)
    return {
        "sold_evidence_id": str(sold_evidence_id),
        **result,
        "classified_at": classified_at,
    }
