"""Era-aware, price-independent structural Treatment taxonomy V3."""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, asdict
from typing import Any

TAXONOMY_VERSION = "pokemon_card_treatment_taxonomy_v3"
ATTRIBUTE_DEFINITIONS = {
    "illustration_led":"Artwork is the dominant presentation feature.","full_art":"Artwork extends beyond the standard illustration box.",
    "extended_art":"Artwork/frame is extended beyond the standard frame; requires explicit metadata.","alternate_artwork":"Alternate artwork for an otherwise corresponding card.",
    "textured":"Physical/textured print treatment is explicitly established.","gold_or_gilded":"Gold-colored border, frame, or accents are intrinsic to the treatment.",
    "rainbow":"Rainbow-colored treatment.","shiny":"The depicted Pokémon is explicitly a Shiny treatment.","holo":"Holofoil presentation.",
    "reverse_holo":"Foil outside the ordinary illustration treatment.","etched_or_special_foil":"Named nonstandard foil or pattern.",
    "gallery_style":"Named gallery/subset illustration presentation; requires explicit metadata.","borderless_or_extended_frame":"Borderless/extended-frame layout; requires explicit metadata.",
    "standard_frame":"Ordinary era-local frame.","premium_frame":"Nonstandard premium frame or layout.","character_scene":"Full scene/environment presentation.",
    "trainer_gallery_style":"Named Trainer Gallery presentation; requires explicit metadata.","subset_specialty":"Special subset or secret-number presentation.",
    "vintage_specialty":"Era-local historical specialty with no asserted modern equivalence.","promo_only":"Distribution-specific promo status; never inferred from rarity alone.",
    "unique_mechanic_treatment":"Presentation is bundled with a named gameplay/form mechanic.",
}

def key(value: Any) -> str | None:
    value=re.sub(r"[^a-z0-9]+","_",str(value or "").strip().lower()).strip("_")
    return value or None

BASE = {
    "common":("common",["standard_frame"]), "uncommon":("uncommon",["standard_frame"]),
    "rare":("rare",["standard_frame"]), "rare_holo":("rare_holo",["holo","standard_frame"]),
    "illustration_rare":("illustration_rare",["illustration_led","full_art","alternate_artwork","character_scene"]),
    "special_illustration_rare":("special_illustration_rare",["illustration_led","full_art","alternate_artwork","premium_frame","character_scene"]),
    "ultra_rare":("ultra_rare",["full_art","premium_frame"]),
    "double_rare":("double_rare",["holo","premium_frame"]),
    "hyper_rare":("hyper_rare_gold",["full_art","gold_or_gilded","premium_frame"]),
    "ace_spec_rare":("ace_spec",["unique_mechanic_treatment","premium_frame"]),
    "shiny_rare":("shiny_rare",["shiny","holo","subset_specialty"]),
    "shiny_ultra_rare":("shiny_ultra_rare",["shiny","full_art","holo","premium_frame","subset_specialty"]),
    "black_white_rare":("black_white_rare",["illustration_led","full_art","premium_frame","subset_specialty"]),
    "mega_hyper_rare":("mega_hyper_rare",["full_art","gold_or_gilded","premium_frame","unique_mechanic_treatment"]),
    "mega_attack_rare":("mega_attack_rare",["illustration_led","full_art","premium_frame","unique_mechanic_treatment"]),
}
LEGACY = {
    "rare_holo_ex":("rare_holo_ex",["holo","premium_frame","unique_mechanic_treatment"]),
    "rare_ultra":("rare_ultra",["full_art","premium_frame"]),
    "rare_ace":("ace_spec",["unique_mechanic_treatment","premium_frame"]),
    "rare_holo_lv_x":("rare_holo_lv_x",["holo","premium_frame","unique_mechanic_treatment","vintage_specialty"]),
    "rare_holo_star":("gold_star",["holo","shiny","premium_frame","vintage_specialty"]),
    "rare_prime":("prime",["holo","premium_frame","unique_mechanic_treatment","vintage_specialty"]),
    "legend":("legend",["holo","premium_frame","unique_mechanic_treatment","vintage_specialty"]),
    "rare_shining":("shining",["holo","shiny","premium_frame","vintage_specialty"]),
    "rare_holo_gx":("rare_holo_gx",["holo","premium_frame","unique_mechanic_treatment"]),
    "rare_rainbow":("rainbow_rare",["rainbow","textured","full_art","premium_frame"]),
    "rare_prism_star":("prism_star",["holo","premium_frame","unique_mechanic_treatment"]),
    "rare_holo_v":("rare_holo_v",["holo","premium_frame","unique_mechanic_treatment"]),
    "rare_holo_vmax":("rare_holo_vmax",["holo","textured","premium_frame","unique_mechanic_treatment"]),
    "rare_holo_vstar":("rare_holo_vstar",["holo","premium_frame","unique_mechanic_treatment"]),
    "radiant_rare":("radiant_rare",["holo","shiny","premium_frame","unique_mechanic_treatment"]),
    "amazing_rare":("amazing_rare",["holo","premium_frame","unique_mechanic_treatment"]),
    "rare_break":("break",["holo","premium_frame","unique_mechanic_treatment"]),
}

SECRET_BY_ERA = {
    "Black and White":["shiny","holo","subset_specialty"],
    "XY":["full_art","gold_or_gilded","premium_frame","subset_specialty"],
    "Sun and Moon":["gold_or_gilded","textured","premium_frame","subset_specialty"],
    "Sword and Shield":["gold_or_gilded","textured","premium_frame","subset_specialty"],
}

@dataclass(frozen=True)
class TreatmentV3:
    era_local_label: str | None
    treatment_key: str | None
    semantic_attributes: tuple[str,...]
    resolution: str
    confidence: str
    unresolved_reason: str | None = None

def resolve_treatment_v3(*, rarity: Any, era: Any, printing_type: Any=None,
                         special_type: Any=None, edition: Any=None) -> TreatmentV3:
    raw=key(rarity); era_name=str(era or "")
    if not raw:
        reason="unsupported_legacy_structure" if era_name in {"Other","EX","XY"} else "missing_source_metadata"
        return TreatmentV3(None,None,(),"UNSUPPORTED_LEGACY_STRUCTURE" if reason.startswith("unsupported") else "MISSING_SOURCE_METADATA","none",reason)
    mapping=BASE.get(raw) or LEGACY.get(raw)
    if raw == "rare_secret":
        attrs=SECRET_BY_ERA.get(era_name,["subset_specialty","vintage_specialty"])
        mapping=(f"{key(era_name)}__secret_rare",attrs)
    if not mapping:
        return TreatmentV3(raw,None,(),"GENUINELY_AMBIGUOUS","none","unknown_era_local_label")
    treatment,attrs=mapping; attrs=set(attrs)
    finish=key(printing_type); special=key(special_type); edition_key=key(edition)
    if finish in {"holo","holofoil"}: attrs.add("holo")
    elif finish in {"reverse","reverse_holo"}: attrs.add("reverse_holo")
    if special in {"poke_ball","pokeball","master_ball","masterball"}: attrs.update(("etched_or_special_foil","subset_specialty"))
    elif special and special != "ace_spec": attrs.add("etched_or_special_foil")
    if edition_key == "1st_edition": attrs.add("vintage_specialty")
    resolution="RESOLVED_BY_EXISTING_METADATA" if raw in BASE else "RESOLVED_BY_ERA_MAPPING"
    return TreatmentV3(raw,treatment,tuple(sorted(attrs)),resolution,"high")

def taxonomy_fingerprint(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(",",":"),ensure_ascii=True).encode()).hexdigest()

def as_json(value: TreatmentV3) -> dict[str,Any]: return asdict(value)
