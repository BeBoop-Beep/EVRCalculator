from backend.scripts.ebay_english_price_eligibility_v1 import resolve
from backend.scripts.run_ebay_p4a_english_safety_diagnostic import run as historical_run


def item(language="English", condition="Near mint or better", options=None, shipping="2.50"):
    return {"title": "Pikachu 1/100", "condition": "Ungraded",
            "conditionDescriptors": [{"name": "Card Condition", "values": [{"content": condition}]}] if condition else [],
            "localizedAspects": [{"name": "Language", "value": language}] if language else [],
            "buyingOptions": options if options is not None else ["FIXED_PRICE"],
            "price": {"value": "10.00", "currency": "USD"},
            "shippingOptions": [{"shippingCost": {"value": shipping, "currency": "USD"}}] if shipping is not None else []}


def test_english_nm_fixed_landed_and_free_shipping():
    result = resolve(item(), text_state="HIGH_CONFIDENCE")
    assert result["state"] == "ENGLISH_PRICE_ELIGIBLE" and result["landed_ask_usd"] == "12.50"
    assert resolve(item(shipping="0.00"), text_state="HIGH_CONFIDENCE")["landed_ask_usd"] == "10.00"


def test_language_veto_and_image_positive():
    assert resolve(item("Japanese"), text_state="HIGH_CONFIDENCE", image_state="MATCH")["state"] == "NON_ENGLISH_EXCLUDED"
    assert resolve(item(None), text_state="HIGH_CONFIDENCE")["state"] == "LANGUAGE_UNRESOLVED"
    assert resolve(item(None), text_state="HIGH_CONFIDENCE", image_state="MATCH")["state"] == "ENGLISH_PRICE_ELIGIBLE"
    assert resolve(item(), text_state="HIGH_CONFIDENCE", image_state="MISMATCH")["state"] == "IDENTITY_REJECTED"
    assert resolve(item(), text_state="HIGH_CONFIDENCE", ocr_v3_state="JAPANESE_MISMATCH")["state"] == "NON_ENGLISH_EXCLUDED"


def test_condition_and_buying_format_fail_closed():
    assert resolve(item(condition=None), text_state="HIGH_CONFIDENCE")["state"] == "CONDITION_UNRESOLVED"
    assert resolve(item(condition="Heavily played (Poor)"), text_state="HIGH_CONFIDENCE")["state"] == "CONDITION_EXCLUDED"
    assert resolve(item(options=["AUCTION"]), text_state="HIGH_CONFIDENCE")["state"] == "BUYING_FORMAT_EXCLUDED"
    assert resolve(item(options=["AUCTION", "FIXED_PRICE"]), text_state="HIGH_CONFIDENCE")["state"] == "BUYING_FORMAT_EXCLUDED"
    assert resolve(item(shipping=None), text_state="HIGH_CONFIDENCE")["state"] == "BUYING_FORMAT_EXCLUDED"
    assert resolve(item(), text_state="REJECTED")["state"] == "IDENTITY_REJECTED"


def test_retained_human_review_has_no_known_foreign_accept():
    result = historical_run()
    for cohort in result["cohorts"].values():
        rule = cohort["rules"]["either"]
        assert rule["human_no_accepted"] == 0
        assert rule["human_non_english_accepted"] == 0
