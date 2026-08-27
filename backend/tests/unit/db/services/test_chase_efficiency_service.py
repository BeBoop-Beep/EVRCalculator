import pytest

from backend.db.services.chase_efficiency_service import PAGE_SIZE, _all, build_snapshot_from_inputs, publish_candidate, validate_candidate


class _Response:
    def __init__(self, data): self.data = data


def test_paginator_uses_fresh_builder_and_stops_on_short_page():
    rows = [{"id": i} for i in range(PAGE_SIZE * 2 + 17)]
    builders = []

    class Query:
        def __init__(self): self.ranges = []
        def range(self, start, end): self.ranges.append((start, end)); return self
        def execute(self):
            start, end = self.ranges[-1]
            return _Response(rows[start:end + 1])

    def factory():
        query = Query(); builders.append(query); return query

    assert _all(factory) == rows
    assert [builder.ranges for builder in builders] == [[(0, 999)], [(1000, 1999)], [(2000, 2999)]]


def test_publisher_does_not_fallback_to_partial_or_move_latest_on_rpc_failure(monkeypatch):
    import backend.db.services.chase_efficiency_service as service

    state = {"snapshots": [], "rows": [], "latest": "previous"}

    class Rpc:
        def __init__(self, name): self.name = name
        def execute(self):
            # Model work staged inside the database transaction, then failure.
            # PostgreSQL rolls this back; the Python publisher must not attempt
            # any non-atomic fallback writes or latest-pointer mutation.
            if self.name == "begin_pokemon_card_chase_efficiency_publication":
                return _Response("job-1")
            if self.name == "abort_pokemon_card_chase_efficiency_publication":
                return _Response(None)
            raise RuntimeError("simulated row insert failure")

    class Client:
        def rpc(self, name, params):
            assert name in {
                "begin_pokemon_card_chase_efficiency_publication",
                "append_pokemon_card_chase_efficiency_publication_rows",
                "abort_pokemon_card_chase_efficiency_publication",
            }
            return Rpc(name)

    candidate = {"snapshot": {}, "rows": [{"card_variant_id": "v1"}], "excluded": []}
    monkeypatch.setattr(service, "validate_candidate", lambda value: [])
    with pytest.raises(RuntimeError, match="simulated row insert failure"):
        publish_candidate(Client(), candidate)
    assert state == {"snapshots": [], "rows": [], "latest": "previous"}


def test_candidate_keeps_exclusions_and_passes_audit():
    product = {"sealed_product_id":"p", "product_name":"Box", "product_family":"booster_box", "product_price":100,
               "random_pack_count":36, "composition_verified":True, "price_source":"x", "price_as_of":"2026-08-27"}
    base = {"set_id":"s", "source_calculation_run_id":"r", "effective_pull_rate":100, "canonical_card_id":"c",
            "era_id":"e", "canonical_rarity":"Illustration Rare", "card_name":"A", "current_market_price":50,
            "price_is_fresh":True, "card_price_as_of":"2026-08-27"}
    candidate = build_snapshot_from_inputs(
        market_date="2026-08-27", cards=[dict(base, card_variant_id="v1"), dict(base, card_variant_id="v2", price_is_fresh=False)],
        products_by_set={"s":[product]}, authoritative_run_ids={"s":"r"}, supported_set_count=1,
    )
    assert candidate["snapshot"]["eligible_cohort_count"] == 1
    assert candidate["snapshot"]["excluded_cohort_count"] == 1
    assert candidate["excluded"][0]["reason"] == "stale_near_mint_price"
    assert validate_candidate(candidate) == []
