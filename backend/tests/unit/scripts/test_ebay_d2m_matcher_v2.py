from collections import Counter
import pytest
from backend.scripts.ebay_d2m_matcher_v2 import (
    MATCHER_VERSION, classify_listing, classify_product_object, rule_fingerprint,
)
from backend.scripts.ebay_gold_access import load_partition
from backend.scripts.ebay_gold_review_server import read_history, reconstruct_effective_state

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
    assert rule_fingerprint()=="b5b1a1b32df3a93b00d73741be478b68ffd1e8d432c529e3b0aec3072468354b"
