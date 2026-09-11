import json
from pathlib import Path
from backend.desirability.treatment_taxonomy_v3 import resolve_treatment_v3,taxonomy_fingerprint
ROOT=Path(__file__).resolve().parents[4]

def test_modern_semantics_are_composable():
    x=resolve_treatment_v3(rarity="Special Illustration Rare",era="Scarlet and Violet")
    assert x.treatment_key=="special_illustration_rare" and "alternate_artwork" in x.semantic_attributes

def test_historical_labels_are_era_local():
    assert resolve_treatment_v3(rarity="Rare Secret",era="Black and White").treatment_key != resolve_treatment_v3(rarity="Rare Secret",era="Sword and Shield").treatment_key
    assert "shiny" in resolve_treatment_v3(rarity="Rare Secret",era="Black and White").semantic_attributes
    assert "gold_or_gilded" in resolve_treatment_v3(rarity="Rare Secret",era="Sword and Shield").semantic_attributes

def test_known_historical_classes_and_normalization():
    cases={"Rare Holo LV.X":"rare_holo_lv_x","Rare Holo Star":"gold_star","Rare Prime":"prime","LEGEND":"legend","Rare BREAK":"break","Amazing Rare":"amazing_rare","Radiant Rare":"radiant_rare"}
    for raw,expected in cases.items(): assert resolve_treatment_v3(rarity=raw,era="XY").treatment_key==expected

def test_finish_and_edition_do_not_become_global_rarity_equivalence():
    x=resolve_treatment_v3(rarity="Common",era="Base/WOTC",printing_type="reverse-holo",edition="1st-edition")
    assert x.treatment_key=="common" and {"reverse_holo","vintage_specialty"} <= set(x.semantic_attributes)

def test_unknown_missing_and_legacy_are_explicit():
    assert resolve_treatment_v3(rarity="Mystery",era="XY").resolution=="GENUINELY_AMBIGUOUS"
    assert resolve_treatment_v3(rarity=None,era="Black and White").resolution=="MISSING_SOURCE_METADATA"
    assert resolve_treatment_v3(rarity=None,era="Other").resolution=="UNSUPPORTED_LEGACY_STRUCTURE"

def test_fingerprint_is_deterministic():
    assert taxonomy_fingerprint({"b":2,"a":1})==taxonomy_fingerprint({"a":1,"b":2})

def test_live_census_accounts_for_every_v7_card_without_guessing():
    x=json.loads((ROOT/"backend/artifacts/treatment/treatment_coverage_current.json").read_text())
    assert x["eligibleCanonicalCards"]==x["mappedAfter"]+x["unmappedAfter"]
    assert x["unmappedAfter"]==x["legacyUnsupported"]+x["missingSourceMetadata"]+x["ambiguous"]

def test_unresolved_manifest_retains_exact_card_and_variant_identity():
    x=json.loads((ROOT/"backend/artifacts/treatment/treatment_unresolved_manifest.json").read_text())
    assert x["count"]==len(x["rows"])
    assert all(r["canonical_card_id"] and "variant_ids" in r and r["unresolved_reason"] for r in x["rows"])

def test_t2_cohorts_are_price_blind_and_fingerprinted():
    x=json.loads((ROOT/"backend/artifacts/treatment/treatment_t2_research_cohorts.json").read_text())
    assert x["priceDerivedInclusion"] is False
    assert all(len(v["fingerprint"])==64 for v in x["cohortManifest"].values())

def test_comparability_does_not_imply_transitivity():
    x=json.loads((ROOT/"backend/artifacts/treatment/treatment_pairwise_comparability.json").read_text())
    assert "does not authorize transitive" in x["warning"]
    assert {e["status"] for e in x["edges"]} >= {"DIRECTLY_IDENTIFIABLE","LOCALLY_IDENTIFIABLE","CONNECTED_ONLY_THROUGH_INTERMEDIATES","UNSUPPORTED"}
