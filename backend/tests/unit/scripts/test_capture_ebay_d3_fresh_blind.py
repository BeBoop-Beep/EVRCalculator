from backend.scripts.capture_ebay_d3_fresh_blind import canonical_fingerprint, seller_title
from backend.scripts.prepare_ebay_d3_blind_benchmark import SAFE_FIELDS, safe_row, select_cohorts


def rows():
    result=[]
    for card in range(70):
        for number in range(7):
            result.append({"canonical_card_id":f"card-{card}", "card_variant_id":f"variant-{card}",
                           "listing_item_id":f"item-{card}-{number}", "seller_id":f"seller-{number}",
                           "listing_title":f"Card {card} #{number}", "_matcher_state":"HIGH_CONFIDENCE"})
    return result


def test_fingerprints_and_selection_are_deterministic():
    values=rows(); first=select_cohorts(values); second=select_cohorts(list(reversed(values)))
    assert canonical_fingerprint([row["listing_item_id"] for row in first[0]]) == canonical_fingerprint([row["listing_item_id"] for row in second[0]])
    assert len(first[0])==300 and len(first[1])==420


def test_normalized_seller_title_identity_and_missing_seller_policy():
    assert seller_title({"seller_id":" Seller ","listing_title":"Pokemon  CARD"})=="seller|pokemon card"
    assert seller_title({"seller_id":"","listing_title":"Pokemon card"}) is None


def test_human_review_row_has_no_private_or_price_fields():
    source=dict(rows()[0]);source.update({"price_json":"hidden", "matcher_state":"HIGH_CONFIDENCE", "matcher_evidence":"hidden"})
    output=safe_row(source,"D3_BLIND_REVIEW")
    assert set(output)==set(SAFE_FIELDS)
    assert not any(token in key for key in output for token in ("matcher","confidence","price","cohort"))
