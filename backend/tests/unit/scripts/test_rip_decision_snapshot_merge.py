"""The RIP decision contract's delivery into the set-page snapshot.

Delivery matters as much as shape here: the underlying table is backend-only
(migration 065 revoked anon/authenticated SELECT), so the published snapshot is
the ONLY way this data can legitimately reach a browser, and it must ride along
with the snapshot the page already fetches rather than becoming a second call.
"""

import pytest

import backend.scripts.pokemon_snapshot_builders as builders

RUN_A = "11111111-1111-1111-1111-111111111111"
RUN_B = "22222222-2222-2222-2222-222222222222"


class _Result:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, table_name, client):
        self.table_name = table_name
        self.client = client
        self.range_filter = None

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

    def range(self, start, end):
        self.range_filter = (start, end)
        return self

    def execute(self):
        self.client.tables_read.append(self.table_name)
        rows = self.client.handlers.get(self.table_name, lambda: [])()
        if self.range_filter is not None:
            start, end = self.range_filter
            rows = list(rows)[start:end + 1]
        return _Result(rows)


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
                {"card_variant_id": "variant-b", "effective_pull_rate": 250}
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
        "get_sealed_product_results_for_run",
        lambda run_id, client=None: _product_rows(),
    )

    merged = builders._merge_rip_decision_contract_into_set_payload(
        payload=_payload(), set_id="set-1", client=_client()
    )

    contract = merged["ripDecision"]
    assert contract["sealedProducts"]["products"][0]["modelEdgePercent"] == -25.0
    assert contract["topChase"]["cardVariantId"] == "variant-b"
    assert contract["topChase"]["impliedOddsOneInN"] == 250.0
    assert contract["crossFormatComparable"] is False


@pytest.mark.parametrize("base_run", [None, RUN_B])
def test_canonical_rankings_run_overrides_missing_or_stale_base_run(monkeypatch, base_run):
    seen = []
    monkeypatch.setattr(
        builders.rip_decision_service,
        "build_rip_decision_contract",
        lambda *, set_id, run_id, client: seen.append(run_id) or {
            "sourceCalculationRunId": run_id,
            "sealedProducts": {"sourceCalculationRunId": run_id, "products": []},
            "topChase": {"sourceCalculationRunId": run_id},
        },
    )
    payload = {"summary": {"calculation_run_id": base_run}, "meta": {}}
    merged = builders._merge_rip_decision_contract_into_set_payload(
        payload=payload, set_id="set-1", decision_run_id=RUN_A, client=_client()
    )
    assert seen == [RUN_A]
    assert merged["ripDecision"]["sealedProducts"]["sourceCalculationRunId"] == RUN_A
    assert merged["ripDecision"]["topChase"]["sourceCalculationRunId"] == RUN_A


def test_a_snapshot_without_a_current_run_publishes_no_decision_economics(monkeypatch):
    """A page with no current run must not borrow a historical run's numbers.

    The previous behaviour published the latest scored product rows here. Those
    rows are real and correctly provenanced, which is exactly what makes them
    dangerous next to a page that is not describing that run.
    """
    def _must_not_be_called(run_id, client=None):
        raise AssertionError("no product read may happen without a current run")

    monkeypatch.setattr(
        builders.rip_decision_service, "get_sealed_product_results_for_run", _must_not_be_called
    )
    payload = {"target": {}, "summary": {}, "meta": {}}
    client = _client()

    merged = builders._merge_rip_decision_contract_into_set_payload(
        payload=payload, set_id="set-1", client=client
    )

    assert merged["ripDecision"]["topChase"] is None
    assert merged["ripDecision"]["sealedProducts"]["products"] == []
    assert merged["ripDecision"]["sealedProducts"]["productCount"] == 0
    assert merged["ripDecision"]["currentRunAvailable"] is False
    assert client.tables_read == []


def test_a_failed_decision_read_degrades_the_section_instead_of_the_snapshot(monkeypatch):
    def _boom(_run_id, client=None):
        raise ValueError("column does not exist")

    monkeypatch.setattr(
        builders.rip_decision_service, "get_sealed_product_results_for_run", _boom
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
    def _outage(_run_id, client=None):
        raise ConnectionError("connection reset by peer")

    monkeypatch.setattr(
        builders.rip_decision_service, "get_sealed_product_results_for_run", _outage
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
        "get_sealed_product_results_for_run",
        lambda run_id, client=None: _product_rows(),
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

    # This set has no simulation run at all, so there is no current run to
    # publish decision economics for - and no historical one is substituted.
    assert payload["ripDecision"]["currentRunAvailable"] is False
    assert payload["ripDecision"]["sealedProducts"]["products"] == []
    assert payload["ripDecision"]["topChase"] is None
