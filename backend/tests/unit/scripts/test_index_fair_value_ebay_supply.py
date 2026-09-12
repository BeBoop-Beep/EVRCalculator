import pytest
from backend.scripts.index_fair_value_ebay_supply import aggregate, build_query, classify_listing, normalize, number_forms

CARD={"card_name":"Pikachu ex","card_number":"238/191","set_name":"Surging Sparks","printing_type":"special illustration rare","edition":None}

def test_query_is_deterministic_and_price_blind():
    assert build_query(CARD) == build_query(CARD)
    assert build_query(CARD)["query"] == "Pikachu ex 238/191 Surging Sparks Pokemon card"
    assert "price" not in build_query(CARD)["query"].lower()

def test_normalization_and_number_forms():
    assert normalize("Pokemon / EX") == "pokemon ex"
    assert {"238", "238 191"} <= number_forms("238/191")

@pytest.mark.parametrize("title,state", [
    ("Pikachu ex 238/191 Surging Sparks Pokemon Card", "EXACT_MATCH"),
    ("PSA 10 Pikachu ex 238/191 Surging Sparks", "GRADED"),
    ("Lot of 3 Pikachu ex 238/191", "LOT_OR_BUNDLE"),
    ("Japanese Pikachu ex 238/191 Surging Sparks", "NON_ENGLISH"),
    ("Pikachu card sleeves", "ACCESSORY"),
    ("Charizard ex 238/191 Surging Sparks", "WRONG_CARD"),
    ("Pikachu ex 238/191", "LIKELY_MATCH"),
])
def test_matching_rejections_and_ambiguity(title,state):
    assert classify_listing(CARD,{"title":title,"condition":"Ungraded - Near mint or better"})["match_state"] == state

def test_metric_aggregation_and_seller_depth():
    rows=[{"match_state":"EXACT_MATCH","raw_condition_state":"RAW_ELIGIBLE_CONDITION","price":p,"seller_id":s,"buying_options":["FIXED_PRICE"]} for p,s in [(10,"a"),(20,"a"),(30,"b")]]
    out=aggregate(rows)
    assert out["exact_match_listing_count"] == 3
    assert out["unique_seller_count"] == 2
    assert out["median_listing_price"] == 20
    assert out["listing_price_iqr"] == 20

def test_ungraded_and_pack_fresh_are_not_misclassified():
    out=classify_listing(CARD,{"title":"Pikachu ex 238/191 Surging Sparks pack fresh","condition":"Ungraded"})
    assert out["match_state"] == "EXACT_MATCH"
    assert out["raw_condition_state"] == "RAW_ELIGIBLE_CONDITION"
