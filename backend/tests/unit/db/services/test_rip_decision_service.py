"""Contract tests for the RIP decision read layer.

Two contracts are built here and both are read-only projections of data another
pass already computed: the sealed-product decision table for one set, and the
single canonical Top Chase card for one simulation run.
"""

import pytest

import backend.db.services.rip_decision_service as service
from backend.db.services.rip_decision_service import (
    RIP_DECISION_CONTRACT_VERSION,
    build_rip_decision_contract,
    build_sealed_product_decision_contract,
    build_top_chase_contract,
    select_top_chase_card,
)

RUN_A = "11111111-1111-1111-1111-111111111111"
RUN_B = "22222222-2222-2222-2222-222222222222"


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

class _Result:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, table_name, client):
        self.table_name = table_name
        self.client = client
        self.eq_filters = []
        self.in_filters = []
        self.order_fields = []
        self.select_fields = None
        self.limit_value = None

    def select(self, fields):
        self.select_fields = fields
        return self

    def eq(self, field, value):
        self.eq_filters.append((field, value))
        return self

    def in_(self, field, values):
        self.in_filters.append((field, list(values)))
        return self

    def order(self, field, desc=False):
        self.order_fields.append((field, desc))
        return self

    def limit(self, value):
        self.limit_value = value
        return self

    def execute(self):
        self.client.queries.append(self)
        return _Result(self.client.handlers[self.table_name](self))


class _Client:
    def __init__(self, handlers):
        self.handlers = handlers
        self.queries = []

    def table(self, table_name):
        return _Query(table_name, self)

    def table_calls(self, table_name):
        return [query for query in self.queries if query.table_name == table_name]


def _product_row(**overrides):
    row = {
        "calculation_run_id": RUN_A,
        "sealed_product_id": "sp-booster-box",
        "set_id": "set-1",
        "product_family": "booster_box",
        "product_name": "Test Set Booster Box",
        "pack_count": 36,
        "composition_version": "sealed-product-composition-stage1-v1",
        "composition_id": None,
        "distribution_model_version": "stage1-distribution-v1",
        "random_pack_count": 36,
        "guaranteed_component_count": 0,
        "guaranteed_component_market_value": None,
        "accessory_value_included": False,
        "product_market_cost": 120.0,
        "price_as_of": "2026-08-15",
        "price_source": "TCGPLAYER",
        "expected_value": 90.0,
        "median_value": 84.0,
        "p05_value": 60.0,
        "p95_value": 180.0,
        "p99_value": 320.0,
        "chance_to_recover_cost": 0.21,
        "expected_loss_when_losing": 38.0,
        "total_value_to_cost_ratio": 0.75,
        "financial_rip_v3_score": 41.2,
        "financial_rip_v3_status": "ok",
        "financial_rip_v3_rankable": True,
        "financial_rip_v3_version": "financial-rip-v3",
        "collector_appeal_score": 71.0,
        "collector_appeal_version": "collector-appeal-v4",
        "overall_rip_score": 44.2,
        "overall_rip_version": "overall-rip-v8",
        "overall_rip_rankable": True,
    }
    row.update(overrides)
    return row


# ---------------------------------------------------------------------------
# Sealed product decision contract
# ---------------------------------------------------------------------------

def test_product_contract_exposes_break_even_and_ratios_from_the_stored_row():
    contract = build_sealed_product_decision_contract([_product_row()])
    product = contract["products"][0]

    assert product["modelBreakEvenPrice"] == 90.0
    assert product["marketPrice"] == 120.0
    assert product["modeledReturnRatio"] == 0.75
    assert product["modeledReturnPercent"] == 75.0
    assert product["modelEdgePercent"] == -25.0
    assert product["typicalOpening"] == 84.0
    assert product["chanceToRecoverCost"] == 0.21
    assert product["expectedLossWhenLosing"] == 38.0
    assert product["financialRipScore"] == 41.2
    assert product["collectorAppealScore"] == 71.0
    assert product["overallRipScore"] == 44.2
    assert product["priceAsOf"] == "2026-08-15"
    assert product["priceSource"] == "TCGPLAYER"
    assert product["packCount"] == 36
    assert product["productFamily"] == "booster_box"


def test_product_with_an_invalid_price_keeps_its_row_and_fabricates_nothing():
    contract = build_sealed_product_decision_contract(
        [_product_row(product_market_cost=0, price_source=None, price_as_of=None)]
    )
    product = contract["products"][0]

    assert product["marketPrice"] is None
    assert product["modeledReturnRatio"] is None
    assert product["modeledReturnPercent"] is None
    assert product["modelEdgePercent"] is None
    # The row is still published, with an explicit reason, rather than dropped.
    assert product["availability"]["decisionMetricsAvailable"] is False
    assert product["availability"]["reason"] == service.REASON_MARKET_PRICE_UNAVAILABLE
    assert product["modelBreakEvenPrice"] == 90.0


def test_product_with_no_expected_value_reports_the_model_as_unavailable():
    contract = build_sealed_product_decision_contract([_product_row(expected_value=None)])
    product = contract["products"][0]

    assert product["modelBreakEvenPrice"] is None
    assert product["modeledReturnRatio"] is None
    assert product["availability"]["decisionMetricsAvailable"] is False
    assert product["availability"]["reason"] == service.REASON_EXPECTED_VALUE_UNAVAILABLE


def test_product_contract_refuses_to_mix_calculation_runs():
    rows = [_product_row(), _product_row(sealed_product_id="sp-bundle", calculation_run_id=RUN_B)]
    with pytest.raises(ValueError) as excinfo:
        build_sealed_product_decision_contract(rows)
    assert "calculation_run_id" in str(excinfo.value)


def test_product_contract_reports_the_single_run_it_was_built_from():
    contract = build_sealed_product_decision_contract(
        [_product_row(), _product_row(sealed_product_id="sp-bundle", product_family="booster_bundle")]
    )
    assert contract["sourceCalculationRunId"] == RUN_A
    assert contract["contractVersion"] == RIP_DECISION_CONTRACT_VERSION
    assert contract["productCount"] == 2


def test_product_contract_carries_the_within_family_comparison_scope():
    contract = build_sealed_product_decision_contract([_product_row()])
    assert contract["comparisonScope"] == "within_product_family_only"
    assert contract["crossFormatComparable"] is False


def _all_keys(node):
    keys = set()
    if isinstance(node, dict):
        for key, value in node.items():
            keys.add(key)
            keys |= _all_keys(value)
    elif isinstance(node, list):
        for item in node:
            keys |= _all_keys(item)
    return keys


def test_contract_introduces_no_cross_format_ranking_or_consensus_field():
    contract = build_sealed_product_decision_contract(
        [_product_row(), _product_row(sealed_product_id="sp-bundle", product_family="booster_bundle")]
    )
    forbidden = {
        "rank",
        "ranks",
        "ranking",
        "rankings",
        "consensus",
        "setConsensus",
        "setRipConsensus",
        "leaderboard",
        "productRank",
        "overallRank",
        "crossFormatRank",
        "bestProduct",
        "recommendation",
        "recommendedProduct",
    }
    assert not (_all_keys(contract) & forbidden)


def test_product_contract_preserves_market_order_and_never_sorts_by_score():
    # Row order is the repository's (pack count ascending). Re-sorting by score
    # inside one payload is the first half of a ranking; there is none here.
    rows = [
        _product_row(sealed_product_id="sp-pack", product_family="sleeved_booster_pack", pack_count=1, overall_rip_score=10.0),
        _product_row(sealed_product_id="sp-bundle", product_family="booster_bundle", pack_count=6, overall_rip_score=99.0),
        _product_row(sealed_product_id="sp-box", pack_count=36, overall_rip_score=50.0),
    ]
    contract = build_sealed_product_decision_contract(rows)
    assert [product["sealedProductId"] for product in contract["products"]] == [
        "sp-pack",
        "sp-bundle",
        "sp-box",
    ]


# ---------------------------------------------------------------------------
# Top chase selection
# ---------------------------------------------------------------------------

def _price_row(**overrides):
    row = {
        "card_id": "card-a",
        "card_variant_id": "variant-a",
        "card_name": "Card A",
        "rarity_bucket": "ultra_rare",
        "ev_contribution": 1.50,
        "current_near_mint_price": 100.0,
    }
    row.update(overrides)
    return row


def test_top_chase_is_the_highest_priced_card_not_the_highest_ev_contributor():
    # Card A pulls far more often, so it contributes more EV. Card B is the
    # card people are actually chasing: it is worth more.
    card_a = _price_row(
        card_id="card-a",
        card_variant_id="variant-a",
        card_name="Card A",
        ev_contribution=4.00,
        current_near_mint_price=80.0,
    )
    card_b = _price_row(
        card_id="card-b",
        card_variant_id="variant-b",
        card_name="Card B",
        ev_contribution=0.50,
        current_near_mint_price=400.0,
    )
    pull_rates = {"variant-a": 0.05, "variant-b": 0.00125}

    chosen = select_top_chase_card([card_a, card_b], pull_rates)
    assert chosen["card_variant_id"] == "variant-b"


def test_top_chase_skips_cards_without_a_valid_positive_modeled_probability():
    priciest = _price_row(card_variant_id="variant-zero", current_near_mint_price=900.0)
    runner_up = _price_row(card_variant_id="variant-b", current_near_mint_price=400.0)
    pull_rates = {"variant-zero": 0.0, "variant-b": 0.00125}

    chosen = select_top_chase_card([priciest, runner_up], pull_rates)
    assert chosen["card_variant_id"] == "variant-b"


def test_top_chase_skips_cards_missing_from_the_simulation_input_entirely():
    orphan = _price_row(card_variant_id="variant-orphan", current_near_mint_price=900.0)
    modeled = _price_row(card_variant_id="variant-b", current_near_mint_price=400.0)

    chosen = select_top_chase_card([orphan, modeled], {"variant-b": 0.00125})
    assert chosen["card_variant_id"] == "variant-b"


def test_top_chase_is_unavailable_when_no_card_has_both_a_price_and_a_probability():
    assert select_top_chase_card([], {}) is None
    assert select_top_chase_card([_price_row(current_near_mint_price=None)], {"variant-a": 0.1}) is None
    assert select_top_chase_card([_price_row()], {"variant-a": 0.0}) is None


# ---------------------------------------------------------------------------
# Top chase contract (read path)
# ---------------------------------------------------------------------------

def _top_chase_client(price_rows, input_rows, variant_rows=(), card_rows=()):
    return _Client(
        {
            "simulation_input_cards_with_near_mint_price": lambda query: list(price_rows),
            "simulation_input_cards": lambda query: list(input_rows),
            "card_variants": lambda query: list(variant_rows),
            "cards": lambda query: list(card_rows),
        }
    )


def test_top_chase_contract_shape_and_modeled_odds():
    price_rows = [
        _price_row(card_id="card-b", card_variant_id="variant-b", card_name="Card B", current_near_mint_price=400.0),
        _price_row(card_id="card-a", card_variant_id="variant-a", card_name="Card A", current_near_mint_price=80.0),
    ]
    input_rows = [
        {"card_variant_id": "variant-b", "effective_pull_rate": 0.004, "captured_at": "2026-08-15T00:00:00Z"},
        {"card_variant_id": "variant-a", "effective_pull_rate": 0.05, "captured_at": "2026-08-15T00:00:00Z"},
    ]
    variant_rows = [{"id": "variant-b", "card_id": "card-b", "image_small_url": "https://img/b-small.png", "image_large_url": None}]
    client = _top_chase_client(price_rows, input_rows, variant_rows)

    chase = build_top_chase_contract(run_id=RUN_A, client=client)

    assert chase["cardId"] == "card-b"
    assert chase["cardVariantId"] == "variant-b"
    assert chase["cardName"] == "Card B"
    assert chase["rarity"] == "ultra_rare"
    assert chase["imageUrl"] == "https://img/b-small.png"
    assert chase["currentMarketPrice"] == 400.0
    assert chase["modeledProbability"] == 0.004
    assert chase["impliedOddsOneInN"] == 250.0
    assert chase["packsFor50PercentChance"] == 173
    assert chase["packsFor90PercentChance"] == 575
    assert chase["sourceCalculationRunId"] == RUN_A


def test_top_chase_contract_reads_a_bounded_number_of_queries():
    price_rows = [
        _price_row(card_variant_id=f"variant-{index}", current_near_mint_price=float(500 - index))
        for index in range(50)
    ]
    input_rows = [
        {"card_variant_id": f"variant-{index}", "effective_pull_rate": 0.01}
        for index in range(50)
    ]
    client = _top_chase_client(price_rows, input_rows)

    build_top_chase_contract(run_id=RUN_A, client=client)

    # One priced-candidate read, one modeled-probability read, and the image
    # lookups for the single chosen card. Never one query per card.
    assert len(client.table_calls("simulation_input_cards_with_near_mint_price")) == 1
    assert len(client.table_calls("simulation_input_cards")) == 1
    assert len(client.queries) <= 4


def test_top_chase_candidate_read_is_ordered_by_current_price_and_limited():
    client = _top_chase_client([_price_row()], [{"card_variant_id": "variant-a", "effective_pull_rate": 0.01}])
    build_top_chase_contract(run_id=RUN_A, client=client)

    query = client.table_calls("simulation_input_cards_with_near_mint_price")[0]
    assert ("current_near_mint_price", True) in query.order_fields
    assert ("calculation_run_id", RUN_A) in query.eq_filters
    assert query.limit_value == service.TOP_CHASE_CANDIDATE_LIMIT


def test_top_chase_probability_read_is_scoped_to_the_same_run_and_candidates():
    price_rows = [_price_row(card_variant_id="variant-a"), _price_row(card_variant_id="variant-b")]
    client = _top_chase_client(price_rows, [{"card_variant_id": "variant-a", "effective_pull_rate": 0.01}])
    build_top_chase_contract(run_id=RUN_A, client=client)

    query = client.table_calls("simulation_input_cards")[0]
    assert ("calculation_run_id", RUN_A) in query.eq_filters
    assert query.in_filters == [("card_variant_id", ["variant-a", "variant-b"])]


def test_top_chase_is_none_when_the_run_has_no_priced_modeled_cards():
    client = _top_chase_client([], [])
    assert build_top_chase_contract(run_id=RUN_A, client=client) is None


def test_top_chase_never_infers_probability_from_ev_contribution():
    # ev_contribution / price would give 0.01 here. The stored rate is 0.004.
    price_rows = [_price_row(card_variant_id="variant-b", ev_contribution=4.0, current_near_mint_price=400.0)]
    input_rows = [{"card_variant_id": "variant-b", "effective_pull_rate": 0.004}]
    client = _top_chase_client(price_rows, input_rows)

    chase = build_top_chase_contract(run_id=RUN_A, client=client)
    assert chase["modeledProbability"] == 0.004


def test_top_chase_is_unavailable_rather_than_wrong_without_a_run_id():
    client = _top_chase_client([_price_row()], [])
    assert build_top_chase_contract(run_id=None, client=client) is None
    assert client.queries == []


# ---------------------------------------------------------------------------
# Combined contract
# ---------------------------------------------------------------------------

def test_combined_contract_carries_both_sections_and_the_scope(monkeypatch):
    monkeypatch.setattr(
        service, "get_latest_sealed_product_results_for_set", lambda set_id, client=None: [_product_row()]
    )
    price_rows = [_price_row(card_variant_id="variant-b", current_near_mint_price=400.0)]
    input_rows = [{"card_variant_id": "variant-b", "effective_pull_rate": 0.004}]
    client = _top_chase_client(price_rows, input_rows)

    contract = build_rip_decision_contract(set_id="set-1", run_id=RUN_A, client=client)

    assert contract["contractVersion"] == RIP_DECISION_CONTRACT_VERSION
    assert contract["sealedProducts"]["products"][0]["sealedProductId"] == "sp-booster-box"
    assert contract["topChase"]["cardVariantId"] == "variant-b"
    assert contract["comparisonScope"] == "within_product_family_only"
    assert contract["crossFormatComparable"] is False


def test_combined_contract_survives_a_set_with_no_sealed_product_rows(monkeypatch):
    monkeypatch.setattr(service, "get_latest_sealed_product_results_for_set", lambda set_id, client=None: [])
    client = _top_chase_client([], [])

    contract = build_rip_decision_contract(set_id="set-1", run_id=RUN_A, client=client)

    assert contract["sealedProducts"]["products"] == []
    assert contract["sealedProducts"]["sourceCalculationRunId"] is None
    assert contract["topChase"] is None


def test_the_product_read_uses_the_client_it_was_given(monkeypatch):
    """A snapshot build runs on an injected service-role client.

    Silently falling back to the repository's module-level client would make the
    product rows come from a different connection than every other section of
    the same snapshot - and would reach for real credentials inside a unit test.
    """
    seen = {}

    def _loader(set_id, client=None):
        seen["set_id"] = set_id
        seen["client"] = client
        return [_product_row()]

    monkeypatch.setattr(service, "get_latest_sealed_product_results_for_set", _loader)
    client = _top_chase_client([], [])

    build_rip_decision_contract(set_id="set-1", run_id=RUN_A, client=client)

    assert seen["set_id"] == "set-1"
    assert seen["client"] is client
