import json

import pytest

from backend.scripts.index_fair_value_ebay_evidence_collector import (
    BrowseHTTP,
    BudgetExhausted,
    Collector,
    CollectorConfig,
    RunCounters,
    RunState,
    TokenProvider,
    cohort_fingerprint,
    generate_queries,
    normalize_listing,
    redact,
    run_matcher_on_listing,
    select_cohort,
)

CARD = {
    "canonical_card_id": "card-1",
    "card_variant_id": "variant-1",
    "card_name": "Pikachu ex",
    "card_number": "238/191",
    "set_name": "Surging Sparks",
    "treatment_key": "special illustration rare",
    "printing_type": "special illustration rare",
    "edition": None,
}
CARD_2 = {**CARD, "canonical_card_id": "card-2", "card_variant_id": "variant-2"}


def make_item(item_id, title="Pikachu ex 238/191 Surging Sparks Pokemon Card", price="10.00", condition="Ungraded - Near mint or better"):
    return {
        "itemId": item_id,
        "title": title,
        "itemWebUrl": f"https://ebay.com/{item_id}",
        "image": {"imageUrl": "https://img/x.jpg"},
        "price": {"value": price, "currency": "USD"},
        "shippingOptions": [{"shippingCost": {"value": "2.50", "currency": "USD"}}],
        "condition": condition,
        "conditionId": "4000",
        "seller": {"username": "seller1"},
        "buyingOptions": ["FIXED_PRICE"],
        "itemLocation": {"country": "US"},
    }


class FakeSleep:
    def __init__(self):
        self.calls = []

    def __call__(self, seconds):
        self.calls.append(seconds)


class ScriptedOpener:
    """Replays a scripted sequence of (result-or-exception) per call."""

    def __init__(self, script):
        self._script = list(script)
        self.calls = 0

    def __call__(self, url, token):
        self.calls += 1
        outcome = self._script.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def http_error(status):
    import urllib.error

    return urllib.error.HTTPError("url", status, "err", {}, None)


# 1. deterministic cohort selection
def test_cohort_selection_is_deterministic(tmp_path):
    target_file = tmp_path / "targets.json"
    target_file.write_text(json.dumps([CARD_2, CARD]), encoding="utf-8")
    first = select_cohort(target_file=target_file)
    second = select_cohort(target_file=target_file)
    assert first == second
    assert [c["canonical_card_id"] for c in first] == ["card-1", "card-2"]
    assert cohort_fingerprint(first) == cohort_fingerprint(second)


# 2. query generation
def test_query_generation_centralized_and_provenance_tracked():
    queries = generate_queries(CARD)
    assert queries[0]["formulation"] == "primary"
    assert all("query" in q for q in queries)
    assert queries == generate_queries(CARD)


# 3. item deduplication across queries/pages
def test_dedup_across_queries_and_pages(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "backend.scripts.index_fair_value_ebay_evidence_collector.RUNS_DIR", tmp_path
    )
    responses = [
        {"itemSummaries": [make_item("A"), make_item("B")], "next": None},
        {"itemSummaries": [make_item("B"), make_item("C")], "next": None},
    ]
    opener = ScriptedOpener(responses)
    tokens = TokenProvider({"EBAY_CLIENT_ID": "x", "EBAY_CLIENT_SECRET": "y"}, fetch=lambda: "tok")
    config = CollectorConfig(max_requests_per_run=10, run_matcher=False)
    http = BrowseHTTP(tokens, config, opener=opener, sleep=lambda s: None)
    collector = Collector(http, config)
    state = RunState.new("run1", [CARD], config)
    state = collector.run(state, [CARD])
    raw_lines = state.raw_evidence_path().read_text(encoding="utf-8").splitlines()
    assert len(raw_lines) == 3  # A, B, C -- B captured once despite appearing twice


# 4. next-based pagination, 5. total not controlling pagination
def test_pagination_follows_next_link_not_total(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "backend.scripts.index_fair_value_ebay_evidence_collector.RUNS_DIR", tmp_path
    )
    responses = [
        {"itemSummaries": [make_item("A")], "next": "https://api.ebay.com/next-page", "total": 500},
        {"itemSummaries": [make_item("B")], "next": None, "total": 500},
        {"itemSummaries": [make_item("C")], "next": None, "total": 500},  # second query formulation, single page
    ]
    opener = ScriptedOpener(responses)
    tokens = TokenProvider({}, fetch=lambda: "tok")
    config = CollectorConfig(max_requests_per_run=10, max_pages_per_search=5, run_matcher=False)
    http = BrowseHTTP(tokens, config, opener=opener, sleep=lambda s: None)
    collector = Collector(http, config)
    state = RunState.new("run2", [CARD], config)
    state = collector.run(state, [CARD])
    assert opener.calls == 3  # first formulation stopped when `next` was None, not because of `total`
    raw_lines = state.raw_evidence_path().read_text(encoding="utf-8").splitlines()
    assert len(raw_lines) == 3


# 6. request-budget enforcement, 7. per-run budget exhaustion
def test_run_budget_exhaustion_stops_cleanly_and_marks_deferred(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "backend.scripts.index_fair_value_ebay_evidence_collector.RUNS_DIR", tmp_path
    )
    responses = [{"itemSummaries": [make_item("A")], "next": "https://x/next"}] * 10
    opener = ScriptedOpener(responses)
    tokens = TokenProvider({}, fetch=lambda: "tok")
    config = CollectorConfig(max_requests_per_run=1, max_pages_per_search=5, run_matcher=False)
    http = BrowseHTTP(tokens, config, opener=opener, sleep=lambda s: None)
    collector = Collector(http, config)
    state = RunState.new("run3", [CARD, CARD_2], config)
    state = collector.run(state, [CARD, CARD_2])
    assert state.completed is False
    assert state.requests_attempted == 1
    assert any(t.get("status") == "deferred" for t in state.targets.values())


# 8. per-search page cap
def test_max_pages_per_search_is_respected(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "backend.scripts.index_fair_value_ebay_evidence_collector.RUNS_DIR", tmp_path
    )
    responses = [{"itemSummaries": [make_item(f"A{i}")], "next": "https://x/next"} for i in range(10)]
    opener = ScriptedOpener(responses)
    tokens = TokenProvider({}, fetch=lambda: "tok")
    config = CollectorConfig(max_requests_per_run=100, max_pages_per_search=2, run_matcher=False)
    http = BrowseHTTP(tokens, config, opener=opener, sleep=lambda s: None)
    collector = Collector(http, config)
    state = RunState.new("run4", [CARD], config)
    collector.run(state, [CARD])
    # 2 formulations x 2 pages max = at most 4 calls for this single target
    assert opener.calls <= 4


# 9. listing cap
def test_max_listings_per_target_is_respected(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "backend.scripts.index_fair_value_ebay_evidence_collector.RUNS_DIR", tmp_path
    )
    many_items = [make_item(f"I{i}") for i in range(50)]
    responses = [{"itemSummaries": many_items, "next": None}]
    opener = ScriptedOpener(responses)
    tokens = TokenProvider({}, fetch=lambda: "tok")
    config = CollectorConfig(max_requests_per_run=100, max_listings_per_target=5, run_matcher=False)
    http = BrowseHTTP(tokens, config, opener=opener, sleep=lambda s: None)
    collector = Collector(http, config)
    state = RunState.new("run5", [CARD], config)
    state = collector.run(state, [CARD])
    raw_lines = state.raw_evidence_path().read_text(encoding="utf-8").splitlines()
    assert len(raw_lines) <= 5


# 10. retryable 429
def test_retryable_429_is_retried_then_succeeds():
    sleep = FakeSleep()
    opener = ScriptedOpener([http_error(429), {"itemSummaries": [], "next": None}])
    tokens = TokenProvider({}, fetch=lambda: "tok")
    config = CollectorConfig(retry_budget=3)
    http = BrowseHTTP(tokens, config, opener=opener, sleep=sleep)
    counters = RunCounters(remaining_run_budget=10)
    outcome = http.get("https://x", counters)
    assert outcome.ok is True
    assert counters.retries == 1
    assert len(sleep.calls) == 1


# 11. bounded 5xx retry
def test_5xx_retry_is_bounded_by_retry_budget():
    sleep = FakeSleep()
    opener = ScriptedOpener([http_error(503)] * 10)
    tokens = TokenProvider({}, fetch=lambda: "tok")
    config = CollectorConfig(retry_budget=2)
    http = BrowseHTTP(tokens, config, opener=opener, sleep=sleep)
    counters = RunCounters(remaining_run_budget=100)
    outcome = http.get("https://x", counters)
    assert outcome.ok is False
    assert counters.requests_failed == 1
    assert opener.calls == 3  # 1 initial + 2 retries, then give up


# 12. deterministic 4xx failure
def test_deterministic_4xx_fails_without_retry():
    sleep = FakeSleep()
    opener = ScriptedOpener([http_error(404)])
    tokens = TokenProvider({}, fetch=lambda: "tok")
    config = CollectorConfig(retry_budget=5)
    http = BrowseHTTP(tokens, config, opener=opener, sleep=sleep)
    counters = RunCounters(remaining_run_budget=100)
    outcome = http.get("https://x", counters)
    assert outcome.ok is False
    assert opener.calls == 1
    assert sleep.calls == []


# 13. token refresh behavior
def test_401_triggers_single_token_refresh_and_retry():
    refresh_calls = {"n": 0}

    def fetch():
        refresh_calls["n"] += 1
        return f"tok{refresh_calls['n']}"

    opener = ScriptedOpener([http_error(401), {"itemSummaries": [], "next": None}])
    tokens = TokenProvider({}, fetch=fetch)
    config = CollectorConfig()
    http = BrowseHTTP(tokens, config, opener=opener, sleep=lambda s: None)
    counters = RunCounters(remaining_run_budget=10)
    outcome = http.get("https://x", counters)
    assert outcome.ok is True
    assert refresh_calls["n"] == 2  # initial + forced refresh


# 14. unknown/missing condition preservation
def test_unknown_condition_is_preserved_not_fabricated():
    item = make_item("X")
    del item["condition"]
    del item["conditionId"]
    listing = normalize_listing(item, query={"query": "q", "formulation": "primary"}, target=CARD, run_id="r", page=1)
    assert listing["condition"] is None
    assert listing["condition_id"] is None


# 15. raw listing survives matcher rejection
def test_raw_listing_survives_matcher_rejection(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "backend.scripts.index_fair_value_ebay_evidence_collector.RUNS_DIR", tmp_path
    )
    responses = [{"itemSummaries": [make_item("G", title="PSA 10 Pikachu ex 238/191 Surging Sparks")], "next": None}]
    opener = ScriptedOpener(responses)
    tokens = TokenProvider({}, fetch=lambda: "tok")
    config = CollectorConfig(run_matcher=True)
    http = BrowseHTTP(tokens, config, opener=opener, sleep=lambda s: None)
    collector = Collector(http, config)
    state = RunState.new("run6", [CARD], config)
    state = collector.run(state, [CARD])
    raw_lines = state.raw_evidence_path().read_text(encoding="utf-8").splitlines()
    match_lines = [json.loads(l) for l in state.match_results_path().read_text(encoding="utf-8").splitlines()]
    assert len(raw_lines) == 1  # still captured even though matcher will reject it
    assert match_lines[0]["accepted"] is False


# 16. matcher output versioning
def test_matcher_output_is_versioned_and_separate_from_raw():
    listing = normalize_listing(make_item("Z"), query={"query": "q", "formulation": "primary"}, target=CARD, run_id="r", page=1)
    result = run_matcher_on_listing(CARD, listing)
    assert result["matcher_version"]
    assert "raw_item_summary" not in result


# 17. ambiguous result does not become accepted
def test_ambiguous_result_is_never_accepted():
    listing = normalize_listing(
        make_item("Q", title="Pikachu 238/191"), query={"query": "q", "formulation": "primary"}, target=CARD, run_id="r", page=1
    )
    result = run_matcher_on_listing(CARD, listing)
    if result["match_status"] == "AMBIGUOUS":
        assert result["accepted"] is False


# 18. active ask never becomes transaction
def test_evidence_kind_is_always_active_ask():
    listing = normalize_listing(make_item("Z"), query={"query": "q", "formulation": "primary"}, target=CARD, run_id="r", page=1)
    assert listing["evidence_kind"] == "active_ask"
    assert "sold" not in listing
    assert "realized_price" not in listing


# 19. resume after interrupted target
def test_resume_after_interrupted_target_continues_remaining(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "backend.scripts.index_fair_value_ebay_evidence_collector.RUNS_DIR", tmp_path
    )
    monkeypatch.setattr(
        "backend.scripts.index_fair_value_ebay_evidence_collector.generate_queries",
        lambda target: [{"formulation": "primary", "query": "q", "marketplace": "EBAY_US", "category_id": "183454", "limit": 100, "filters": "f"}],
    )
    config = CollectorConfig(max_requests_per_run=1, run_matcher=False)
    tokens = TokenProvider({}, fetch=lambda: "tok")

    opener1 = ScriptedOpener([{"itemSummaries": [make_item("A")], "next": None}])
    http1 = BrowseHTTP(tokens, config, opener=opener1, sleep=lambda s: None)
    state = RunState.new("run7", [CARD, CARD_2], config)
    state.save()
    state = Collector(http1, config).run(state, [CARD, CARD_2])
    state.save()
    assert state.completed is False

    resumed = RunState.load("run7")
    resumed.config["max_requests_per_run"] = 10
    config2 = CollectorConfig(max_requests_per_run=10, run_matcher=False)
    opener2 = ScriptedOpener([{"itemSummaries": [make_item("B")], "next": None}])
    http2 = BrowseHTTP(tokens, config2, opener=opener2, sleep=lambda s: None)
    resumed = Collector(http2, config2).run(resumed, [CARD, CARD_2])
    assert resumed.completed is True
    assert all(t["status"] == "completed" for t in resumed.targets.values())


# 20. rerun/idempotency, 21. raw-data/provenance deduplication
def test_rerun_same_completed_run_does_not_duplicate_evidence(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "backend.scripts.index_fair_value_ebay_evidence_collector.RUNS_DIR", tmp_path
    )
    config = CollectorConfig(run_matcher=False)
    tokens = TokenProvider({}, fetch=lambda: "tok")
    opener = ScriptedOpener([{"itemSummaries": [make_item("A")], "next": None}])
    http = BrowseHTTP(tokens, config, opener=opener, sleep=lambda s: None)
    state = RunState.new("run8", [CARD], config)
    state.save()
    state = Collector(http, config).run(state, [CARD])
    state.save()

    reloaded = RunState.load("run8")
    opener2 = ScriptedOpener([])  # would error if any call attempted -- target already completed
    http2 = BrowseHTTP(tokens, config, opener=opener2, sleep=lambda s: None)
    reloaded = Collector(http2, config).run(reloaded, [CARD])
    raw_lines = reloaded.raw_evidence_path().read_text(encoding="utf-8").splitlines()
    assert len(raw_lines) == 1
    assert opener2.calls == 0


# 22. credential redaction
def test_credential_redaction_never_reveals_secret():
    assert redact("super-secret-token") == "<redacted:18>"
    assert "super-secret-token" not in redact("super-secret-token")
    assert redact(None) == "<empty>"
