"""Selection and assembly tests for the chase-economics publication contract.

The top-25 cap is a PUBLICATION policy. Every test that touches it also checks
that the underlying calculator is not restricted by it.
"""

import json

import pytest

from backend.db.services.chase_economics_service import (
    DEFAULT_PUBLISHED_CARD_LIMIT,
    build_chase_economics_contract,
    build_chase_economics_snapshot_row,
    pack_groups_for_product,
    read_chase_economics_snapshot,
    select_chase_cards,
)
from backend.domain.pokemon.target_chase_economics import (
    PackGroup,
    target_chase_for_product,
)


def _price_row(variant_id, price, name=None, price_as_of=None):
    return {
        "card_id": f"card-{variant_id}",
        "card_variant_id": variant_id,
        "card_name": name or f"Card {variant_id}",
        "rarity_bucket": "ultra",
        "current_near_mint_price": price,
        "current_near_mint_price_captured_at": price_as_of,
        "current_near_mint_price_source": "TCGPlayer" if price_as_of else None,
    }


def _stage1_product(pack_count=36, price=149.99, ev=107.89):
    return {
        "sealed_product_id": "prod-box",
        "product_name": "Booster Box",
        "product_family": "booster_box",
        "pack_count": pack_count,
        "product_market_cost": price,
        "expected_value": ev,
        "random_pack_count": None,
        "guaranteed_component_market_value": None,
        "price_as_of": "2026-08-17",
        "price_source": "TCGPlayer",
        "updated_at": "2026-08-17T10:00:00+00:00",
    }


def _stage2_product():
    return {
        "sealed_product_id": "prod-etb",
        "product_name": "Elite Trainer Box",
        "product_family": "elite_trainer_box",
        "pack_count": 9,
        "product_market_cost": 49.99,
        "expected_value": 32.0,
        "random_pack_count": 9,
        "guaranteed_component_market_value": 5.0,
    }


# ---------------------------------------------------------------------------
# Card selection
# ---------------------------------------------------------------------------

def test_cards_are_selected_by_descending_market_price():
    rows = [_price_row("a", 10.0), _price_row("b", 300.0), _price_row("c", 55.0)]
    denominators = {"a": 100.0, "b": 500.0, "c": 250.0}
    used = {"a": 9.0, "b": 280.0, "c": 50.0}
    selected = select_chase_cards(rows, denominators, used, limit=10)
    assert [c["cardVariantId"] for c in selected] == ["b", "c", "a"]


def test_cards_without_a_modeled_pull_rate_are_excluded():
    # However expensive, a card the model cannot produce is not a chase this
    # contract can honestly describe.
    rows = [_price_row("a", 999.0), _price_row("b", 10.0)]
    selected = select_chase_cards(rows, {"b": 100.0}, {"b": 9.0}, limit=10)
    assert [c["cardVariantId"] for c in selected] == ["b"]


def test_cards_without_a_price_are_excluded():
    rows = [_price_row("a", None), _price_row("b", 10.0)]
    selected = select_chase_cards(rows, {"a": 100.0, "b": 100.0}, {"a": 1.0, "b": 9.0}, limit=10)
    assert [c["cardVariantId"] for c in selected] == ["b"]


def test_selection_is_capped_at_the_limit():
    rows = [_price_row(str(i), float(100 - i)) for i in range(50)]
    denominators = {str(i): 100.0 for i in range(50)}
    used = {str(i): 90.0 for i in range(50)}
    selected = select_chase_cards(rows, denominators, used, limit=25)
    assert len(selected) == 25
    assert selected[0]["cardVariantId"] == "0"


def test_selection_ties_break_deterministically():
    rows = [_price_row("b", 50.0), _price_row("a", 50.0)]
    denominators = {"a": 100.0, "b": 100.0}
    used = {"a": 45.0, "b": 45.0}
    first = select_chase_cards(rows, denominators, used, limit=10)
    second = select_chase_cards(list(reversed(rows)), denominators, used, limit=10)
    assert [c["cardVariantId"] for c in first] == [c["cardVariantId"] for c in second]


def test_selected_card_carries_both_price_bases_and_probability():
    rows = [_price_row("a", 310.0)]
    selected = select_chase_cards(rows, {"a": 476.19}, {"a": 280.0}, limit=10)[0]
    assert selected["currentTargetMarketPrice"] == 310.0
    assert selected["targetValueUsedInEV"] == 280.0
    assert selected["modeledProbability"] == pytest.approx(1.0 / 476.19)


def test_current_price_as_of_is_the_actual_current_observation_clock():
    selected = select_chase_cards(
        [_price_row("a", 310.0, price_as_of="2026-08-17")],
        {"a": 480}, {"a": 280}, limit=1,
    )[0]
    assert selected["currentPriceAsOf"] == "2026-08-17"
    assert selected["currentPriceAsOf"] != "2026-08-15T00:00:00+00:00"


def test_same_name_variants_remain_distinct_by_variant_id():
    selected = select_chase_cards(
        [_price_row("variant-a", 20, "Same Name"), _price_row("variant-b", 19, "Same Name")],
        {"variant-a": 100, "variant-b": 200},
        {"variant-a": 18, "variant-b": 17}, limit=25,
    )
    assert [row["cardVariantId"] for row in selected] == ["variant-a", "variant-b"]
    assert [row["modeledProbability"] for row in selected] == [pytest.approx(.01), pytest.approx(.005)]


def test_missing_price_used_leaves_the_ev_basis_none_rather_than_borrowing_current():
    # Borrowing today's price as the EV basis would silently zero the drift.
    rows = [_price_row("a", 310.0)]
    selected = select_chase_cards(rows, {"a": 476.19}, {}, limit=10)[0]
    assert selected["targetValueUsedInEV"] is None
    assert selected["currentTargetMarketPrice"] == 310.0


# ---------------------------------------------------------------------------
# Pack group construction
# ---------------------------------------------------------------------------

def test_stage1_pack_group_uses_expected_value_over_pack_count():
    groups, reason = pack_groups_for_product(_stage1_product(), target_probability_per_pack=0.002)
    assert reason is None
    assert len(groups) == 1
    assert groups[0].pack_count == 36
    assert groups[0].expected_pack_value == pytest.approx(107.89 / 36)


def test_stage2_pack_group_excludes_the_guaranteed_component():
    # 32.0 total minus a 5.0 promo, over 9 random packs.
    groups, reason = pack_groups_for_product(_stage2_product(), target_probability_per_pack=0.002)
    assert reason is None
    assert groups[0].pack_count == 9
    assert groups[0].expected_pack_value == pytest.approx((32.0 - 5.0) / 9)


def test_pack_group_copies_default_to_the_probability():
    # Today's Pokemon model: at most one copy of a given card per pack.
    groups, reason = pack_groups_for_product(_stage1_product(), target_probability_per_pack=0.002)
    assert reason is None
    assert groups[0].expected_target_copies_per_pack == pytest.approx(0.002)


def test_unusable_product_row_yields_no_groups():
    broken = _stage1_product(ev=None)
    groups, reason = pack_groups_for_product(broken, target_probability_per_pack=0.002)
    assert groups == []


# ---------------------------------------------------------------------------
# Stage 2 fail-closed: exactly one of the two Stage 2 inputs is present
# ---------------------------------------------------------------------------

def test_promo_value_without_random_pack_count_is_unavailable_not_stage1():
    row = {
        "sealed_product_id": "p", "product_family": "elite_trainer_box",
        "pack_count": 9, "product_market_cost": 49.99, "expected_value": 32.0,
        "random_pack_count": None,              # missing
        "guaranteed_component_market_value": 5.0,
    }
    groups, reason = pack_groups_for_product(row, target_probability_per_pack=0.002)
    assert groups == []
    assert reason == "unresolved_composition"


def test_random_pack_count_without_promo_value_is_unavailable_not_stage1():
    row = {
        "sealed_product_id": "p", "product_family": "elite_trainer_box",
        "pack_count": 9, "product_market_cost": 49.99, "expected_value": 32.0,
        "random_pack_count": 9,
        "guaranteed_component_market_value": None,   # missing
    }
    groups, reason = pack_groups_for_product(row, target_probability_per_pack=0.002)
    assert groups == []
    assert reason == "guaranteed_component_market_price_unavailable"


def test_genuine_stage1_product_still_uses_the_stage1_path():
    # Neither field present is NOT a mixed row - it is an ordinary booster box.
    row = {
        "sealed_product_id": "p", "product_family": "booster_box",
        "pack_count": 36, "product_market_cost": 149.99, "expected_value": 107.89,
        "random_pack_count": None, "guaranteed_component_market_value": None,
    }
    groups, reason = pack_groups_for_product(row, target_probability_per_pack=0.002)
    assert reason is None
    assert len(groups) == 1
    assert groups[0].expected_pack_value == pytest.approx(107.89 / 36)


def test_mixed_stage2_row_never_smears_the_promo_across_packs():
    # The specific wrong answer this rule exists to prevent: 32.0/9 = 3.556,
    # which silently includes the promo. Unavailable is the correct answer.
    row = {
        "sealed_product_id": "p", "product_family": "elite_trainer_box",
        "pack_count": 9, "product_market_cost": 49.99, "expected_value": 32.0,
        "random_pack_count": 9, "guaranteed_component_market_value": None,
    }
    groups, _ = pack_groups_for_product(row, target_probability_per_pack=0.002)
    assert groups == []


def test_mixed_stage2_product_publishes_the_specific_unavailable_reason():
    broken = {**_stage2_product(), "guaranteed_component_market_value": None}
    contract = build_chase_economics_contract(
        cards=select_chase_cards([_price_row("a", 10)], {"a": 100}, {"a": 9}),
        product_rows=[broken],
        run_id="run-1",
    )
    product = contract["cards"][0]["products"][0]
    assert product["available"] is False
    assert product["reason"] == "guaranteed_component_market_price_unavailable"


# ---------------------------------------------------------------------------
# Contract assembly
# ---------------------------------------------------------------------------

def _contract(limit=DEFAULT_PUBLISHED_CARD_LIMIT):
    cards = select_chase_cards(
        [_price_row("a", 310.0), _price_row("b", 40.0)],
        {"a": 476.19, "b": 20.0},
        {"a": 280.0, "b": 38.0},
        limit=limit,
    )
    return build_chase_economics_contract(
        cards=cards,
        product_rows=[_stage1_product(), _stage2_product()],
        run_id="run-1",
        limit=limit,
    )


def test_contract_publishes_model_assumptions():
    contract = _contract()
    assert contract["modelAssumptions"]["successfulProductFullyOpened"] is True
    assert contract["modelAssumptions"]["retainedTargetCopies"] == 1
    assert contract["recoveryModel"] == "gross_market_value"


def test_contract_carries_run_identity_and_selection_policy():
    contract = _contract()
    assert contract["sourceCalculationRunId"] == "run-1"
    assert contract["selectionPolicy"] == "top_market_price_pullable"
    assert contract["publishedCardLimit"] == DEFAULT_PUBLISHED_CARD_LIMIT


def test_each_card_carries_loose_pack_thresholds_and_a_product_row_per_sku():
    contract = _contract()
    card = contract["cards"][0]
    assert card["packsFor50PercentChance"] is not None
    assert card["packsFor95PercentChance"] is not None
    assert {p["sealedProductId"] for p in card["products"]} == {"prod-box", "prod-etb"}


def test_price_basis_delta_is_published_per_card():
    contract = _contract()
    card = next(c for c in contract["cards"] if c["cardVariantId"] == "a")
    assert card["targetPriceBasisDelta"] == pytest.approx(30.0)


def test_only_current_card_price_changes_current_price_delta_and_premium():
    def card_at(price):
        cards = select_chase_cards([_price_row("a", price)], {"a": 480}, {"a": 280})
        return build_chase_economics_contract(
            cards=cards, product_rows=[_stage1_product()], run_id="run-1"
        )["cards"][0]
    before, after = card_at(300), card_at(325)
    for key in ("modeledProbability", "impliedOddsOneInN", "expectedPacksToHit",
                "packsFor50PercentChance", "packsFor75PercentChance",
                "packsFor90PercentChance", "packsFor95PercentChance", "targetValueUsedInEV"):
        assert before[key] == after[key]
    assert before["currentTargetMarketPrice"] != after["currentTargetMarketPrice"]
    assert before["targetPriceBasisDelta"] != after["targetPriceBasisDelta"]
    assert before["products"][0]["entertainmentPremium"] != after["products"][0]["entertainmentPremium"]


def test_current_product_price_and_provenance_flow_into_rebuilt_contract():
    cards = select_chase_cards([_price_row("a", 300)], {"a": 480}, {"a": 280})
    old = build_chase_economics_contract(cards=cards, product_rows=[_stage1_product(price=84.59)], run_id="r")
    new = build_chase_economics_contract(cards=cards, product_rows=[_stage1_product(price=88.23)], run_id="r")
    old_product, new_product = old["cards"][0]["products"][0], new["cards"][0]["products"][0]
    assert old_product["productPrice"] == 84.59
    assert new_product["productPrice"] == 88.23
    assert old_product["grossSpend"] != new_product["grossSpend"]
    assert new_product["productPriceAsOf"] == "2026-08-17"


def test_provenance_nulls_are_not_defaulted_to_read_time():
    cards = select_chase_cards([_price_row("a", 310.0)], {"a": 476.19}, {"a": 280.0}, limit=5)
    contract = build_chase_economics_contract(
        cards=cards, product_rows=[_stage1_product()], run_id="run-1"
    )
    card = contract["cards"][0]
    # No timestamp was supplied by the rows, so none may be asserted.
    assert card["evPriceBasisAsOf"] is None
    assert card["currentPriceAsOf"] is None
    assert card["evPriceBasisRunId"] == "run-1"


def test_eligible_card_count_reports_the_full_population_not_the_cap():
    rows = [_price_row(str(i), float(100 - i)) for i in range(40)]
    denominators = {str(i): 100.0 for i in range(40)}
    used = {str(i): 90.0 for i in range(40)}
    cards = select_chase_cards(rows, denominators, used, limit=5)
    contract = build_chase_economics_contract(
        cards=cards, product_rows=[_stage1_product()], run_id="run-1",
        limit=5, eligible_card_count=len(rows),
    )
    assert contract["publishedCardLimit"] == 5
    assert len(contract["cards"]) == 5
    assert contract["eligibleCardCount"] == 40


def test_the_publication_cap_does_not_restrict_the_calculator():
    # A card ranked far outside the published 25 computes identically through
    # the pure function. The cap is policy, not a property of the math.
    groups, _ = pack_groups_for_product(
        _stage1_product(), target_probability_per_pack=0.0001
    )
    block = target_chase_for_product(
        product_price=149.99,
        pack_groups=groups,
        target_value_used_in_ev=1.5,
        current_target_market_price=1.75,
    )
    assert block["available"] is True
    assert block["entertainmentPremium"] is not None


def test_contract_is_json_safe():
    json.dumps(_contract(), allow_nan=False)


def test_empty_population_publishes_an_explicit_empty_contract():
    contract = build_chase_economics_contract(cards=[], product_rows=[], run_id=None)
    assert contract["cards"] == []
    assert contract["eligibleCardCount"] == 0
    assert contract["sourceCalculationRunId"] is None
    json.dumps(contract, allow_nan=False)


class _Result:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, rows):
        self.rows = rows

    def select(self, *_args, **_kwargs): return self
    def eq(self, *_args, **_kwargs): return self
    def range(self, start, end):
        self.rows = self.rows[start:end + 1]
        return self
    def limit(self, value):
        self.rows = self.rows[:value]
        return self
    def execute(self): return _Result(self.rows)


class _Client:
    def __init__(self, tables):
        self.tables = tables

    def table(self, name): return _Query(list(self.tables.get(name, [])))


def test_snapshot_builder_counts_full_population_before_storing_top_25(monkeypatch):
    price_rows = [_price_row(str(i), 1000 - i) for i in range(187)]
    inputs = [
        {"card_variant_id": str(i), "effective_pull_rate": 100,
         "price_used": 900 - i, "captured_at": "2026-08-15T00:00:00+00:00"}
        for i in range(187)
    ]
    monkeypatch.setattr(
        "backend.db.services.chase_economics_service._load_current_run_product_rows",
        lambda **_kwargs: [_stage1_product()],
    )
    row = build_chase_economics_snapshot_row(
        set_id="set-1", run_id="run-1",
        client=_Client({"simulation_input_cards": inputs,
                        "simulation_input_cards_with_near_mint_price": price_rows}),
    )
    assert row["card_count"] == 25
    assert row["payload_json"]["eligibleCardCount"] == 187
    assert row["payload_json"]["publishedCardLimit"] == 25
    assert len(row["payload_json"]["cards"]) == 25
    assert row["payload_json"]["cards"][0]["targetPriceBasisDelta"] == 100
    assert row["payload_json"]["cards"][0]["evPriceBasisAsOf"] == "2026-08-15T00:00:00+00:00"


def test_dedicated_reader_returns_payload_without_another_snapshot():
    payload = _contract()
    read = read_chase_economics_snapshot(
        set_id="set-1",
        client=_Client({"pokemon_set_chase_economics_snapshot_latest": [{"payload_json": payload}]}),
    )
    assert read == payload


# ---------------------------------------------------------------------------
# Reconciliation: the top-level calculation_run_id column must never disagree
# with payload_json.sourceCalculationRunId. The column exists specifically so
# a reader can tell whether this row describes the same run as the set page's
# ripDecision without opening the payload; if the two drift, that promise is
# silently broken.
# ---------------------------------------------------------------------------

def test_snapshot_row_calculation_run_id_matches_payload_source_run_id(monkeypatch):
    price_rows = [_price_row("a", 100.0)]
    inputs = [
        {"card_variant_id": "a", "effective_pull_rate": 100,
         "price_used": 90.0, "captured_at": "2026-08-15T00:00:00+00:00"}
    ]
    monkeypatch.setattr(
        "backend.db.services.chase_economics_service._load_current_run_product_rows",
        lambda **_kwargs: [_stage1_product()],
    )
    row = build_chase_economics_snapshot_row(
        set_id="set-1", run_id="run-1",
        client=_Client({"simulation_input_cards": inputs,
                        "simulation_input_cards_with_near_mint_price": price_rows}),
    )
    assert row["calculation_run_id"] == row["payload_json"]["sourceCalculationRunId"]
    assert row["calculation_run_id"] == "run-1"


def test_snapshot_row_with_no_run_publishes_explicitly_empty_payload():
    row = build_chase_economics_snapshot_row(
        set_id="set-1", run_id=None,
        client=_Client({}),
    )
    assert row["calculation_run_id"] is None
    assert row["payload_json"]["sourceCalculationRunId"] is None
    assert row["payload_json"]["cards"] == []
    assert row["card_count"] == 0


def test_snapshot_row_card_count_matches_payload_card_list_length(monkeypatch):
    price_rows = [_price_row(str(i), float(100 - i)) for i in range(30)]
    inputs = [
        {"card_variant_id": str(i), "effective_pull_rate": 100,
         "price_used": 90 - i, "captured_at": "2026-08-15T00:00:00+00:00"}
        for i in range(30)
    ]
    monkeypatch.setattr(
        "backend.db.services.chase_economics_service._load_current_run_product_rows",
        lambda **_kwargs: [_stage1_product()],
    )
    row = build_chase_economics_snapshot_row(
        set_id="set-1", run_id="run-1",
        client=_Client({"simulation_input_cards": inputs,
                        "simulation_input_cards_with_near_mint_price": price_rows}),
    )
    assert row["card_count"] == len(row["payload_json"]["cards"])
