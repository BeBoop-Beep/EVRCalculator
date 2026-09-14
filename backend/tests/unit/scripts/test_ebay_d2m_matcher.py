import csv
import json
from pathlib import Path
import pytest
from backend.scripts.ebay_d2m_matcher import (
    MATCHER_VERSION, classify_listing, number_evidence, rule_fingerprint, set_evidence,
)
from backend.scripts.ebay_gold_access import load_partition
from backend.scripts.ebay_gold_review_server import read_history, reconstruct_effective_state

OUT=Path(__file__).resolve().parents[3]/"artifacts/index_fair_value"

def match(title,condition="Ungraded",**target):
    base={"card_name":"Penny","set_name":"Scarlet and Violet Base Set",
          "card_number":"252","treatment":"special_illustration_rare"}
    base.update(target)
    return classify_listing(base,{"title":title,"condition":condition})

@pytest.mark.parametrize("marker",["PSA 10","BGS 9.5","CGC 9","SGC 8","ACE 10","TAG 9","graded 8"])
def test_graded_markers_reject(marker):
    assert match(f"Penny 252/198 SIR SV01 {marker}")["reason"]=="GRADED"

def test_condition_field_rejects_slab_even_without_title_marker():
    assert match("Penny 252/198 SIR SV01",condition="Graded")["reason"]=="GRADED"

def test_number_parser_matches_formats_and_rejects_substring_collision():
    assert number_evidence("Card 238/191","238")["state"]=="MATCH"
    assert number_evidence("Card #0238","238")["state"]=="MATCH"
    assert number_evidence("Card 1238","238")["state"]=="ABSENT"
    assert number_evidence("Card 239/198","252")["state"]=="CONFLICT"
    assert number_evidence("Cards 277/217 and 276/217","277")["state"]=="MULTIPLE"

def test_set_alias_exact_absent_and_conflict():
    assert set_evidence("Penny SVI 252/198","Scarlet and Violet Base Set")["state"]=="ALIAS"
    assert set_evidence("Penny 252/198","Scarlet and Violet Base Set")["state"]=="ABSENT"
    assert set_evidence("Penny 252/198 Temporal Forces","Scarlet and Violet Base Set")["state"]=="CONFLICT"

@pytest.mark.parametrize("parallel",["reverse holo","Pokeball","stamped","Pokemon Center"])
def test_wrong_base_parallel_rejects(parallel):
    result=match(f"Grubbin 18/162 Temporal Forces {parallel}",
      card_name="Grubbin",set_name="Temporal Forces",card_number="18",treatment="common")
    assert result["reason"]=="WRONG_VARIANT"

@pytest.mark.parametrize("word",["Japanese","Korean","Chinese","French"])
def test_non_english_rejects(word):
    assert match(f"Penny 252/198 SIR SV01 {word}")["reason"]=="WRONG_LANGUAGE"

@pytest.mark.parametrize("phrase",["lot of 3","playset","choose your card","you pick"])
def test_lot_bundle_rejects(phrase):
    assert match(f"Penny 252/198 SIR SV01 {phrase}")["reason"]=="LOT_OR_BUNDLE"

@pytest.mark.parametrize("phrase",["extended artwork case","booster pack","binder","blanket"])
def test_sealed_accessory_rejects(phrase):
    assert match(f"Penny 252/198 SIR SV01 {phrase}")["reason"]=="SEALED_OR_ACCESSORY"

def test_missing_set_with_strong_name_number_variant_is_high():
    assert match("Penny 252/198 Special Illustration Rare")["identity_state"]=="HIGH_CONFIDENCE"

def test_missing_number_is_ambiguous_not_high():
    assert match("Penny Special Illustration Rare Scarlet Violet Base Set")["identity_state"]=="AMBIGUOUS"

def test_base_parallel_unspecified_is_medium():
    result=match("Grubbin 18/162 Temporal Forces Common",
      card_name="Grubbin",set_name="Temporal Forces",card_number="18",treatment="common")
    assert result["identity_state"]=="MEDIUM_CONFIDENCE"

def test_identity_and_raw_condition_are_separate():
    result=match("Penny 252/198 SIR SV01 heavily played")
    assert result["identity_state"]=="HIGH_CONFIDENCE"
    assert result["condition_state"]=="RAW_CONDITION_INELIGIBLE"

def test_exact_good_case_is_high_and_versioned():
    result=match("Penny 252/198 Special Illustration Rare SVI Near Mint")
    assert result["identity_state"]=="HIGH_CONFIDENCE"
    assert result["matcher_version"]==MATCHER_VERSION
    assert len(rule_fingerprint())==64

def test_frozen_development_benchmark_meets_preregistered_high_gate():
    report=json.loads((OUT/"ebay_d2m_development_benchmark.json").read_text(encoding="utf-8"))
    assert report["high"]["precision"]==1
    assert report["high"]["wilson_95"][0]>=.98
    assert report["high"]["card_coverage"]>=.80
    assert report["high"]["non_positive_rows"]==[]

def test_validation_and_final_remain_protected_from_matcher_development():
    with pytest.raises(PermissionError):
        load_partition("VALIDATION")
    with pytest.raises(PermissionError):
        load_partition("FINAL_BLIND_TEST")

def test_all_development_negative_classes_have_zero_high_acceptance():
    rows=load_partition("DEVELOPMENT",purpose="matcher_development")
    state=reconstruct_effective_state(
        read_history(),"DEVELOPMENT","Donny",
        [row["benchmark_row_id"] for row in rows],
    )
    prohibited={"GRADED","WRONG_LANGUAGE","LOT_OR_BUNDLE","SEALED_OR_ACCESSORY",
                "WRONG_SET","WRONG_CARD_NUMBER","RELATED_BUT_WRONG_VARIANT"}
    high_bad=[]
    for row in rows:
        result=classify_listing(
            {"card_name":row["target_card_name"],"set_name":row["target_set_name"],
             "card_number":row["target_card_number"],"treatment":row["target_treatment"]},
            {"title":row["listing_title"],"condition":row["condition"],
             "aspects":row["localized_aspects_json"]},
        )
        gold=state["labels"][row["benchmark_row_id"]]["label"]
        if result["identity_state"]=="HIGH_CONFIDENCE" and gold in prohibited:
            high_bad.append((row["benchmark_row_id"],gold))
    assert high_bad==[]

def test_second_review_queue_is_blind_to_price_and_matcher_verdict():
    with (OUT/"ebay_d2m_second_review_queue.csv").open(encoding="utf-8",newline="") as handle:
        reader=csv.DictReader(handle)
        assert "price_json" not in reader.fieldnames
        assert "gold_label" not in reader.fieldnames
        assert "identity_state" not in reader.fieldnames
        assert len(list(reader))>=17
