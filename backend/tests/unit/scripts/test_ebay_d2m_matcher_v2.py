from collections import Counter
import json
from pathlib import Path
import pytest
from backend.scripts.ebay_d2m_matcher_v2 import (
    MATCHER_VERSION, classify_listing, classify_product_object, rule_fingerprint,
)
from backend.scripts.ebay_gold_access import load_partition
from backend.scripts.ebay_gold_review_server import read_history, reconstruct_effective_state

OUT=Path(__file__).resolve().parents[3]/"artifacts/index_fair_value"
def artifact(name):
    return json.loads((OUT/name).read_text(encoding="utf-8"))

def target(**changes):
    value={"card_name":"Furret","set_name":"Journey Together","card_number":"168",
           "treatment":"illustration_rare"}
    value.update(changes);return value
def listing(title,condition="Ungraded"):
    return {"title":title,"condition":condition,"aspects":[]}

@pytest.mark.parametrize("title",[
 "Furret 168/159 Journey Together Extended Art Custom Case",
 "Furret 168/159 Journey Together Extended Artwork Case",
 "Furret acrylic display case 168/159",
 "Furret card holder frame 168/159",
 "Furret framed display 168/159",
 "Furret binder insert 168/159",
 "Furret card sleeves 168/159",
 "Furret card protector 168/159",
 "Furret card stand 168/159",
 "Furret deck box 168/159",
 "Furret top loader 168/159",
])
def test_accessory_product_ontology_precedes_identity(title):
    result=classify_listing(target(),listing(title))
    assert result["product_object"]["state"]=="CARD_ACCESSORY"
    assert result["identity_state"]=="REJECTED"

def test_benign_case_language_does_not_trigger_accessory():
    result=classify_listing(
      target(),listing("Furret 168/159 Journey Together Illustration Rare case fresh NM"))
    assert result["product_object"]["state"]=="SINGLE_RAW_CARD"
    assert result["identity_state"]=="HIGH_CONFIDENCE"

@pytest.mark.parametrize("phrase",["Choose Your Card","You Pick","multi variation","card(s)"])
def test_selectable_or_multi_card_offer_is_never_high(phrase):
    result=classify_listing(target(),listing(f"Journey Together {phrase}"))
    assert result["product_object"]["state"]=="MULTI_CARD_OFFER"
    assert result["identity_state"]=="REJECTED"

def test_valid_raw_exact_listing_is_high():
    result=classify_listing(target(),listing(
      "Furret 168/159 Journey Together Illustration Rare Pokemon Card NM"))
    assert result["product_object"]["state"]=="SINGLE_RAW_CARD"
    assert result["identity_state"]=="HIGH_CONFIDENCE"
    assert result["matcher_version"]==MATCHER_VERSION

@pytest.mark.parametrize(("title","reason"),[
 ("Furret 168/159 Journey Together PSA 10","GRADED_CARD"),
 ("Furret 169/159 Journey Together IR","WRONG_CARD_NUMBER"),
 ("Furret 168/159 Temporal Forces IR","WRONG_SET"),
 ("Furret 168/159 Journey Together reverse holo","WRONG_VARIANT"),
 ("Furret 168/159 Journey Together IR Japanese","WRONG_LANGUAGE"),
 ("Furret card lot 168/159 Journey Together","MULTI_CARD_OFFER"),
 ("Furret booster box 168/159 Journey Together","SEALED_TCG_PRODUCT"),
])
def test_existing_rejection_classes_do_not_regress(title,reason):
    result=classify_listing(target(),listing(title))
    assert result["identity_state"]=="REJECTED"
    assert result["reason"]==reason

def test_expanded_development_has_zero_catastrophic_high_rows():
    events=read_history();bad=[];distribution=Counter()
    prohibited={"GRADED","WRONG_CARD_NUMBER","SEALED_OR_ACCESSORY","LOT_OR_BUNDLE",
      "RELATED_BUT_WRONG_VARIANT","WRONG_LANGUAGE","WRONG_SET"}
    for partition in ("DEVELOPMENT","VALIDATION"):
        rows=load_partition(partition,purpose="human_review")
        state=reconstruct_effective_state(events,partition,"Donny",
                                           [row["benchmark_row_id"] for row in rows])
        for row in rows:
            gold=state["labels"][row["benchmark_row_id"]]["label"];distribution[gold]+=1
            result=classify_listing(
              {"card_name":row["target_card_name"],"set_name":row["target_set_name"],
               "card_number":row["target_card_number"],"treatment":row["target_treatment"]},
              listing(row["listing_title"],row["condition"]))
            if gold in prohibited and result["identity_state"]=="HIGH_CONFIDENCE":
                bad.append((partition,row["benchmark_row_id"],gold))
    assert bad==[]
    assert distribution["EXACT_TARGET_MATCH"]==447
    assert distribution["AMBIGUOUS"]==18

def test_v2_fingerprint_is_stable():
    assert rule_fingerprint()=="a2ac052891df2745f2a2dde8b615a5ccbf1ef23a777eb2a0310e35aef94f6d5e"

def test_expanded_manifest_has_exact_effective_corpus_contract():
    manifest=artifact("ebay_d2m_v2_expanded_development_manifest.json")
    assert (manifest["rows"],manifest["positive_count"],manifest["negative_count"],
            manifest["ambiguous_count"],manifest["binary_denominator"])==(700,447,235,18,682)
    assert len(manifest["membership_and_label_fingerprint"])==64
    assert manifest["final_blind_used"] is False

def test_expanded_metrics_meet_diagnostic_targets_with_zero_high_errors():
    metrics=artifact("ebay_d2m_v2_expanded_metrics.json")
    assert metrics["high"]["accepted"]==metrics["high"]["tp"]==298
    assert metrics["high"]["fp"]==0
    assert metrics["high"]["wilson_95"][0]>=.98
    assert metrics["high"]["card_coverage"]>=.80
    assert metrics["medium"]["authority"]=="DIAGNOSTIC_ONLY"
    assert artifact("ebay_d2m_v2_coverage_analysis.json")["cards_still_lacking_high"]==11

def test_all_accessory_examples_feed_general_ontology():
    ontology=artifact("ebay_d2m_v2_accessory_ontology.json")
    assert len(ontology["expanded_development_examples"])==19
    assert all(not row["card_itself_sold"] for row in ontology["expanded_development_examples"])
    assert "Extended Art Custom Case" not in ontology["families"].values()

def test_final_freeze_manifest_is_complete_and_guard_remains_closed_without_it():
    freeze=artifact("ebay_d2m_v2_final_freeze_manifest.json")
    assert freeze["matcher_version"]==MATCHER_VERSION
    assert freeze["matcher_fingerprint"]==rule_fingerprint()
    assert freeze["frozen_commit"]=="3d70f0032fbc7e39d759a0e13669c1c6bc475367"
    assert freeze["logic_frozen"] is True
    assert freeze["final_blind_rows_from_original_manifest"]==350
    assert freeze["final_blind_labels_accessed"] is False
    with pytest.raises(PermissionError):
        load_partition("FINAL_BLIND_TEST")
