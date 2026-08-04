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


def _cards(**overrides):
    """A published pokemon_set_cards_snapshot_latest row (its OWN source)."""
    row = {
        "set_id": "set-1",
        "payload_json": {"meta": {"pricingContract": {"latestMarketDate": DATE}}},
        "card_count": 1,
    }
    row.update(overrides)
    return row


def _page(**overrides):
    """A published pokemon_set_page_snapshot_latest row (its OWN source)."""
    row = {
        "set_id": "set-1",
        "payload_json": {"meta": {"snapshot": {"marketAsOfDate": DATE}}},
        "title_card_json": {},
        "market_summary_json": {"setValue": 100.0},
        "as_of": DATE,
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
        "cards_row": _cards(),
        "page_row": _page(),
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
    """Read from the CARDS snapshot's own payload contract, not the dashboard."""
    row = _audit(
        cards_row=_cards(payload_json={"meta": {"pricingContract": {"latestMarketDate": PRIOR}}})
    )
    assert SECTION_CARD_PRICES in row.failed_sections
    assert "cards snapshot market date" in _section(row, SECTION_CARD_PRICES).detail


def test_card_prices_ignore_a_fresh_dashboard_row_when_the_cards_snapshot_is_stale():
    """The regression: the dashboard's date is no longer accepted as proof."""
    row = _audit(
        dashboard_row=_dashboard(latest_market_date=DATE),
        cards_row=_cards(payload_json={"meta": {"pricingContract": {"latestMarketDate": PRIOR}}}),
    )
    assert SECTION_CARD_PRICES in row.failed_sections


def test_header_must_not_advertise_a_newer_generation_than_its_sections():
    # Header says Aug 3, but the sealed section is still on Aug 2.
    row = _audit(sealed_row={"market_date": PRIOR})
    header = _section(row, SECTION_HEADER_SUMMARY)
    assert header.passed is False
    assert "sections are older" in header.detail


def test_missing_dashboard_row_fails_only_the_sections_it_backs():
    """The dashboard backs Top Chase and OPvC; other surfaces have own sources."""
    row = audit_market_set_row(
        canonical_key="testSet", set_id="set-1", set_name="Test Set",
        market_date=DATE, dashboard_row=None,
        value_history=[{"date": DATE, "setValue": 100.0}],
        cards_row=_cards(), page_row=_page(),
        sealed_row={"market_date": DATE}, has_sealed_product=True,
        supports_simulation=True,
    )
    assert row.passed is False
    assert SECTION_TOP_CHASE in row.failed_sections
    assert SECTION_OPENING_PROFIT_VS_COST in row.failed_sections
    # These read their own sources and are current, so they must not be blamed.
    assert SECTION_CARD_PRICES not in row.failed_sections
    assert SECTION_SEALED_MARKET not in row.failed_sections
    assert SECTION_SET_VALUE not in row.failed_sections


# --- A: card prices read pokemon_set_cards_snapshot_latest -------------------
def test_missing_cards_snapshot_row_fails_card_prices():
    row = _audit(cards_row=None)
    assert SECTION_CARD_PRICES in row.failed_sections
    assert "no published card prices snapshot row" in _section(row, SECTION_CARD_PRICES).detail


def test_cards_snapshot_date_falls_back_to_published_card_price_dates():
    row = _audit(
        cards_row=_cards(
            payload_json={"meta": {}},
            cards_json=[{"id": "c1", "priceUpdatedAt": DATE}],
        )
    )
    assert SECTION_CARD_PRICES not in row.failed_sections


# --- B: header reads pokemon_set_page_snapshot_latest ------------------------
def test_missing_page_snapshot_row_fails_the_header():
    row = _audit(page_row=None)
    assert SECTION_HEADER_SUMMARY in row.failed_sections
    assert "no published set page snapshot row" in _section(row, SECTION_HEADER_SUMMARY).detail


def test_header_ahead_of_the_promoted_date_fails():
    row = _audit(
        page_row=_page(payload_json={"meta": {"snapshot": {"marketAsOfDate": "2026-08-04"}}})
    )
    header = _section(row, SECTION_HEADER_SUMMARY)
    assert header.passed is False
    assert "ahead of the promoted market date" in header.detail


def test_header_lagging_its_dependencies_is_allowed():
    """The page snapshot rebuilds on the simulation cadence; lagging is legal."""
    row = _audit(
        page_row=_page(
            payload_json={"meta": {"snapshot": {"marketAsOfDate": PRIOR}}},
            market_summary_json={},
        )
    )
    assert SECTION_HEADER_SUMMARY not in row.failed_sections


def test_header_date_is_derived_from_market_summary_when_meta_is_absent():
    row = _audit(
        page_row=_page(payload_json={}, market_summary_json={"latestMarketDate": DATE})
    )
    assert _section(row, SECTION_HEADER_SUMMARY).observed_date == DATE


# --- C: set-value displayed comparison ---------------------------------------
def test_displayed_set_value_disagreeing_with_final_history_point_fails():
    row = _audit(page_row=_page(market_summary_json={"setValue": 999.0}))
    assert SECTION_SET_VALUE in row.failed_sections
    assert "disagrees with final published history point" in _section(row, SECTION_SET_VALUE).detail


def test_absent_displayed_set_value_is_reported_not_silently_compared():
    """The defect: the old code compared against a column it never selected."""
    row = _audit(page_row=_page(market_summary_json={}, payload_json={}))
    verdict = _section(row, SECTION_SET_VALUE)
    assert verdict.passed is True
    assert "publishes no displayed set-value field" in verdict.detail


def test_displayed_set_value_matching_the_final_point_passes():
    row = _audit(
        value_history=[{"date": DATE, "setValue": 100.004}],
        page_row=_page(market_summary_json={"setValue": 100.0}),
    )
    assert SECTION_SET_VALUE not in row.failed_sections


# --- D: sealed applicability uses the real classifier ------------------------
def test_sealed_applicability_uses_the_builder_mapping_contract():
    from backend.scripts.audit_pokemon_market_publication import set_has_supported_sealed_product

    # Overview-eligible families make the section applicable.
    assert set_has_supported_sealed_product(["Scarlet & Violet Booster Box"]) is True
    assert set_has_supported_sealed_product(["Elite Trainer Box [Blue]"]) is True
    # A sealed product that the snapshot builder would never publish does not.
    assert set_has_supported_sealed_product(["Booster Box Case"]) is False
    assert set_has_supported_sealed_product(["Collector Chest"]) is False
    assert set_has_supported_sealed_product([]) is False


def test_set_with_only_unsupported_sealed_products_has_a_non_applicable_section():
    row = _audit(has_sealed_product=False, sealed_row=None)
    verdict = _section(row, SECTION_SEALED_MARKET)
    assert verdict.applicable is False
    assert SECTION_SEALED_MARKET not in row.failed_sections


# --- E: Top Chase structural contract ----------------------------------------
def test_top_chase_card_without_stable_identity_fails():
    row = _audit(dashboard_row=_dashboard(
        top_chase_cards_json=[
            {"cardVariantId": "v1", "marketPrice": 12.5, "setId": "set-1"},
            {"marketPrice": 9.0, "setId": "set-1"},
        ],
    ))
    assert SECTION_TOP_CHASE in row.failed_sections
    assert "no stable identity" in _section(row, SECTION_TOP_CHASE).detail


def test_top_chase_new_set_with_one_point_everywhere_is_not_applicable():
    row = _audit(dashboard_row=_dashboard(
        top_chase_card_histories_json={"v1": _history([DATE])},
    ))
    verdict = _section(row, SECTION_TOP_CHASE)
    assert verdict.applicable is False
    assert "too new for a trend" in verdict.detail


def test_top_chase_established_set_missing_history_on_one_card_fails():
    row = _audit(dashboard_row=_dashboard(
        top_chase_cards_json=[
            {"cardVariantId": "v1", "marketPrice": 12.5, "setId": "set-1"},
            {"cardVariantId": "v2", "marketPrice": 9.0, "setId": "set-1"},
        ],
        top_chase_card_histories_json={"v1": _history([PRIOR, DATE]), "v2": []},
    ))
    assert SECTION_TOP_CHASE in row.failed_sections


# --- OPvC applicability ------------------------------------------------------
def test_opvc_is_not_applicable_to_a_set_the_runner_never_executes():
    row = _audit(supports_simulation=False)
    verdict = _section(row, SECTION_OPENING_PROFIT_VS_COST)
    assert verdict.applicable is False
    assert SECTION_OPENING_PROFIT_VS_COST not in row.failed_sections


# --- source-table wiring ------------------------------------------------------
class _FakeResult:
    def __init__(self, data):
        self.data = data


class _FakeQuery:
    def __init__(self, db, table):
        self.db = db
        self.table_name = table
        self.filters = {}

    @property
    def not_(self):
        return self

    def is_(self, *_args):
        return self

    def select(self, _columns):
        return self

    def eq(self, column, value):
        self.filters[column] = value
        return self

    def in_(self, column, values):
        self.filters[column] = set(values)
        return self

    def gte(self, *_args):
        return self

    def order(self, *_args, **_kwargs):
        return self

    def limit(self, *_args):
        return self

    def execute(self):
        self.db.reads.append(self.table_name)
        rows = list(self.db.tables.get(self.table_name, []))
        for column, value in self.filters.items():
            if isinstance(value, set):
                rows = [r for r in rows if r.get(column) in value]
            else:
                rows = [r for r in rows if r.get(column) == value]
        return _FakeResult(rows)


class _FakeClient:
    def __init__(self, tables):
        self.tables = tables
        self.reads = []

    def table(self, name):
        return _FakeQuery(self, name)


def _publication_db(**overrides):
    tables = {
        "pokemon_scrape_batches": [
            {"market_date": DATE, "promoted_at": f"{DATE}T10:00:00Z", "status": "complete"}
        ],
        "sets": [
            {
                "id": "set-1",
                "name": "Test Set",
                "canonical_key": "testSet",
                "ready_for_daily_scrape": True,
                "catalog_only": False,
                "supports_opening_simulation": True,
                "has_sealed_details_url": True,
            }
        ],
        "pokemon_set_market_dashboard_snapshot_latest": [
            {"set_id": "set-1", "window_key": "365d", **_dashboard()}
        ],
        "pokemon_set_sealed_market_snapshot_latest": [
            {"set_id": "set-1", "market_date": DATE, "product_count": 1}
        ],
        "pokemon_set_cards_snapshot_latest": [_cards()],
        "pokemon_set_page_snapshot_latest": [_page()],
        "pokemon_set_value_daily_history": [
            {"set_id": "set-1", "snapshot_date": DATE, "set_value": 100.0, "value_scope": "standard"}
        ],
        "sealed_products": [{"set_id": "set-1", "name": "Test Set Booster Box"}],
    }
    tables.update(overrides)
    return _FakeClient(tables)


def test_audit_reads_every_declared_source_table():
    from backend.scripts.audit_pokemon_market_publication import run_market_publication_audit

    client = _publication_db()
    report = run_market_publication_audit(client)

    for table in (
        "pokemon_scrape_batches",
        "sets",
        "pokemon_set_market_dashboard_snapshot_latest",
        "pokemon_set_sealed_market_snapshot_latest",
        "pokemon_set_cards_snapshot_latest",
        "pokemon_set_page_snapshot_latest",
        "pokemon_set_value_daily_history",
        "sealed_products",
    ):
        assert table in client.reads, f"{table} was never read"

    assert report.market_date == DATE
    assert report.passed, report.to_dict()["failed_by_section"]


def test_audit_fails_closed_when_the_cards_snapshot_is_stale():
    from backend.scripts.audit_pokemon_market_publication import run_market_publication_audit

    client = _publication_db(
        pokemon_set_cards_snapshot_latest=[
            _cards(payload_json={"meta": {"pricingContract": {"latestMarketDate": PRIOR}}})
        ]
    )
    report = run_market_publication_audit(client)

    assert report.passed is False
    assert SECTION_CARD_PRICES in report.to_dict()["failed_by_section"]


def test_audit_marks_sealed_non_applicable_without_a_supported_product():
    from backend.scripts.audit_pokemon_market_publication import run_market_publication_audit

    client = _publication_db(
        sealed_products=[{"set_id": "set-1", "name": "Test Set Collector Chest"}],
        pokemon_set_sealed_market_snapshot_latest=[],
    )
    report = run_market_publication_audit(client)

    sealed = next(
        v for v in report.rows[0].sections if v.section == SECTION_SEALED_MARKET
    )
    assert sealed.applicable is False
    assert report.passed, report.to_dict()["failed_by_section"]


# --- Correction 5: identity handling ------------------------------------------
def test_priced_cards_without_identity_fail_rather_than_reporting_no_priced_cards():
    """The defect: applicability was derived from IDENTIFIED cards only.

    A row whose priced cards all lacked identities reported "no priced Top Chase
    cards" and passed as non-applicable, hiding a structurally broken row.
    """
    row = _audit(dashboard_row=_dashboard(
        top_chase_cards_json=[
            {"marketPrice": 12.5, "setId": "set-1"},
            {"marketPrice": 9.0, "setId": "set-1"},
        ],
        top_chase_card_histories_json={},
    ))
    verdict = _section(row, SECTION_TOP_CHASE)
    assert verdict.applicable is True, "priced cards exist, so the section applies"
    assert verdict.passed is False
    assert "no stable identity" in verdict.detail


def test_only_unpriced_cards_is_the_non_applicable_empty_state():
    row = _audit(dashboard_row=_dashboard(
        top_chase_cards_json=[{"cardVariantId": "v1", "marketPrice": 0, "setId": "set-1"}],
        top_chase_card_histories_json={},
    ))
    verdict = _section(row, SECTION_TOP_CHASE)
    assert verdict.applicable is False
    assert verdict.detail == "no priced Top Chase cards"


def test_priced_identified_card_with_missing_history_fails():
    row = _audit(dashboard_row=_dashboard(
        top_chase_cards_json=[{"cardVariantId": "v1", "marketPrice": 12.5, "setId": "set-1"}],
        top_chase_card_histories_json={},
    ))
    verdict = _section(row, SECTION_TOP_CHASE)
    assert verdict.applicable is True
    assert verdict.passed is False
    assert "usable history point" in verdict.detail


# --- Correction 4 (audit half): the new-set exception must be CURRENT ---------
def test_a_single_stale_point_fails_instead_of_being_called_a_new_set():
    row = _audit(dashboard_row=_dashboard(
        top_chase_card_histories_json={"v1": _history([PRIOR])},
    ))
    verdict = _section(row, SECTION_TOP_CHASE)
    assert verdict.applicable is True, "a stale single point is not a new set"
    assert verdict.passed is False


def test_a_single_current_point_on_every_card_is_a_new_set():
    row = _audit(dashboard_row=_dashboard(
        top_chase_card_histories_json={"v1": _history([DATE])},
    ))
    verdict = _section(row, SECTION_TOP_CHASE)
    assert verdict.applicable is False
    assert "too new for a trend" in verdict.detail
    assert DATE in verdict.detail


def test_a_new_set_exception_requires_every_priced_card_to_be_identified():
    row = _audit(dashboard_row=_dashboard(
        top_chase_cards_json=[
            {"cardVariantId": "v1", "marketPrice": 12.5, "setId": "set-1"},
            {"marketPrice": 9.0, "setId": "set-1"},
        ],
        top_chase_card_histories_json={"v1": _history([DATE])},
    ))
    verdict = _section(row, SECTION_TOP_CHASE)
    assert verdict.applicable is True
    assert verdict.passed is False


# --- Correction 6: the cards_json fallback is actually reachable --------------
def test_cards_json_price_dates_are_used_when_payload_meta_has_no_date():
    row = _audit(
        cards_row=_cards(
            payload_json={"meta": {}},
            cards_json=[
                {"id": "c1", "priceUpdatedAt": PRIOR},
                {"id": "c2", "priceUpdatedAt": DATE},
            ],
        )
    )
    verdict = _section(row, SECTION_CARD_PRICES)
    assert verdict.observed_date == DATE
    assert SECTION_CARD_PRICES not in row.failed_sections


def test_cards_snapshot_projection_selects_cards_json():
    """Without cards_json in the projection the fallback above can never fire."""
    from backend.scripts.audit_pokemon_market_publication import run_market_publication_audit

    selected = {}

    class _CapturingQuery(_FakeQuery):
        def select(self, columns):
            selected[self.table_name] = columns
            return self

    class _CapturingClient(_FakeClient):
        def table(self, name):
            return _CapturingQuery(self, name)

    client = _CapturingClient(_publication_db().tables)
    run_market_publication_audit(client)

    assert "cards_json" in selected["pokemon_set_cards_snapshot_latest"]


def test_audit_still_passes_using_only_the_cards_json_fallback_end_to_end():
    from backend.scripts.audit_pokemon_market_publication import run_market_publication_audit

    client = _publication_db(
        pokemon_set_cards_snapshot_latest=[
            _cards(payload_json={"meta": {}}, cards_json=[{"id": "c1", "priceUpdatedAt": DATE}])
        ]
    )
    report = run_market_publication_audit(client)

    assert report.passed, report.to_dict()["failed_by_section"]
