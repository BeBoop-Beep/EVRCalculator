import json
from datetime import date

from backend.scripts.select_ebay_daily_pricing_targets import plan
from backend.scripts.index_fair_value_ebay_evidence_collector import (
    BrowseHTTP, Collector, CollectorConfig, RunState, TokenProvider, normalize_listing, pricing_eligibility,
)


def _card(cid, rarity="Rare", **extra):
    return {"id": cid, "set_id": "s", "name": f"Card {cid}", "number": cid,
            "rarity": rarity, "catalog_role": "main", "canonical_review_status": "approved",
            "opening_eligible": True, "set_value_eligible": True, **extra}


def test_priority_gap_staleness_rotation_and_budget():
    cards = [_card("missing"), _card("stale"), _card("fresh"), _card("common", "Common")]
    prices = [{"canonical_card_id": "stale", "market_price": 8, "captured_at": "2026-08-01"},
              {"canonical_card_id": "fresh", "market_price": 8, "captured_at": "2026-09-18"}]
    args = (cards, [{"id": "s", "name": "Set", "era_id": "e"}], prices, date(2026, 9, 19))
    result = plan(*args, ceiling=18)
    assert result == plan(*args, ceiling=18)
    assert result["estimated_requests"] <= 18
    assert result["canonical_card_ids"][:2] == ["missing", "stale"]
    assert "common" not in result["canonical_card_ids"]
    assert len(result["canonical_card_ids"]) == len(set(result["canonical_card_ids"]))
    assert "ROTATIONAL_COVERAGE" in plan(*args, ceiling=18)["cards"][-1]["priority_reasons"]


def test_recent_event_mover_priority():
    cards = [_card("mover")]
    prices = [{"canonical_card_id": "mover", "card_variant_id": "v", "market_price": 30,
               "captured_at": "2026-09-18"}]
    events = [{"id": "1", "card_variant_id": "v", "effective_date": "2026-09-01", "market_price": 20},
              {"id": "2", "card_variant_id": "v", "effective_date": "2026-09-18", "market_price": 30}]
    row = plan(cards, [{"id": "s", "name": "Set"}], prices, date(2026, 9, 19),
               recent_events=events)["cards"][0]
    assert "RECENT_MEANINGFUL_MOVER" in row["priority_reasons"]
    assert "RECENT_HIGH_VOLATILITY" in row["priority_reasons"]


def test_raw_landed_ask_and_language_states(monkeypatch):
    target = {"canonical_card_id": "x", "card_name": "Pikachu", "card_number": "1", "set_name": "Set"}
    item = {"itemId": "i", "title": "Pikachu 1 Set", "price": {"value": "10.10", "currency": "USD"},
            "shippingOptions": [{"shippingCost": {"value": "2.20", "currency": "USD"}}]}
    raw = normalize_listing(item, query={"query": "q", "formulation": "primary"}, target=target, run_id="r", page=1)
    assert raw["evidence_kind"] == "active_ask" and raw["landed_ask_value"] == 12.3
    monkeypatch.setattr("backend.scripts.index_fair_value_ebay_evidence_collector.pricing_matcher.classify_listing",
                        lambda *_: {"identity_state": "HIGH_CONFIDENCE"})
    assert pricing_eligibility(target, raw)["eligibility_status"] == "LANGUAGE_UNRESOLVED"
    raw["raw_item_summary"]["localizedAspects"] = [{"name": "Language", "value": "English"}]
    assert pricing_eligibility(target, raw)["eligibility_status"] == "ENGLISH_ELIGIBLE"
    raw["raw_item_summary"]["localizedAspects"][0]["value"] = "Japanese"
    assert pricing_eligibility(target, raw)["eligibility_status"] == "NON_ENGLISH_EXCLUDED"
    monkeypatch.setattr("backend.scripts.index_fair_value_ebay_evidence_collector.pricing_matcher.classify_listing",
                        lambda *_: {"identity_state": "REJECTED"})
    assert pricing_eligibility(target, raw)["eligibility_status"] == "IDENTITY_REJECTED"


def test_pricing_collector_resume_is_artifact_only(tmp_path, monkeypatch):
    monkeypatch.setattr("backend.scripts.index_fair_value_ebay_evidence_collector.RUNS_DIR", tmp_path)
    target = {"pricing_target": True, "canonical_card_id": "x", "card_name": "Pikachu",
              "card_number": "1", "set_name": "Set"}
    replies = iter([{"itemSummaries": [{"itemId": "i", "title": "Pikachu 1 Set"}]}, {"itemSummaries": []}])
    http = BrowseHTTP(TokenProvider({}, fetch=lambda: "token"), CollectorConfig(max_requests_per_run=2),
                      opener=lambda *_: next(replies))
    collector = Collector(http, CollectorConfig(max_requests_per_run=2))
    state = RunState.new("r", [target], CollectorConfig(max_requests_per_run=2))
    collector.run(state, [target])
    state.save()
    count = len(state.raw_evidence_path().read_text().splitlines())
    collector.run(RunState.load("r"), [target])
    assert len(state.raw_evidence_path().read_text().splitlines()) == count
    assert not list(tmp_path.glob("*.sql"))
