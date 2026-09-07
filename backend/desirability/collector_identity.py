"""Deterministic identity rules for Collector Card Appeal.

This module owns *identity only*.  It does not score appeal, playability,
Treatment, scarcity, or market value.

Two identities deliberately remain separate:

* collector subject identity -- Pokemon or named Trainer represented by a card;
* functional identity -- the game piece whose competitive use is measured.

A Professor's Research printing can therefore have one functional identity while
its depicted Trainer subject is unknown/overridden separately.  Conversely, two
cards depicting Cynthia can share a collector subject while being different game
pieces.

The safety rule is conservative: false splits are preferable to false merges.
When canonical gameplay text is missing, functional identity falls back to the
exact Pokemon TCG API card rather than grouping cards by name alone.
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Optional, Sequence


COLLECTOR_IDENTITY_MAPPING_VERSION = "collector_identity_mapping_v1"
FUNCTIONAL_IDENTITY_VERSION = "pokemon_functional_identity_v1"

SUBJECT_ROLE = "subject"
ARTIST_ROLE = "artist"

TRAINER_EXACT = "trainer_exact_name_v1"
TRAINER_POSSESSIVE = "trainer_possessive_name_v1"
TRAINER_COMPOUND = "trainer_compound_exact_v1"
TRAINER_OVERRIDE = "trainer_card_override_v1"

FUNCTIONAL_SIGNATURE = "gameplay_signature_v1"
FUNCTIONAL_EXACT_FALLBACK = "exact_card_fallback_v1"


@dataclass(frozen=True)
class TrainerEntity:
    id: str
    display_name: str
    normalized_name: str


@dataclass(frozen=True)
class TrainerSubjectMatch:
    entity_id: str
    display_name: str
    method: str
    confidence: float
    contribution_weight: float = 1.0


@dataclass(frozen=True)
class FunctionalIdentity:
    functional_key: str
    display_name: str
    normalized_name: str
    supertype: Optional[str]
    method: str
    confidence: float
    identity_json: dict[str, Any]


def normalize_identity_text(value: Any) -> str:
    """Stable accent/punctuation-insensitive identity key."""
    text = str(value or "").strip().casefold()
    text = text.replace("♀", " f ").replace("♂", " m ")
    text = text.replace("’", "'").replace("‘", "'").replace("`", "'")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def normalize_rule_text(value: Any) -> str:
    """Normalize gameplay prose without trying to reinterpret it.

    Boilerplate is intentionally retained in V1.  That may split equivalent
    historical reprints whose rules templating changed, but cannot merge two
    genuinely different game pieces.  Later aliasing can safely join proven
    equivalents; undoing a false merge is much harder.
    """
    return normalize_identity_text(value)


def is_supporter(card: Mapping[str, Any]) -> bool:
    if normalize_identity_text(card.get("supertype")) != "trainer":
        return False
    return "supporter" in {
        normalize_identity_text(value)
        for value in _as_sequence(card.get("subtypes"))
    }


def match_trainer_subjects(
    card: Mapping[str, Any],
    trainer_entities: Sequence[Mapping[str, Any]],
    *,
    card_overrides: Optional[Mapping[str, Sequence[str]]] = None,
) -> list[TrainerSubjectMatch]:
    """Return only deterministic named-Trainer subject matches.

    Safe automatic cases:
      * card name exactly equals a known Trainer name (``Iono``);
      * possessive card title begins with a known Trainer (``Cynthia's Ambition``);
      * every side of an ``&`` / ``and`` compound is a known Trainer
        (``Cynthia & Caitlin``).

    Generic titles such as Professor's Research, Boss's Orders, Friends in
    Sinnoh, Pokemon Fan Club, etc. deliberately return no automatic match.
    Specific printings may be handled by a card-id override after authoritative
    subject review.
    """
    if not is_supporter(card):
        return []

    entities = _trainer_index(trainer_entities)
    if not entities:
        return []

    card_id = str(card.get("id") or "")
    api_card_id = str(card.get("pokemon_tcg_api_card_id") or "")
    overrides = card_overrides or {}
    override_keys = [key for key in (api_card_id, card_id) if key]
    for key in override_keys:
        requested = list(overrides.get(key) or [])
        if not requested:
            continue
        resolved = _resolve_requested_entities(requested, entities)
        if len(resolved) != len(requested):
            return []
        weight = 1.0 / len(resolved)
        return [
            TrainerSubjectMatch(
                entity_id=entity.id,
                display_name=entity.display_name,
                method=TRAINER_OVERRIDE,
                confidence=1.0,
                contribution_weight=weight,
            )
            for entity in resolved
        ]

    raw_name = str(card.get("name") or "").strip()
    normalized = normalize_identity_text(raw_name)
    if not normalized:
        return []

    exact = entities.get(normalized)
    if exact is not None:
        return [
            TrainerSubjectMatch(
                entity_id=exact.id,
                display_name=exact.display_name,
                method=TRAINER_EXACT,
                confidence=1.0,
            )
        ]

    # Match possessive syntax against the raw title so the apostrophe is an
    # explicit boundary.  Do not treat arbitrary substring containment as a
    # Trainer match.
    apostrophe_normalized = raw_name.replace("’", "'").replace("‘", "'")
    possessive = re.match(r"^(.+?)'s\b", apostrophe_normalized, flags=re.IGNORECASE)
    if possessive:
        owner = entities.get(normalize_identity_text(possessive.group(1)))
        if owner is not None:
            return [
                TrainerSubjectMatch(
                    entity_id=owner.id,
                    display_name=owner.display_name,
                    method=TRAINER_POSSESSIVE,
                    confidence=0.98,
                )
            ]

    compound_parts = _compound_parts(raw_name)
    if len(compound_parts) >= 2:
        resolved: list[TrainerEntity] = []
        seen: set[str] = set()
        for part in compound_parts:
            entity = entities.get(normalize_identity_text(part))
            if entity is None or entity.id in seen:
                return []
            seen.add(entity.id)
            resolved.append(entity)
        weight = 1.0 / len(resolved)
        return [
            TrainerSubjectMatch(
                entity_id=entity.id,
                display_name=entity.display_name,
                method=TRAINER_COMPOUND,
                confidence=0.98,
                contribution_weight=weight,
            )
            for entity in resolved
        ]

    return []


def build_functional_identity(card: Mapping[str, Any]) -> Optional[FunctionalIdentity]:
    """Build a stable gameplay identity for Pokemon/Trainer cards.

    Energy is deliberately excluded from Collector Appeal V1 playability.  Cards
    with usable source payloads are grouped by a conservative gameplay signature.
    When that payload is missing or incomplete, the fallback key is exact-card
    scoped so no unrelated historical cards can inherit current playability.
    """
    supertype = str(card.get("supertype") or "").strip() or None
    supertype_key = normalize_identity_text(supertype)
    if supertype_key not in {"pokemon", "trainer"}:
        return None

    name = str(card.get("name") or "").strip()
    normalized_name = normalize_identity_text(name)
    if not normalized_name:
        return None

    payload = card.get("source_payload")
    if isinstance(payload, Mapping):
        signature = gameplay_signature(card, payload)
        if signature_is_usable(signature):
            digest = _stable_digest(signature)
            return FunctionalIdentity(
                functional_key=f"function:{FUNCTIONAL_IDENTITY_VERSION}:{digest}",
                display_name=name,
                normalized_name=normalized_name,
                supertype=supertype,
                method=FUNCTIONAL_SIGNATURE,
                confidence=1.0,
                identity_json={
                    "identityVersion": FUNCTIONAL_IDENTITY_VERSION,
                    "method": FUNCTIONAL_SIGNATURE,
                    "signature": signature,
                },
            )

    exact_key = str(card.get("pokemon_tcg_api_card_id") or card.get("id") or "").strip()
    if not exact_key:
        return None
    return FunctionalIdentity(
        functional_key=f"function:{FUNCTIONAL_IDENTITY_VERSION}:exact:{exact_key}",
        display_name=name,
        normalized_name=normalized_name,
        supertype=supertype,
        method=FUNCTIONAL_EXACT_FALLBACK,
        confidence=0.75,
        identity_json={
            "identityVersion": FUNCTIONAL_IDENTITY_VERSION,
            "method": FUNCTIONAL_EXACT_FALLBACK,
            "exactCardKey": exact_key,
            "reason": "canonical gameplay payload missing_or_incomplete",
        },
    )


def gameplay_signature(card: Mapping[str, Any], payload: Mapping[str, Any]) -> dict[str, Any]:
    """Price/art/set/rarity-independent gameplay signature."""
    supertype = normalize_identity_text(card.get("supertype") or payload.get("supertype"))
    signature: dict[str, Any] = {
        "name": normalize_identity_text(card.get("name") or payload.get("name")),
        "supertype": supertype,
        "subtypes": sorted(
            value for value in (
                normalize_identity_text(item)
                for item in _as_sequence(card.get("subtypes") or payload.get("subtypes"))
            ) if value
        ),
        "rules": sorted(
            value for value in (
                normalize_rule_text(item)
                for item in _as_sequence(payload.get("rules"))
            ) if value
        ),
    }

    if supertype == "pokemon":
        signature.update(
            {
                "hp": _normalized_scalar(payload.get("hp")),
                "types": sorted(_normalized_sequence(payload.get("types"))),
                "evolvesFrom": normalize_identity_text(payload.get("evolvesFrom")),
                "abilities": _normalized_object_list(
                    payload.get("abilities"),
                    fields=("name", "type", "text"),
                ),
                "attacks": _normalized_attacks(payload.get("attacks")),
                "weaknesses": _normalized_object_list(
                    payload.get("weaknesses"),
                    fields=("type", "value"),
                ),
                "resistances": _normalized_object_list(
                    payload.get("resistances"),
                    fields=("type", "value"),
                ),
                "retreatCost": sorted(_normalized_sequence(payload.get("retreatCost"))),
                "convertedRetreatCost": _normalized_scalar(payload.get("convertedRetreatCost")),
            }
        )

    return signature


def signature_is_usable(signature: Mapping[str, Any]) -> bool:
    if not signature.get("name") or signature.get("supertype") not in {"pokemon", "trainer"}:
        return False
    if signature.get("supertype") == "trainer":
        return bool(signature.get("rules"))
    return bool(
        signature.get("attacks")
        or signature.get("abilities")
        or signature.get("rules")
        or signature.get("hp")
    )


def _trainer_index(rows: Iterable[Mapping[str, Any]]) -> dict[str, TrainerEntity]:
    index: dict[str, TrainerEntity] = {}
    duplicates: set[str] = set()
    for row in rows:
        if normalize_identity_text(row.get("entity_type")) != "trainer":
            continue
        entity_id = str(row.get("id") or "")
        display = str(row.get("display_name") or "").strip()
        key = normalize_identity_text(row.get("normalized_name") or display)
        if not entity_id or not display or not key:
            continue
        if key in index and index[key].id != entity_id:
            duplicates.add(key)
            continue
        index[key] = TrainerEntity(entity_id, display, key)
    for key in duplicates:
        index.pop(key, None)
    return index


def _resolve_requested_entities(
    requested: Sequence[str],
    entities: Mapping[str, TrainerEntity],
) -> list[TrainerEntity]:
    resolved: list[TrainerEntity] = []
    seen: set[str] = set()
    for name in requested:
        entity = entities.get(normalize_identity_text(name))
        if entity is None or entity.id in seen:
            continue
        seen.add(entity.id)
        resolved.append(entity)
    return resolved


def _compound_parts(value: str) -> list[str]:
    # Ampersand is the unambiguous TCG convention for Tag Team Supporters.
    # Plain "and" is accepted only when it yields 2+ nonempty exact names; the
    # caller still requires every part to resolve to an entity.
    normalized = value.replace("＆", "&")
    parts = re.split(r"\s+(?:&|and)\s+", normalized, flags=re.IGNORECASE)
    return [part.strip() for part in parts if part.strip()]


def _stable_digest(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:24]


def _as_sequence(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return list(value)
    return [value]


def _normalized_scalar(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return value
    text = normalize_identity_text(value)
    return text or None


def _normalized_sequence(value: Any) -> list[str]:
    return [
        normalized
        for normalized in (normalize_identity_text(item) for item in _as_sequence(value))
        if normalized
    ]


def _normalized_object_list(value: Any, *, fields: Sequence[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in _as_sequence(value):
        if not isinstance(item, Mapping):
            continue
        row = {
            field: normalize_rule_text(item.get(field))
            for field in fields
            if item.get(field) is not None
        }
        if row:
            rows.append(row)
    return sorted(rows, key=lambda row: json.dumps(row, sort_keys=True, separators=(",", ":")))


def _normalized_attacks(value: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for attack in _as_sequence(value):
        if not isinstance(attack, Mapping):
            continue
        row = {
            "name": normalize_identity_text(attack.get("name")),
            "cost": _normalized_sequence(attack.get("cost")),
            "convertedEnergyCost": _normalized_scalar(attack.get("convertedEnergyCost")),
            "damage": normalize_identity_text(attack.get("damage")),
            "text": normalize_rule_text(attack.get("text")),
        }
        rows.append(row)
    return sorted(rows, key=lambda row: json.dumps(row, sort_keys=True, separators=(",", ":")))
