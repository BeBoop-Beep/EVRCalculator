import hashlib
import json

import pytest

from backend.scripts.index_fair_value_ebay_evidence_collector import (
    BrowseHTTP, BudgetExhausted, CollectorConfig, DailyBrowseLedger, RequestOutcome,
    RunCounters, TokenProvider,
)
from backend.scripts.run_ebay_p4a_adaptive_development import candidate_rank, choose_cohort, collect


def test_candidate_rank_prioritizes_distinct_sellers_not_cheapest(monkeypatch):
    monkeypatch.setattr("backend.scripts.run_ebay_p4a_adaptive_development.ebay_d3_matcher_v5.classify_listing",
                        lambda *_: {"identity_state": "HIGH_CONFIDENCE"})
    rows = [{"itemId": str(i), "title": "Card", "seller": {"username": seller},
             "price": {"value": price, "currency": "USD"},
             "buyingOptions": ["FIXED_PRICE"],
             "shippingOptions": [{"shippingCost": {"value": "1", "currency": "USD"}}]}
            for i, seller, price in [(1, "a", "9"), (2, "a", "10"), (3, "b", "12"), (4, "c", "11")]]
    ranked = candidate_rank(rows, {"tcgplayer_market_price": 10})
    assert [row["item"]["itemId"] for row in ranked[:3]] == ["2", "4", "3"] or [row["item"]["itemId"] for row in ranked[:3]] == ["1", "4", "3"]
    assert ranked[-1]["seller"] == "a"


def test_adaptive_hydration_stops_at_three_eligible_sellers(tmp_path, monkeypatch):
    monkeypatch.setattr("backend.scripts.run_ebay_p4a_adaptive_development.OUT", tmp_path)
    monkeypatch.setattr("backend.scripts.run_ebay_p4a_adaptive_development.ebay_d3_matcher_v5.classify_listing",
                        lambda *_: {"identity_state": "HIGH_CONFIDENCE"})
    card = {"canonical_card_id": "card", "card_name": "Card", "card_number": "1",
            "set_name": "Set", "era_id": "era", "set_id": "set", "tcgplayer_market_price": 10}
    manifest = {"market_date": "2026-09-19", "cards": [card]}
    manifest["selector_fingerprint"] = hashlib.sha256(json.dumps(manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
    search = {"itemSummaries": [{"itemId": str(i), "seller": {"username": str(i)},
              "price": {"value": "10", "currency": "USD"}, "buyingOptions": ["FIXED_PRICE"]} for i in range(8)]}

    class FakeHttp:
        def get(self, url, counters):
            counters.requests_attempted += 1
            counters.requests_successful += 1
            counters.remaining_run_budget -= 1
            if "item_summary/search" in url:
                return RequestOutcome(ok=True, data=search)
            return RequestOutcome(ok=True, data={"title": "Card 1 Set", "itemId": url.rsplit("/", 1)[-1],
                "localizedAspects": [{"name": "Language", "value": "English"}],
                "condition": "Ungraded", "conditionDescriptors": [{"name": "Card Condition", "values": [{"content": "Near mint or better"}]}],
                "buyingOptions": ["FIXED_PRICE"], "price": {"value": "10", "currency": "USD"},
                "shippingOptions": [{"shippingCost": {"value": "0", "currency": "USD"}}]})

    result = collect(manifest, target_count=1, request_cap=20, http=FakeHttp())
    assert result["requests_attempted"] == 4
    assert result["targets"][0]["eligible_seller_count"] == 3
    assert result["targets"][0]["detail_calls"] == 3


def test_real_manifest_cohort_is_stratified():
    from pathlib import Path
    manifest = json.loads(Path("backend/artifacts/pricing/ebay_daily_pricing_targets_2026-09-19.json").read_text(encoding="utf8"))
    cards = choose_cohort(manifest, 30)
    assert len(cards) == len({card["canonical_card_id"] for card in cards}) == 30
    assert {"missing", "low", "mid", "high"} <= {"missing" if card["tcgplayer_market_price"] is None else "low" if card["tcgplayer_market_price"] < 20 else "mid" if card["tcgplayer_market_price"] < 100 else "high" for card in cards}


def test_shared_daily_ledger_blocks_repeat_run(tmp_path):
    path = tmp_path / "calls.sqlite3"
    ledger_a = DailyBrowseLedger(path, limit=2)
    ledger_b = DailyBrowseLedger(path, limit=2)
    opener_calls = []
    http_a = BrowseHTTP(TokenProvider({}, fetch=lambda: "token"), CollectorConfig(max_requests_per_run=10),
                        opener=lambda *_: opener_calls.append(1) or {}, daily_ledger=ledger_a)
    http_b = BrowseHTTP(TokenProvider({}, fetch=lambda: "token"), CollectorConfig(max_requests_per_run=10),
                        opener=lambda *_: opener_calls.append(1) or {}, daily_ledger=ledger_b)
    http_a.get("https://example.com", RunCounters(remaining_run_budget=10))
    http_b.get("https://example.com", RunCounters(remaining_run_budget=10))
    with pytest.raises(BudgetExhausted):
        http_b.get("https://example.com", RunCounters(remaining_run_budget=10))
    assert len(opener_calls) == 2
