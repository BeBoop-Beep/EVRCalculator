"""Market publication audit: every public surface must reach the promoted date."""

from __future__ import annotations

from backend.scripts.audit_pokemon_market_publication import (
    SECTION_CARD_PRICES,
    SECTION_HEADER_SUMMARY,
    SECTION_OPENING_PROFIT_VS_COST,
    SECTION_SEALED_MARKET,
    SECTION_SET_VALUE,
    SECTION_TOP_CHASE,
    audit_market_set_row,
)

DATE = "2026-08-03"
PRIOR = "2026-08-02"


def _history(dates, price=10.0):
    return [{"date": d, "marketPrice": price} for d in dates]


def _dashboard(**overrides):
    row = {
        "latest_market_date": DATE,
        "top_chase_cards_json": [
            {"cardVariantId": "v1", "marketPrice": 12.5, "setId": "set-1"},
        ],
        "top_chase_card_histories_json": {"v1": _history([PRIOR, DATE])},
        "performance_vs_cost_history_json": [
            {"date": DATE, "simulatedMeanPackValueVsPackCost": 1.1,
             "simulatedMedianPackValueVsPackCost": 0.9},
        ],
    }
    row.update(overrides)
    return row


def _audit(**overrides):
    kwargs = {
        "canonical_key": "testSet",
        "set_id": "set-1",
        "set_name": "Test Set",
        "market_date": DATE,
        "dashboard_row": _dashboard(),
        "value_history": [{"date": DATE, "setValue": 100.0}],
        "sealed_row": {"market_date": DATE},
        "supports_simulation": True,
        "has_sealed_product": True,
    }
    kwargs.update(overrides)
    return audit_market_set_row(**kwargs)


def _section(row, name):
    return next(v for v in row.sections if v.section == name)


def test_fully_current_set_passes_every_section():
    row = _audit()
    assert row.passed, row.failed_sections
    assert len(row.sections) == 6


def test_set_value_behind_promoted_date_fails():
    row = _audit(value_history=[{"date": PRIOR, "setValue": 100.0}])
    assert SECTION_SET_VALUE in row.failed_sections
    assert "behind promoted market date" in _section(row, SECTION_SET_VALUE).detail


def test_missing_set_value_history_fails():
    row = _audit(value_history=[])
    assert SECTION_SET_VALUE in row.failed_sections


def test_top_chase_history_behind_promoted_date_fails():
    row = _audit(dashboard_row=_dashboard(
        top_chase_card_histories_json={"v1": _history(["2026-08-01", PRIOR])}
    ))
    assert SECTION_TOP_CHASE in row.failed_sections


def test_top_chase_future_date_fails():
    row = _audit(dashboard_row=_dashboard(
        top_chase_card_histories_json={"v1": _history([DATE, "2026-08-04"])}
    ))
    assert SECTION_TOP_CHASE in row.failed_sections
    assert "future history date" in _section(row, SECTION_TOP_CHASE).detail


def test_top_chase_cross_set_history_fails():
    row = _audit(dashboard_row=_dashboard(
        top_chase_cards_json=[{"cardVariantId": "v1", "marketPrice": 12.5, "setId": "OTHER-SET"}]
    ))
    assert SECTION_TOP_CHASE in row.failed_sections
    assert "foreign set_id" in _section(row, SECTION_TOP_CHASE).detail


def test_top_chase_carried_forward_point_must_retain_its_real_source_date():
    row = _audit(dashboard_row=_dashboard(
        top_chase_card_histories_json={
            "v1": [
                {"date": PRIOR, "marketPrice": 10.0},
                {"date": DATE, "marketPrice": 10.0, "isCarriedForward": True},
            ]
        }
    ))
    assert SECTION_TOP_CHASE in row.failed_sections
    assert "sourceDate" in _section(row, SECTION_TOP_CHASE).detail


def test_top_chase_carried_forward_with_source_date_is_accepted():
    row = _audit(dashboard_row=_dashboard(
        top_chase_card_histories_json={
            "v1": [
                {"date": PRIOR, "marketPrice": 10.0},
                {"date": DATE, "marketPrice": 10.0, "isCarriedForward": True, "sourceDate": PRIOR},
            ]
        }
    ))
    assert SECTION_TOP_CHASE not in row.failed_sections


def test_top_chase_not_applicable_when_no_priced_cards():
    row = _audit(dashboard_row=_dashboard(top_chase_cards_json=[], top_chase_card_histories_json={}))
    assert _section(row, SECTION_TOP_CHASE).applicable is False
    assert SECTION_TOP_CHASE not in row.failed_sections


def test_carried_forward_simulation_point_cannot_establish_freshness():
    row = _audit(dashboard_row=_dashboard(performance_vs_cost_history_json=[
        {"date": PRIOR, "simulatedMeanPackValueVsPackCost": 1.1,
         "simulatedMedianPackValueVsPackCost": 0.9},
        {"date": DATE, "simulatedMeanPackValueVsPackCost": 1.1,
         "simulatedMedianPackValueVsPackCost": 0.9, "isCarriedForward": True},
    ]))
    assert SECTION_OPENING_PROFIT_VS_COST in row.failed_sections
    assert _section(row, SECTION_OPENING_PROFIT_VS_COST).observed_date == PRIOR


def test_opvc_not_required_for_non_simulation_sets():
    row = _audit(supports_simulation=False, dashboard_row=_dashboard(
        performance_vs_cost_history_json=[]
    ))
    assert _section(row, SECTION_OPENING_PROFIT_VS_COST).applicable is False
    assert SECTION_OPENING_PROFIT_VS_COST not in row.failed_sections


def test_sealed_required_only_when_the_set_has_a_sealed_product():
    without = _audit(has_sealed_product=False, sealed_row=None)
    assert _section(without, SECTION_SEALED_MARKET).applicable is False

    with_product = _audit(has_sealed_product=True, sealed_row=None)
    assert SECTION_SEALED_MARKET in with_product.failed_sections


def test_stale_sealed_snapshot_fails():
    row = _audit(sealed_row={"market_date": PRIOR})
    assert SECTION_SEALED_MARKET in row.failed_sections


def test_card_prices_generation_must_match_promoted_date():
    row = _audit(dashboard_row=_dashboard(latest_market_date=PRIOR))
    assert SECTION_CARD_PRICES in row.failed_sections


def test_header_must_not_advertise_a_newer_generation_than_its_sections():
    # Header says Aug 3, but the sealed section is still on Aug 2.
    row = _audit(sealed_row={"market_date": PRIOR})
    header = _section(row, SECTION_HEADER_SUMMARY)
    assert header.passed is False
    assert "sections are older" in header.detail


def test_missing_dashboard_row_fails_every_section():
    row = audit_market_set_row(
        canonical_key="testSet", set_id="set-1", set_name="Test Set",
        market_date=DATE, dashboard_row=None,
    )
    assert row.passed is False
    assert len(row.failed_sections) == 6
