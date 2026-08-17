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
        self.range_filter = None

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

    def range(self, start, end):
        self.range_filter = (start, end)
        return self

    def execute(self):
        self.client.queries.append(self)
        rows = self.client.handlers[self.table_name](self)
        if self.range_filter is not None:
            start, end = self.range_filter
            rows = list(rows)[start:end + 1]
        return _Result(rows)


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
        {"card_variant_id": "variant-b", "effective_pull_rate": 250},
        {"card_variant_id": "variant-a", "effective_pull_rate": 20},
    ]
    variant_rows = [
        {
            "id": "variant-b",
            "card_id": "card-b",
            "image_small_url": "https://img/b-small.png",
            "image_large_url": None,
        }
    ]
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


@pytest.mark.parametrize("denominator", [480, 1533])
def test_effective_pull_rate_is_the_authoritative_one_in_n_denominator(denominator):
    client = _top_chase_client(
        [_price_row(card_variant_id="variant-a")],
        [{"card_variant_id": "variant-a", "effective_pull_rate": denominator}],
    )
    chase = build_top_chase_contract(run_id=RUN_A, client=client)
    assert chase["impliedOddsOneInN"] == denominator
    assert chase["modeledProbability"] == 1 / denominator


@pytest.mark.parametrize("denominator", [None, 0, -1, float("nan"), float("inf")])
def test_invalid_effective_pull_denominators_are_unavailable(denominator):
    client = _top_chase_client(
        [_price_row(card_variant_id="variant-a")],
        [{"card_variant_id": "variant-a", "effective_pull_rate": denominator}],
    )
    assert build_top_chase_contract(run_id=RUN_A, client=client) is None


def test_top_chase_searches_the_whole_modeled_population_not_the_priciest_n():
    """The 26th-priciest card wins when the 25 above it are unmodeled.

    A top-N price prefilter answers "the priciest card, IF it happens to be
    modeled". The contract's question is "the priciest MODELED card", and the
    two answers differ exactly when a set's most expensive cards are outside the
    modeled population - which is the normal case for promos and sealed-era alt
    arts that never come out of these packs.
    """
    price_rows = [
        _price_row(
            card_id="card-%d" % index,
            card_variant_id="variant-%d" % index,
            card_name="Card %d" % index,
            current_near_mint_price=float(1000 - index),
        )
        for index in range(30)
    ]
    # Only the 26th-priciest card (index 25) is in the run's modeled population.
    input_rows = [{"card_variant_id": "variant-25", "effective_pull_rate": 500}]
    client = _top_chase_client(price_rows, input_rows)

    chase = build_top_chase_contract(run_id=RUN_A, client=client)

    assert chase["cardVariantId"] == "variant-25"
    assert chase["currentMarketPrice"] == 975.0


def test_top_chase_reads_a_bounded_number_of_queries_for_a_full_set():
    price_rows = [
        _price_row(card_variant_id="variant-%d" % index, current_near_mint_price=float(500 - index))
        for index in range(400)
    ]
    input_rows = [
        {"card_variant_id": "variant-%d" % index, "effective_pull_rate": 100}
        for index in range(400)
    ]
    client = _top_chase_client(price_rows, input_rows)

    build_top_chase_contract(run_id=RUN_A, client=client)

    # One probability read, one price read, and the image lookups for the single
    # chosen card. Never one query per card.
    assert len(client.table_calls("simulation_input_cards")) == 1
    assert len(client.table_calls("simulation_input_cards_with_near_mint_price")) == 1
    assert len(client.queries) <= 4


def test_both_top_chase_reads_are_scoped_to_the_same_run():
    client = _top_chase_client(
        [_price_row()], [{"card_variant_id": "variant-a", "effective_pull_rate": 100}]
    )
    build_top_chase_contract(run_id=RUN_A, client=client)

    probability_query = client.table_calls("simulation_input_cards")[0]
    price_query = client.table_calls("simulation_input_cards_with_near_mint_price")[0]
    assert ("calculation_run_id", RUN_A) in probability_query.eq_filters
    assert ("calculation_run_id", RUN_A) in price_query.eq_filters


def test_a_population_larger_than_one_page_is_read_completely():
    """Silent truncation at the page boundary would change the answer."""
    page = service.RUN_POPULATION_PAGE_SIZE
    price_rows = [
        _price_row(card_variant_id="variant-%d" % index, current_near_mint_price=float(index))
        for index in range(page + 5)
    ]
    # The priciest card is the LAST row, reachable only on the second page.
    input_rows = [{"card_variant_id": "variant-%d" % (page + 4), "effective_pull_rate": 100}]
    client = _top_chase_client(price_rows, input_rows)

    chase = build_top_chase_contract(run_id=RUN_A, client=client)

    assert chase["cardVariantId"] == "variant-%d" % (page + 4)
    assert len(client.table_calls("simulation_input_cards_with_near_mint_price")) == 2


def test_top_chase_is_none_when_the_run_has_no_priced_modeled_cards():
    client = _top_chase_client([], [])
    assert build_top_chase_contract(run_id=RUN_A, client=client) is None


def test_no_price_read_happens_when_the_run_models_no_cards():
    client = _top_chase_client([_price_row()], [])
    assert build_top_chase_contract(run_id=RUN_A, client=client) is None
    assert client.table_calls("simulation_input_cards_with_near_mint_price") == []


def test_top_chase_never_infers_probability_from_ev_contribution():
    # ev_contribution / price would give 0.01 here. The stored rate is 0.004.
    price_rows = [_price_row(card_variant_id="variant-b", ev_contribution=4.0, current_near_mint_price=400.0)]
    input_rows = [{"card_variant_id": "variant-b", "effective_pull_rate": 250}]
    client = _top_chase_client(price_rows, input_rows)

    chase = build_top_chase_contract(run_id=RUN_A, client=client)
    assert chase["modeledProbability"] == 1 / 250


def test_top_chase_ignores_non_finite_and_non_positive_pull_denominators():
    price_rows = [
        _price_row(card_variant_id="variant-nan", current_near_mint_price=900.0),
        _price_row(card_variant_id="variant-inf", current_near_mint_price=800.0),
        _price_row(card_variant_id="variant-high", current_near_mint_price=700.0),
        _price_row(card_variant_id="variant-ok", current_near_mint_price=100.0),
    ]
    input_rows = [
        {"card_variant_id": "variant-nan", "effective_pull_rate": float("nan")},
        {"card_variant_id": "variant-inf", "effective_pull_rate": float("inf")},
        {"card_variant_id": "variant-high", "effective_pull_rate": -1.4},
        {"card_variant_id": "variant-ok", "effective_pull_rate": 100},
    ]
    client = _top_chase_client(price_rows, input_rows)

    chase = build_top_chase_contract(run_id=RUN_A, client=client)
    assert chase["cardVariantId"] == "variant-ok"


def test_top_chase_is_unavailable_rather_than_wrong_without_a_run_id():
    client = _top_chase_client([_price_row()], [])
    assert build_top_chase_contract(run_id=None, client=client) is None
    assert client.queries == []


# ---------------------------------------------------------------------------
# Run identity: ONE run for the whole contract
# ---------------------------------------------------------------------------

def test_products_are_read_by_the_current_run_never_by_latest(monkeypatch):
    """The snapshot's run is the authority for EVERY section.

    A second "latest scored run" lookup can resolve to a different run than the
    page is publishing, which would put one run's product economics next to
    another run's opening odds on a single screen, with nothing on the page to
    reveal the mismatch.
    """
    seen = {}

    def _by_run(run_id, client=None):
        seen["run_id"] = run_id
        seen["client"] = client
        return [_product_row()]

    monkeypatch.setattr(service, "get_sealed_product_results_for_run", _by_run)
    client = _top_chase_client([], [])

    contract = build_rip_decision_contract(set_id="set-1", run_id=RUN_A, client=client)

    assert seen["run_id"] == RUN_A
    assert seen["client"] is client
    assert contract["sealedProducts"]["sourceCalculationRunId"] == RUN_A


def test_the_decision_layer_never_resolves_latest_itself():
    assert not hasattr(service, "get_latest_sealed_product_results_for_set")
    assert not hasattr(service, "load_sealed_product_decision_contract")


def test_a_historical_run_is_never_published_for_the_current_page():
    # RUN_B rows exist and are newer, but the page is publishing RUN_A.
    product_rows_by_run = {
        RUN_A: [_product_row(calculation_run_id=RUN_A, product_market_cost=120.0)],
        RUN_B: [_product_row(calculation_run_id=RUN_B, product_market_cost=999.0)],
    }

    def _products(query):
        requested = dict(query.eq_filters).get("calculation_run_id")
        return product_rows_by_run.get(requested, [])

    client = _Client(
        {
            "simulation_sealed_product_results": _products,
            "simulation_input_cards_with_near_mint_price": lambda query: [],
            "simulation_input_cards": lambda query: [],
        }
    )

    contract = build_rip_decision_contract(set_id="set-1", run_id=RUN_A, client=client)

    assert contract["sealedProducts"]["sourceCalculationRunId"] == RUN_A
    assert contract["sealedProducts"]["products"][0]["marketPrice"] == 120.0


def test_no_current_run_publishes_an_empty_section_without_touching_history():
    """No coordinated current run is not permission to publish stale economics."""
    client = _Client(
        {
            "simulation_sealed_product_results": lambda query: [_product_row()],
            "simulation_input_cards_with_near_mint_price": lambda query: [_price_row()],
            "simulation_input_cards": lambda query: [],
        }
    )

    contract = build_rip_decision_contract(set_id="set-1", run_id=None, client=client)

    assert contract["sealedProducts"]["products"] == []
    assert contract["sealedProducts"]["productCount"] == 0
    assert contract["sealedProducts"]["sourceCalculationRunId"] is None
    assert contract["sealedProducts"]["runStatus"] == service.RUN_STATUS_NO_CURRENT_RUN
    assert contract["topChase"] is None
    assert contract["currentRunAvailable"] is False
    # Nothing historical was read at all.
    assert client.queries == []


def test_a_current_run_labels_the_section_as_current(monkeypatch):
    monkeypatch.setattr(
        service, "get_sealed_product_results_for_run", lambda run_id, client=None: [_product_row()]
    )
    contract = build_rip_decision_contract(
        set_id="set-1", run_id=RUN_A, client=_top_chase_client([], [])
    )

    assert contract["sealedProducts"]["runStatus"] == service.RUN_STATUS_CURRENT
    assert contract["currentRunAvailable"] is True
    assert contract["sourceCalculationRunId"] == RUN_A


def test_a_product_row_belonging_to_another_set_fails_loudly(monkeypatch):
    monkeypatch.setattr(
        service,
        "get_sealed_product_results_for_run",
        lambda run_id, client=None: [_product_row(set_id="set-2")],
    )

    with pytest.raises(ValueError) as excinfo:
        build_rip_decision_contract(
            set_id="set-1", run_id=RUN_A, client=_top_chase_client([], [])
        )
    assert "set_id" in str(excinfo.value)


def test_combined_contract_carries_both_sections_and_the_scope(monkeypatch):
    monkeypatch.setattr(
        service, "get_sealed_product_results_for_run", lambda run_id, client=None: [_product_row()]
    )
    price_rows = [_price_row(card_variant_id="variant-b", current_near_mint_price=400.0)]
    input_rows = [{"card_variant_id": "variant-b", "effective_pull_rate": 250}]
    client = _top_chase_client(price_rows, input_rows)

    contract = build_rip_decision_contract(set_id="set-1", run_id=RUN_A, client=client)

    assert contract["contractVersion"] == RIP_DECISION_CONTRACT_VERSION
    assert contract["sealedProducts"]["products"][0]["sealedProductId"] == "sp-booster-box"
    assert contract["topChase"]["cardVariantId"] == "variant-b"
    assert contract["comparisonScope"] == "within_product_family_only"
    assert contract["crossFormatComparable"] is False


def test_combined_contract_survives_a_run_with_no_sealed_product_rows(monkeypatch):
    monkeypatch.setattr(
        service, "get_sealed_product_results_for_run", lambda run_id, client=None: []
    )
    client = _top_chase_client([], [])

    contract = build_rip_decision_contract(set_id="set-1", run_id=RUN_A, client=client)

    assert contract["sealedProducts"]["products"] == []
    assert contract["sealedProducts"]["runStatus"] == service.RUN_STATUS_CURRENT
    assert contract["topChase"] is None


# ---------------------------------------------------------------------------
# Finite public numbers
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_no_public_product_number_is_ever_nan_or_infinity(bad):
    contract = build_sealed_product_decision_contract(
        [
            _product_row(
                product_market_cost=bad,
                median_value=bad,
                chance_to_recover_cost=bad,
                expected_loss_when_losing=bad,
                financial_rip_v3_score=bad,
                collector_appeal_score=bad,
                overall_rip_score=bad,
                guaranteed_component_market_value=bad,
            )
        ]
    )
    product = contract["products"][0]

    for key in (
        "marketPrice",
        "typicalOpening",
        "chanceToRecoverCost",
        "expectedLossWhenLosing",
        "financialRipScore",
        "collectorAppealScore",
        "overallRipScore",
    ):
        assert product[key] is None, "%s published %r" % (key, product[key])
    assert product["composition"]["guaranteedComponentMarketValue"] is None


def test_a_legitimate_zero_measurement_is_still_published():
    contract = build_sealed_product_decision_contract(
        [_product_row(chance_to_recover_cost=0.0, expected_loss_when_losing=0.0, median_value=0.0)]
    )
    product = contract["products"][0]

    assert product["chanceToRecoverCost"] == 0.0
    assert product["expectedLossWhenLosing"] == 0.0
    assert product["typicalOpening"] == 0.0


def test_a_non_finite_chase_price_is_not_publishable():
    price_rows = [
        _price_row(card_variant_id="variant-bad", current_near_mint_price=float("inf")),
        _price_row(card_variant_id="variant-ok", current_near_mint_price=50.0),
    ]
    input_rows = [
        {"card_variant_id": "variant-bad", "effective_pull_rate": 100},
        {"card_variant_id": "variant-ok", "effective_pull_rate": 100},
    ]
    chase = build_top_chase_contract(run_id=RUN_A, client=_top_chase_client(price_rows, input_rows))

    assert chase["cardVariantId"] == "variant-ok"
    assert chase["currentMarketPrice"] == 50.0


# ---------------------------------------------------------------------------
# Entertainment Cost (additive to the existing product decision contract)
# ---------------------------------------------------------------------------

import json as _json

from backend.db.services.rip_decision_service import (
    build_sealed_product_decision_contract,
    build_unsupported_products_contract,
)


def _scored_row(**overrides):
    row = {
        "calculation_run_id": "run-1",
        "sealed_product_id": "prod-box",
        "product_name": "Booster Box",
        "product_family": "booster_box",
        "pack_count": 36,
        "product_market_cost": 149.99,
        "expected_value": 107.89,
        "median_value": 95.0,
        "chance_to_recover_cost": 0.21,
    }
    row.update(overrides)
    return row


def test_each_product_row_carries_an_entertainment_cost_block():
    contract = build_sealed_product_decision_contract([_scored_row()])
    block = contract["products"][0]["entertainmentCost"]
    assert block["entertainmentCost"] == pytest.approx(42.10)
    assert block["entertainmentCostPerPackEquivalent"] == pytest.approx(42.10 / 36)
    assert block["recoveryModel"] == "gross_market_value"


def test_entertainment_cost_marks_stage2_products_as_including_the_promo():
    contract = build_sealed_product_decision_contract(
        [_scored_row(guaranteed_component_market_value=5.0, random_pack_count=9)]
    )
    assert contract["products"][0]["entertainmentCost"]["guaranteedComponentIncluded"] is True


def test_entertainment_cost_is_unavailable_without_a_price():
    contract = build_sealed_product_decision_contract(
        [_scored_row(product_market_cost=None)]
    )
    block = contract["products"][0]["entertainmentCost"]
    assert block["available"] is False
    assert block["entertainmentCost"] is None


def test_negative_entertainment_cost_reaches_the_contract_unclamped():
    contract = build_sealed_product_decision_contract(
        [_scored_row(product_market_cost=100.0, expected_value=130.0)]
    )
    assert contract["products"][0]["entertainmentCost"]["entertainmentCost"] == pytest.approx(-30.0)


# ---------------------------------------------------------------------------
# Entertainment Cost: Stage 2 fail-closed on a half-populated row
# ---------------------------------------------------------------------------

def test_entertainment_cost_is_unavailable_when_only_promo_value_is_present():
    contract = build_sealed_product_decision_contract(
        [_scored_row(
            product_family="elite_trainer_box",
            pack_count=9,
            product_market_cost=49.99,
            expected_value=32.0,
            guaranteed_component_market_value=5.0,
            random_pack_count=None,
        )]
    )
    block = contract["products"][0]["entertainmentCost"]
    assert block["available"] is False
    assert block["entertainmentCost"] is None
    assert block["reason"] == "unresolved_composition"


def test_entertainment_cost_is_unavailable_when_only_random_pack_count_is_present():
    contract = build_sealed_product_decision_contract(
        [_scored_row(
            product_family="elite_trainer_box",
            pack_count=9,
            product_market_cost=49.99,
            expected_value=32.0,
            guaranteed_component_market_value=None,
            random_pack_count=9,
        )]
    )
    block = contract["products"][0]["entertainmentCost"]
    assert block["available"] is False
    assert block["entertainmentCost"] is None
    assert block["reason"] == "guaranteed_component_market_price_unavailable"


# ---------------------------------------------------------------------------
# Unsupported products
# ---------------------------------------------------------------------------

_SNAPSHOT = {
    "products": [
        {"sealedProductId": "prod-box", "name": "Booster Box",
         "productFamily": "booster_box", "currentPrice": 149.99},
        {"sealedProductId": "prod-blister", "name": "3-Pack Blister",
         "productFamily": "three_pack_blister", "currentPrice": 14.99},
        {"sealedProductId": "prod-halfbox", "name": "Half Booster Box",
         "productFamily": "booster_box", "currentPrice": 79.99},
    ]
}


def test_unmodeled_families_are_published_explicitly_not_omitted():
    contract = build_unsupported_products_contract(_SNAPSHOT, {"prod-box"})
    ids = {p["sealedProductId"] for p in contract["products"]}
    assert "prod-blister" in ids
    assert "prod-box" not in ids


def test_unsupported_products_carry_a_machine_readable_reason():
    contract = build_unsupported_products_contract(_SNAPSHOT, {"prod-box"})
    reasons = {p["sealedProductId"]: p["entertainmentCost"]["reason"] for p in contract["products"]}
    assert reasons["prod-blister"] == "unsupported_product_family"
    # Right family, wrong pack count: the more specific existing reason wins.
    assert reasons["prod-halfbox"] == "non_default_pack_count_variant"


def test_unsupported_products_keep_their_market_price():
    contract = build_unsupported_products_contract(_SNAPSHOT, {"prod-box"})
    blister = next(p for p in contract["products"] if p["sealedProductId"] == "prod-blister")
    assert blister["marketPrice"] == 14.99
    assert blister["entertainmentCost"]["entertainmentCost"] is None


def test_unsupported_contract_is_empty_without_a_snapshot():
    contract = build_unsupported_products_contract(None, set())
    assert contract["products"] == []
    assert contract["productCount"] == 0


# ---------------------------------------------------------------------------
# Unsupported reason precedence
# ---------------------------------------------------------------------------
# `simulation_result_unavailable` is the LAST resort. Each of these pins one
# step of the precedence so a future edit cannot let the new reason swallow a
# genuine price or composition fault.

def _reasons(snapshot, scored=()):
    contract = build_unsupported_products_contract(snapshot, set(scored))
    return {p["sealedProductId"]: p["entertainmentCost"]["reason"] for p in contract["products"]}


def test_supported_half_booster_box_with_a_price_but_no_score_is_simulation_unavailable():
    # The production defect: `half_booster_box` is a supported Stage 1 family
    # with a verified 18-pack composition and a real price. Nothing about its
    # price or composition is wrong; it simply was not scored.
    snapshot = {"products": [
        {"sealedProductId": "prod-half", "name": "Half Booster Box",
         "productFamily": "half_booster_box", "currentPrice": 79.99},
    ]}
    assert _reasons(snapshot) == {"prod-half": "simulation_result_unavailable"}


def test_the_half_booster_box_keeps_its_market_price_alongside_the_new_reason():
    snapshot = {"products": [
        {"sealedProductId": "prod-half", "name": "Half Booster Box",
         "productFamily": "half_booster_box", "currentPrice": 79.99},
    ]}
    row = build_unsupported_products_contract(snapshot, set())["products"][0]
    assert row["marketPrice"] == 79.99
    assert row["entertainmentCost"]["purchasePrice"] == 79.99


@pytest.mark.parametrize("price", [None, 0.0, -1.0])
def test_supported_product_without_a_usable_price_keeps_the_market_price_reason(price):
    # The new reason must never displace this one: a missing or non-positive
    # price is a real price fault and still reads as one.
    snapshot = {"products": [
        {"sealedProductId": "prod-half", "name": "Half Booster Box",
         "productFamily": "half_booster_box", "currentPrice": price},
        {"sealedProductId": "prod-box", "name": "Booster Box",
         "productFamily": "booster_box", "currentPrice": price},
    ]}
    assert _reasons(snapshot) == {
        "prod-half": "invalid_or_missing_market_price",
        "prod-box": "invalid_or_missing_market_price",
    }


def test_genuinely_unsupported_family_still_reports_unsupported_product_family():
    snapshot = {"products": [
        {"sealedProductId": "prod-blister", "name": "3-Pack Blister",
         "productFamily": "three_pack_blister", "currentPrice": 14.99},
    ]}
    assert _reasons(snapshot) == {"prod-blister": "unsupported_product_family"}


def test_stage2_family_without_a_verified_composition_still_reports_unresolved_composition():
    snapshot = {"products": [
        {"sealedProductId": "prod-etb", "name": "Elite Trainer Box",
         "productFamily": "elite_trainer_box", "currentPrice": 49.99},
    ]}
    assert _reasons(snapshot) == {"prod-etb": "unresolved_composition"}


def test_composition_disqualifiers_outrank_the_new_reason():
    # Priced, supported family, unscored - and still refused for composition
    # reasons, because the pack count is not the Stage 1 default.
    snapshot = {"products": [
        {"sealedProductId": "prod-quarter", "name": "Quarter Booster Box",
         "productFamily": "booster_box", "currentPrice": 39.99},
        {"sealedProductId": "prod-combo", "name": "Booster Bundle + Surprise Box",
         "productFamily": "booster_bundle", "currentPrice": 34.99},
    ]}
    assert _reasons(snapshot) == {
        "prod-quarter": "non_default_pack_count_variant",
        "prod-combo": "composite_multi_product_sku",
    }


def test_decision_contract_stays_json_safe_with_the_new_blocks():
    contract = build_sealed_product_decision_contract([_scored_row()])
    _json.dumps(contract, allow_nan=False)
    _json.dumps(build_unsupported_products_contract(_SNAPSHOT, {"prod-box"}), allow_nan=False)


def test_the_large_chase_table_is_not_in_the_decision_contract():
    # Chase economics lives in its own snapshot precisely so the critical set
    # page payload does not grow by 60-90 KB per set.
    contract = build_sealed_product_decision_contract([_scored_row()])
    assert "chaseEconomics" not in contract
    assert "chaseEconomics" not in contract["products"][0]
