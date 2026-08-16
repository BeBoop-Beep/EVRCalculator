"""The RIP decision contract's delivery into the set-page snapshot.

Delivery matters as much as shape here: the underlying table is backend-only
(migration 065 revoked anon/authenticated SELECT), so the published snapshot is
the ONLY way this data can legitimately reach a browser, and it must ride along
with the snapshot the page already fetches rather than becoming a second call.
"""

import pytest

import backend.scripts.pokemon_snapshot_builders as builders

RUN_A = "11111111-1111-1111-1111-111111111111"


class _Result:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, table_name, client):
        self.table_name = table_name
        self.client = client

    def select(self, _fields):
        return self

    def eq(self, _field, _value):
        return self

    def in_(self, _field, _values):
        return self

    def order(self, _field, desc=False):
        return self

    def limit(self, _value):
        return self

    def execute(self):
        self.client.tables_read.append(self.table_name)
        return _Result(self.client.handlers.get(self.table_name, lambda: [])())


class _Client:
    def __init__(self, handlers):
        self.handlers = handlers
        self.tables_read = []

    def table(self, table_name):
        return _Query(table_name, self)


def _payload():
    return {
        "target": {"target_type": "set", "target_id": "set-1"},
        "summary": {"calculation_run_id": RUN_A},
        "meta": {"warnings": []},
    }


def _client():
    return _Client(
        {
            "simulation_input_cards_with_near_mint_price": lambda: [
                {
                    "card_id": "card-b",
                    "card_variant_id": "variant-b",
                    "card_name": "Card B",
                    "rarity_bucket": "special_illustration_rare",
                    "current_near_mint_price": 400.0,
                }
            ],
            "simulation_input_cards": lambda: [
                {"card_variant_id": "variant-b", "effective_pull_rate": 0.004}
            ],
            "card_variants": lambda: [],
            "cards": lambda: [],
        }
    )


def _product_rows():
    return [
        {
            "calculation_run_id": RUN_A,
            "sealed_product_id": "sp-box",
            "product_family": "booster_box",
            "product_name": "Test Set Booster Box",
            "pack_count": 36,
            "product_market_cost": 120.0,
            "expected_value": 90.0,
            "median_value": 84.0,
            "chance_to_recover_cost": 0.21,
            "expected_loss_when_losing": 38.0,
            "financial_rip_v3_score": 41.2,
            "collector_appeal_score": 71.0,
            "overall_rip_score": 44.2,
            "price_as_of": "2026-08-15",
            "price_source": "TCGPLAYER",
        }
    ]


def test_snapshot_payload_carries_the_rip_decision_contract(monkeypatch):
    monkeypatch.setattr(
        builders.rip_decision_service,
        "get_latest_sealed_product_results_for_set",
        lambda set_id, client=None: _product_rows(),
    )

    merged = builders._merge_rip_decision_contract_into_set_payload(
        payload=_payload(), set_id="set-1", client=_client()
    )

    contract = merged["ripDecision"]
    assert contract["sealedProducts"]["products"][0]["modelEdgePercent"] == -25.0
    assert contract["topChase"]["cardVariantId"] == "variant-b"
    assert contract["topChase"]["impliedOddsOneInN"] == 250.0
    assert contract["crossFormatComparable"] is False


def test_merge_publishes_without_a_top_chase_when_the_run_id_is_unknown(monkeypatch):
    monkeypatch.setattr(
        builders.rip_decision_service,
        "get_latest_sealed_product_results_for_set",
        lambda set_id, client=None: _product_rows(),
    )
    payload = {"target": {}, "summary": {}, "meta": {}}
    client = _client()

    merged = builders._merge_rip_decision_contract_into_set_payload(
        payload=payload, set_id="set-1", client=client
    )

    assert merged["ripDecision"]["topChase"] is None
    assert merged["ripDecision"]["sealedProducts"]["productCount"] == 1
    assert client.tables_read == []


def test_a_failed_decision_read_degrades_the_section_instead_of_the_snapshot(monkeypatch):
    def _boom(_set_id, client=None):
        raise ValueError("column does not exist")

    monkeypatch.setattr(
        builders.rip_decision_service, "get_latest_sealed_product_results_for_set", _boom
    )

    merged = builders._merge_rip_decision_contract_into_set_payload(
        payload=_payload(), set_id="set-1", client=_client()
    )

    assert merged["ripDecision"] is None
    # Build-internal, so it goes to debugWarnings - never to the page's warnings.
    assert any("RIP decision" in str(warning) for warning in merged["meta"]["debugWarnings"])
    assert merged["meta"]["warnings"] == []
    # The rest of the page is untouched.
    assert merged["summary"]["calculation_run_id"] == RUN_A


def test_a_transient_outage_still_fails_the_build(monkeypatch):
    def _outage(_set_id, client=None):
        raise ConnectionError("connection reset by peer")

    monkeypatch.setattr(
        builders.rip_decision_service, "get_latest_sealed_product_results_for_set", _outage
    )

    with pytest.raises(ConnectionError):
        builders._merge_rip_decision_contract_into_set_payload(
            payload=_payload(), set_id="set-1", client=_client()
        )


def test_the_real_set_page_builder_publishes_the_section(monkeypatch):
    """Wiring, not shape: a section nothing calls is a section nobody gets."""
    from backend.db.services.explore_page_service import ExplorePageError
    from backend.tests.unit.scripts.test_pokemon_snapshot_builders import _Client as _BuilderClient

    def _raise_missing(_target_type, _set_id):
        raise ExplorePageError(
            status_code=404,
            message="No simulation data found for this target",
            code="TARGET_NOT_FOUND",
        )

    monkeypatch.setattr(builders, "get_explore_page_payload", _raise_missing)
    monkeypatch.setattr(builders, "get_rip_statistics_targets_payload", lambda limit: {"targets": []})
    monkeypatch.setattr(
        builders.rip_decision_service,
        "get_latest_sealed_product_results_for_set",
        lambda set_id, client=None: _product_rows(),
    )
    client = _BuilderClient(
        {
            "simulation_input_cards_with_near_mint_price": lambda _q: [],
            "simulation_input_cards": lambda _q: [],
            "pokemon_set_cards_snapshot_latest": lambda _q: [],
            "pokemon_explore_rankings_snapshot_latest": lambda _q: [],
            "explore_rip_statistics_latest": lambda _q: [],
            "simulation_latest_by_target": lambda _q: [],
            "pokemon_set_page_snapshot_latest": lambda _q: [],
        }
    )

    payload = builders.build_set_page_snapshot_row(
        {"id": "set-1", "name": "Alpha", "canonical_key": "alpha"}, client=client
    )["payload_json"]

    assert payload["ripDecision"]["sealedProducts"]["products"][0]["modeledReturnPercent"] == 75.0
    # A set with no simulation run has no modeled chase, and says so.
    assert payload["ripDecision"]["topChase"] is None
