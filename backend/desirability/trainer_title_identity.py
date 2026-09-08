"""Conservative, deterministic Supporter-title classification for C2.6."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Sequence

from backend.desirability.collector_identity import normalize_identity_text

CLASSIFIER_VERSION = "trainer_title_denominator_v1"

VARIABLE_TITLES = {
    "boss s orders", "professor s research",
}
GENERIC_PHRASES = {
    "ace trainer", "adventurer s discovery", "aether foundation employee", "apricorn maker",
    "aroma lady", "ball guy", "battle reporter", "beauty", "bird keeper", "black belt",
    "black belt s training", "blacksmith", "bug catcher", "cafe master", "caretaker", "castaway",
    "channeler", "cheerleader s cheer", "ciphermaniac s codebreaking", "coach trainer", "cook",
    "copycat", "dancer", "delinquent", "department store girl", "desert shaman", "digging duo",
    "doctor", "emcee s chatter", "emcee s hype", "engineer s adjustments", "explorer s guidance",
    "fieldworker", "firebreather", "fisherman", "flower shop lady", "forest guardian",
    "fossil excavator", "fossil researcher", "furisode girl", "gym trainer", "harlequin", "hex maniac",
    "hiker", "holon adventurer", "holon farmer", "holon lass", "holon mentor", "holon researcher",
    "holon scientist", "island hermit", "judge", "juggler", "kindler", "lady", "lady outing",
    "lass s special", "league staff", "ninja boy", "oracle", "paldean student", "parasol lady",
    "poke kid", "poke maniac", "pokemon breeder", "pokemon breeder s nurturing", "pokemon center lady",
    "pokemon collector", "pokemon fan club", "pokemon nurse", "pokemon ranger", "psychic s third eye",
    "relic hunter", "rival", "roller skater", "ruffian", "schoolboy", "schoolgirl", "seeker", "seer",
    "sightseer", "surfer", "teammates", "town volunteers", "traveling salesman", "twins", "tv reporter",
    "ultra forest kartenvoy", "underground expedition", "waitress", "welder", "worker", "youngster",
    "interviewer s questions", "mom s kindness", "sage s training",
}
GENERIC_PREFIXES = ("friends in ",)
TEAM_ORGANIZATION = (
    "here comes team rocket", "miss fortune sisters", "rocket s admin", "rocket s mission",
    "rust syndicate grunt", "shadow triad", "team aqua ", "team flare grunt", "team galactic s wager",
    "team magma ", "team plasma grunt", "team rocket s handiwork", "team rocket s trickery",
    "team skull grunt", "team star grunt", "team yell grunt", "team yell s cheer", "ultra recon squad",
)
KNOWN_TEAM_PEOPLE = {"team galactic s mars": "Mars", "team rocket s archer": "Archer",
                     "team rocket s ariana": "Ariana", "team rocket s giovanni": "Giovanni",
                     "team rocket s petrel": "Petrel", "team rocket s proton": "Proton"}
SPECIAL_SUBJECTS = {"rapid strike style mustard": "Mustard", "single strike style mustard": "Mustard"}
SPECIAL_COMPOUNDS = {"hooligans jim and cas": ("Jim", "Cas")}


@dataclass(frozen=True)
class TitleClassification:
    classification: str
    subjects: tuple[str, ...] = ()
    rule: str = ""
    confidence: float = 1.0


def classify_supporter_title(title: str, known_names: Sequence[str] = ()) -> TitleClassification:
    raw = " ".join(str(title or "").replace("◇", "").split()).strip()
    key = normalize_identity_text(raw)
    known = {normalize_identity_text(x): str(x) for x in known_names}
    if key in VARIABLE_TITLES:
        return TitleClassification("generic_card_with_variable_character", rule="variable_functional_title_exact_v1")
    parenthetical = re.match(r"^(.+?)\s*\((.+)\)$", raw)
    if parenthetical and normalize_identity_text(parenthetical.group(1)) in VARIABLE_TITLES:
        return TitleClassification("explicit_named_subject", (parenthetical.group(2).strip(),), "explicit_parenthetical_subject_v1")
    if key in KNOWN_TEAM_PEOPLE:
        return TitleClassification("explicit_named_subject", (KNOWN_TEAM_PEOPLE[key],), "explicit_team_possessive_name_v1")
    if key in SPECIAL_SUBJECTS:
        return TitleClassification("explicit_named_subject", (SPECIAL_SUBJECTS[key],), "explicit_style_name_v1")
    if key in SPECIAL_COMPOUNDS:
        return TitleClassification("explicit_named_subject", SPECIAL_COMPOUNDS[key], "explicit_compound_names_v1", .98)
    if key in GENERIC_PHRASES or any(key.startswith(x) for x in GENERIC_PREFIXES):
        return TitleClassification("generic_role_or_class", rule="reviewed_generic_title_v1")
    if any(key.startswith(x) for x in TEAM_ORGANIZATION):
        return TitleClassification("team_or_organization", rule="reviewed_team_title_v1")
    exact = known.get(key)
    if exact:
        return TitleClassification("explicit_named_subject", (exact,), "registry_exact_title_v1")
    possessive = re.match(r"^(.+?)[’']s\b", raw)
    if possessive:
        owner = possessive.group(1).strip()
        owner_key = normalize_identity_text(owner)
        if owner_key and owner_key not in {"adventurer", "cheerleader", "engineer", "lass", "psychic"}:
            return TitleClassification("explicit_named_subject", (owner,), "explicit_possessive_owner_v1", .98)
    parts = [x.strip() for x in re.split(r"\s+&\s+", raw) if x.strip()]
    if len(parts) >= 2 and all(normalize_identity_text(x) not in GENERIC_PHRASES for x in parts):
        return TitleClassification("explicit_named_subject", tuple(parts), "explicit_compound_names_v1", .98)
    # A standalone, title-cased Supporter title is explicit only when it has no
    # sentence-like connective. Remaining doubtful titles stay reviewable.
    if raw and len(raw.split()) <= 3 and not re.search(r"\b(in|of|the|with|and)\b", raw, re.I):
        return TitleClassification("explicit_named_subject", (raw,), "explicit_standalone_title_v1", .97)
    return TitleClassification("requires_manual_review", rule="no_safe_title_rule_v1", confidence=0.0)
