from backend.scripts.index_fair_value_ebay_evidence_quality import EvidenceQuality, assess_evidence_quality


def listing(price=10.0, seller="s1", condition="Ungraded"):
    return {"price_value": price, "seller_username": seller, "condition": condition}


def many_listings(n, sellers=None, prices=None, condition="Ungraded"):
    sellers = sellers or [f"s{i}" for i in range(n)]
    prices = prices or [10.0] * n
    return [listing(price=prices[i % len(prices)], seller=sellers[i % len(sellers)], condition=condition) for i in range(n)]


# 15. evidence-quality status (typed, not probabilistic)
def test_status_is_typed_enum_not_a_percentage():
    result = assess_evidence_quality(many_listings(20), matcher_certified=True)
    assert isinstance(result.status, EvidenceQuality)
    assert result.status.value in {"INSUFFICIENT", "LOW", "MEDIUM", "HIGH"}


# 16. quality cap for unknown condition
def test_quality_capped_when_condition_unknown():
    listings = many_listings(20, condition=None)
    result = assess_evidence_quality(listings, matcher_certified=True)
    assert result.status in (EvidenceQuality.LOW, EvidenceQuality.INSUFFICIENT)
    assert any("condition" in c for c in result.caps_applied)


# 17. quality cap for ambiguous identity
def test_quality_capped_for_high_ambiguous_rate():
    listings = many_listings(20)
    result = assess_evidence_quality(listings, matcher_certified=True, ambiguous_count=15, rejected_count=0)
    assert result.status == EvidenceQuality.LOW
    assert any("ambiguous" in c for c in result.caps_applied)


# 18. quality cap for too-few observations
def test_insufficient_when_too_few_accepted_listings():
    result = assess_evidence_quality(many_listings(2), matcher_certified=True)
    assert result.status == EvidenceQuality.INSUFFICIENT


# 19. quality cap for excessive dispersion
def test_quality_not_high_when_price_dispersion_extreme():
    listings = many_listings(20, prices=[1.0, 500.0])
    result = assess_evidence_quality(listings, matcher_certified=True)
    assert result.status != EvidenceQuality.HIGH


def test_quality_not_high_when_seller_concentration_extreme():
    listings = many_listings(20, sellers=["dominant_seller"])
    result = assess_evidence_quality(listings, matcher_certified=True)
    assert result.status != EvidenceQuality.HIGH


def test_uncertified_matcher_caps_at_medium():
    listings = many_listings(20)
    result = assess_evidence_quality(listings, matcher_certified=False)
    assert result.status != EvidenceQuality.HIGH
    assert any("certified" in c for c in result.caps_applied)


def test_certified_matcher_with_clean_evidence_can_reach_high():
    listings = many_listings(20)
    result = assess_evidence_quality(listings, matcher_certified=True)
    assert result.status == EvidenceQuality.HIGH


# 20. active-ask semantics preserved (no probability-of-sale language anywhere in the module)
def test_no_probability_of_sale_language_leaks_into_result():
    result = assess_evidence_quality(many_listings(20), matcher_certified=True)
    rendered = str(result.status.value)
    assert "%" not in rendered
    assert "sold" not in rendered.lower()
    assert "probability" not in rendered.lower()
