import pytest

from backend.scripts.ebay_d3_matcher_v3 import (
    MATCHER_VERSION, classify_listing, classify_product_object, rule_fingerprint,
)

TARGET = {"card_name":"Houndour", "set_name":"Obsidian Flames", "card_number":"204", "treatment":"illustration_rare"}


@pytest.mark.parametrize("title", [
    "X2 Houndour Illustration Rare 204/197 Obsidian Flames",
    "2X Houndour Illustration Rare 204/197 Obsidian Flames",
    "x 2 Houndour Illustration Rare 204/197 Obsidian Flames",
    "Houndour 204/197 Obsidian Flames 2 cards",
    "Houndour pair of cards 204/197 Obsidian Flames",
    "Houndour set of 2 cards 204/197 Obsidian Flames",
    "Houndour 204/197 Obsidian Flames 2-pack cards",
    "Houndour 204/197 Obsidian Flames 4x playset",
])
def test_contextual_multiplicity_never_reaches_high(title):
    found = classify_listing(TARGET, {"title":title, "condition":"Ungraded"})
    assert found["identity_state"] == "REJECTED" and found["product_object"]["state"] == "MULTI_CARD_OFFER"


@pytest.mark.parametrize("listing", [
    {"title":"Houndour 204/197 Obsidian Flames PSA 10", "condition":"Ungraded"},
    {"title":"Houndour 204/197 Obsidian Flames", "condition":"Graded"},
    {"title":"Houndour 204/197 Obsidian Flames", "condition":"Ungraded", "conditionId":"2750"},
    {"title":"Houndour 204/197 Obsidian Flames", "condition":"Ungraded", "aspects":[{"name":"Professional Grader", "values":["BGS"]}]},
    {"title":"Houndour 204/197 Obsidian Flames CGC 9", "condition":"Ungraded"},
    {"title":"Houndour 204/197 Obsidian Flames SGC 10", "condition":"Ungraded"},
])
def test_any_affirmative_graded_evidence_rejects_raw_authority(listing):
    found = classify_listing(TARGET, listing)
    assert found["identity_state"] == "REJECTED" and found["product_object"]["state"] == "GRADED_CARD"


def test_d2_0310_is_documented_image_only_risk_not_fabricated_detection():
    listing = {"title":"Charizard EX #234/091 NM Paldean Fates Pokemon Card", "condition":"Ungraded", "conditionId":"4000", "aspects":[]}
    assert classify_product_object(listing)["state"] == "SINGLE_RAW_CARD"


def test_collector_number_containing_two_is_not_multiplicity():
    found = classify_listing(TARGET, {"title":"Houndour 204/197 Obsidian Flames Illustration Rare", "condition":"Ungraded"})
    assert found["identity_state"] == "HIGH_CONFIDENCE"


def test_legitimate_case_fresh_single_card_is_not_accessory():
    found = classify_listing(TARGET, {"title":"Houndour 204/197 Obsidian Flames Illustration Rare case fresh", "condition":"Ungraded"})
    assert found["identity_state"] == "HIGH_CONFIDENCE"


@pytest.mark.parametrize(("title","state"), [
    ("Houndour 204/197 Extended Art Custom Case", "CARD_ACCESSORY"),
    ("Obsidian Flames Choose Your Card Houndour", "MULTI_CARD_OFFER"),
    ("Obsidian Flames Pick Your Card Houndour", "MULTI_CARD_OFFER"),
])
def test_accessory_and_selectable_offers_are_rejected(title,state):
    found=classify_product_object({"title":title,"condition":"Ungraded"})
    assert found["state"]==state


@pytest.mark.parametrize(("title","reason"), [
    ("Houndour 205/197 Obsidian Flames Illustration Rare", "WRONG_CARD_NUMBER"),
    ("Houndour 204/197 Obsidian Flames Reverse Holo", "WRONG_VARIANT"),
    ("Houndour 204/197 Obsidian Flames Illustration Rare Japanese", "WRONG_LANGUAGE"),
])
def test_identity_protections_are_preserved(title,reason):
    found=classify_listing(TARGET,{"title":title,"condition":"Ungraded"})
    assert found["identity_state"]=="REJECTED" and found["reason"]==reason


def test_version_and_fingerprint_are_stable_shape():
    assert MATCHER_VERSION=="index_fair_value_ebay_d3_v3"
    assert len(rule_fingerprint())==64
