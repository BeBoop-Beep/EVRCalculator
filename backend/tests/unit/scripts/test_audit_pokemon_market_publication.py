"""Market publication audit: every public surface must reach the promoted date."""

from __future__ import annotations

from backend.scripts.audit_pokemon_market_publication import (
    EXPECTED_WINDOW_KEYS,
    SECTION_CARD_PRICES,
    SECTION_EXPLORE_SET_VALUE,
    SECTION_GLOBAL_SET_VALUE,
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


def _explore_target(**overrides):
    """A published Explore rankings target, as ExploreTopRankings consumes it."""
    target = {
        "set_id": "set-1",
        "canonical_key": "testSet",
        "checklistSetValue": 100.0,
        "checklistSetValueAsOf": DATE,
    }
    target.update(overrides)
    return target


def _explore_row(targets=None, **payload_overrides):
    """A pokemon_explore_rankings_snapshot_latest row."""
    payload = {
        "meta": {"snapshot": {"marketDate": DATE}},
        "targets": [_explore_target()] if targets is None else targets,
    }
    payload.update(payload_overrides)
    return {"tcg": "pokemon", "scope": "rip-statistics", "ranking_payload_json": payload,
            "updated_at": f"{DATE}T12:00:00Z"}


def _global_set_value_target(**overrides):
    """A published global Market Set Value row, as ExploreTopRankings consumes it."""
    target = {
        "setId": "set-1",
        "canonicalKey": "testSet",
        "name": "Test Set",
        "currentSetValue": 100.0,
        "setValueAsOf": DATE,
        "windows": {key: {"amount": 1.0, "percent": 1.0} for key in EXPECTED_WINDOW_KEYS},
        "trend": [[PRIOR, 99.0], [DATE, 100.0]],
    }
    target.update(overrides)
    return target


def _global_set_value_row(sets=None, **overrides):
    """A pokemon_explore_set_value_snapshot_latest row."""
    published = [_global_set_value_target()] if sets is None else sets
    payload = {"sets": published, "meta": {"snapshot": {"marketDate": DATE}}}
    if "payload_json" in overrides:
        payload = overrides.pop("payload_json")
    row = {
        "tcg": "pokemon",
        "scope": "market",
        "payload_json": payload,
        "market_date": DATE,
        "set_count": len(payload.get("sets") or []) if isinstance(payload, dict) else 0,
        "payload_size_bytes": 1024,
        "updated_at": f"{DATE}T12:00:00Z",
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
        "explore_target": _explore_target(),
        "global_set_value_target": _global_set_value_target(),
        "in_global_set_value_cohort": True,
        "canonical_set_value": 100.0,
    }
    kwargs.update(overrides)
    return audit_market_set_row(**kwargs)


def _section(row, name):
    return next(v for v in row.sections if v.section == name)


def test_fully_current_set_passes_every_section():
    row = _audit()
    assert row.passed, row.failed_sections
    assert len(row.sections) == 8


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
        self.in_column = None
        self.in_values = None

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
        self.in_column = column
        self.in_values = list(values)  # Store the actual list for chunk tracking
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
        # Record the .in_() call for this table if it was made
        if self.in_column is not None and self.in_values is not None:
            self.db.record_in_call(self.table_name, self.in_values)
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
        self.in_calls = {}  # table_name -> list of in_() call arguments

    def table(self, name):
        return _FakeQuery(self, name)

    def record_in_call(self, table_name, values):
        """Record a .in_() call for tracking chunk sizes."""
        if table_name not in self.in_calls:
            self.in_calls[table_name] = []
        self.in_calls[table_name].append(values)

    def calls_for(self, table_name, method_name):
        """Retrieve recorded calls of a given method (currently only 'in_' supported)."""
        if method_name == "in_":
            return self.in_calls.get(table_name, [])
        raise ValueError(f"unsupported method {method_name}")


class _SimulatedChunkFailure(Exception):
    """Raised by _FailingQuery to simulate a chunk-level read failure."""


class _FailingSecondChunkClient(_FakeClient):
    """A fake client that fails on the Nth .execute() call for a given table."""

    def __init__(self, set_ids, fail_on_chunk_index=1):
        """Initialize with set_ids and the 0-based chunk index to fail on."""
        # Create a minimal dataset for pokemon_set_market_dashboard_snapshot_latest
        tables = {
            "pokemon_set_market_dashboard_snapshot_latest": [
                {"set_id": sid, "top_chase_cards_json": []} for sid in set_ids
            ],
        }
        super().__init__(tables)
        self.fail_on_chunk_index = fail_on_chunk_index
        self.chunk_counts = {}  # table_name -> current chunk index

    def table(self, name):
        query = _FailingQuery(self, name)
        return query


class _FailingQuery(_FakeQuery):
    """A query that fails on a specific .execute() call."""

    def execute(self):
        table_name = self.table_name
        if table_name not in self.db.chunk_counts:
            self.db.chunk_counts[table_name] = 0

        chunk_idx = self.db.chunk_counts[table_name]
        self.db.chunk_counts[table_name] += 1

        if chunk_idx == self.db.fail_on_chunk_index:
            raise _SimulatedChunkFailure(f"Simulated failure on chunk {chunk_idx} for table {table_name}")

        return super().execute()


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
        "sealed_products": [{"id": "sp-1", "set_id": "set-1", "name": "Test Set Booster Box"}],
        "sealed_product_price_observations": [
            {"sealed_product_id": "sp-1", "captured_at": f"{DATE}T09:00:00Z"}
        ],
        "pokemon_explore_rankings_snapshot_latest": [_explore_row()],
        "pokemon_explore_set_value_snapshot_latest": [_global_set_value_row()],
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
    # The global Market Set Value artifact is its OWN source table.
    assert "payload_json" in selected["pokemon_explore_set_value_snapshot_latest"]
    assert "set_count" in selected["pokemon_explore_set_value_snapshot_latest"]
    # era_id backs the global Set Value cohort rule.
    assert "era_id" in selected["sets"]


def test_audit_still_passes_using_only_the_cards_json_fallback_end_to_end():
    from backend.scripts.audit_pokemon_market_publication import run_market_publication_audit

    client = _publication_db(
        pokemon_set_cards_snapshot_latest=[
            _cards(payload_json={"meta": {}}, cards_json=[{"id": "c1", "priceUpdatedAt": DATE}])
        ]
    )
    report = run_market_publication_audit(client)

    assert report.passed, report.to_dict()["failed_by_section"]


# --- post-scrape phase: OPvC is deferred, nothing else is ---------------------
def test_stale_opvc_does_not_fail_post_scrape_phase():
    """The early phase publishes pricing only; simulations run hours later."""
    from backend.scripts.audit_pokemon_market_publication import PHASE_POST_SCRAPE

    row = _audit(
        phase=PHASE_POST_SCRAPE,
        dashboard_row=_dashboard(performance_vs_cost_history_json=[
            {"date": PRIOR, "simulatedMeanPackValueVsPackCost": 1.1},
        ]),
    )
    verdict = _section(row, SECTION_OPENING_PROFIT_VS_COST)

    assert row.passed, row.failed_sections
    assert verdict.deferred is True
    assert verdict.applicable is False
    assert verdict.status == "deferred", "deferred must never be reported as passed"
    assert verdict.observed_date == PRIOR, "the real stale date must still be stated"


def test_missing_opvc_history_does_not_fail_post_scrape_phase():
    from backend.scripts.audit_pokemon_market_publication import PHASE_POST_SCRAPE

    row = _audit(
        phase=PHASE_POST_SCRAPE,
        dashboard_row=_dashboard(performance_vs_cost_history_json=[]),
    )
    assert row.passed, row.failed_sections
    assert _section(row, SECTION_OPENING_PROFIT_VS_COST).status == "deferred"


def test_the_same_stale_opvc_still_fails_the_full_phase():
    row = _audit(dashboard_row=_dashboard(performance_vs_cost_history_json=[
        {"date": PRIOR, "simulatedMeanPackValueVsPackCost": 1.1},
    ]))
    verdict = _section(row, SECTION_OPENING_PROFIT_VS_COST)

    assert verdict.applicable is True
    assert verdict.passed is False
    assert SECTION_OPENING_PROFIT_VS_COST in row.failed_sections


def test_missing_dashboard_row_defers_opvc_in_post_scrape_but_fails_in_full():
    from backend.scripts.audit_pokemon_market_publication import PHASE_POST_SCRAPE

    deferred = _section(_audit(dashboard_row=None, phase=PHASE_POST_SCRAPE),
                        SECTION_OPENING_PROFIT_VS_COST)
    required = _section(_audit(dashboard_row=None), SECTION_OPENING_PROFIT_VS_COST)

    assert deferred.status == "deferred"
    assert required.applicable is True and required.passed is False


def test_other_stale_sections_still_fail_post_scrape_phase():
    from backend.scripts.audit_pokemon_market_publication import PHASE_POST_SCRAPE

    row = _audit(
        phase=PHASE_POST_SCRAPE,
        value_history=[{"date": PRIOR, "setValue": 100.0}],
        sealed_row={"market_date": PRIOR},
        cards_row=_cards(payload_json={"meta": {"pricingContract": {"latestMarketDate": PRIOR}}}),
    )
    assert row.passed is False
    for section in (SECTION_SET_VALUE, SECTION_SEALED_MARKET, SECTION_CARD_PRICES):
        assert section in row.failed_sections


# --- Explore Top Rankings Set Value continuity --------------------------------
def test_explore_set_value_current_and_matching_canonical_passes():
    verdict = _section(_audit(), SECTION_EXPLORE_SET_VALUE)
    assert verdict.applicable is True
    assert verdict.passed is True


def test_explore_set_value_dated_one_day_behind_fails():
    """The August-4 production failure: Explore still advertised August 3."""
    row = _audit(
        explore_target=_explore_target(
            checklistSetValue=6535.55, checklistSetValueAsOf=PRIOR,
        ),
        canonical_set_value=6444.06,
    )
    verdict = _section(row, SECTION_EXPLORE_SET_VALUE)

    assert verdict.passed is False
    assert PRIOR in verdict.detail
    assert SECTION_EXPLORE_SET_VALUE in row.failed_sections


def test_explore_set_value_dated_today_with_yesterdays_number_fails():
    """A relabeled date over a stale number is the worst case, not the best."""
    row = _audit(
        explore_target=_explore_target(checklistSetValue=6535.55, checklistSetValueAsOf=DATE),
        canonical_set_value=6444.06,
    )
    verdict = _section(row, SECTION_EXPLORE_SET_VALUE)

    assert verdict.passed is False
    assert "disagrees with the canonical" in verdict.detail


def test_explore_set_value_matching_to_the_cent_passes():
    row = _audit(
        explore_target=_explore_target(checklistSetValue=6444.061, checklistSetValueAsOf=DATE),
        canonical_set_value=6444.058,
    )
    assert _section(row, SECTION_EXPLORE_SET_VALUE).passed is True


def test_explore_set_value_snake_case_aliases_are_handled():
    row = _audit(explore_target={
        "set_id": "set-1",
        "checklist_set_value": 100.0,
        "checklist_set_value_as_of": DATE,
    })
    assert _section(row, SECTION_EXPLORE_SET_VALUE).passed is True


def test_explore_target_outside_the_cohort_is_not_required():
    """The Explore cohort is narrower than the publication-required cohort."""
    verdict = _section(_audit(explore_target=None), SECTION_EXPLORE_SET_VALUE)
    assert verdict.applicable is False
    assert verdict.passed is True


def test_explore_target_without_a_checklist_set_value_is_not_required():
    verdict = _section(
        _audit(explore_target={"set_id": "set-1"}), SECTION_EXPLORE_SET_VALUE
    )
    assert verdict.applicable is False


def test_explore_set_value_missing_canonical_history_row_fails():
    row = _audit(explore_target=_explore_target(), canonical_set_value=None)
    verdict = _section(row, SECTION_EXPLORE_SET_VALUE)
    assert verdict.passed is False
    assert "no canonical" in verdict.detail


def test_explore_set_value_non_positive_value_fails():
    row = _audit(explore_target=_explore_target(checklistSetValue=0))
    verdict = _section(row, SECTION_EXPLORE_SET_VALUE)
    assert verdict.applicable is True and verdict.passed is False
    assert "finite positive" in verdict.detail


def test_explore_snapshot_wide_problem_fails_every_set():
    row = _audit(explore_snapshot_problem_detail="no published Explore rankings snapshot row")
    verdict = _section(row, SECTION_EXPLORE_SET_VALUE)
    assert verdict.applicable is True
    assert verdict.passed is False


def test_explore_snapshot_problem_detects_missing_malformed_and_stale():
    from backend.scripts.audit_pokemon_market_publication import explore_snapshot_problem

    assert "no published Explore rankings snapshot" in explore_snapshot_problem(DATE, None)
    assert "not an object" in explore_snapshot_problem(
        DATE, {"ranking_payload_json": "not-json-at-all"}
    )
    assert "not an array" in explore_snapshot_problem(
        DATE, {"ranking_payload_json": {"meta": {"snapshot": {"marketDate": DATE}}, "targets": {}}}
    )
    assert "does not match promoted market date" in explore_snapshot_problem(
        DATE, _explore_row(**{"meta": {"snapshot": {"marketDate": PRIOR}}})
    )
    assert explore_snapshot_problem(DATE, _explore_row()) is None


def test_explore_snapshot_freshness_is_never_taken_from_updated_at():
    """A rebuild that republishes yesterday's numbers still bumps updated_at."""
    from backend.scripts.audit_pokemon_market_publication import explore_snapshot_problem

    stale = _explore_row(**{"meta": {"snapshot": {"marketDate": PRIOR}}})
    stale["updated_at"] = f"{DATE}T23:59:59Z"
    assert explore_snapshot_problem(DATE, stale) is not None


def test_explore_snapshot_date_falls_back_to_the_comparison_contract_path():
    from backend.scripts.audit_pokemon_market_publication import explore_snapshot_market_date

    row = _explore_row(**{"meta": {"comparisonSnapshots": {"currentMarketDate": DATE}}})
    assert explore_snapshot_market_date(row) == DATE


# --- Explore continuity end to end, in BOTH phases ----------------------------
def test_stale_explore_snapshot_fails_the_post_scrape_audit():
    from backend.scripts.audit_pokemon_market_publication import (
        PHASE_POST_SCRAPE,
        run_market_publication_audit,
    )

    client = _publication_db(pokemon_explore_rankings_snapshot_latest=[
        _explore_row(**{"meta": {"snapshot": {"marketDate": PRIOR}}})
    ])
    report = run_market_publication_audit(client, phase=PHASE_POST_SCRAPE)

    assert report.passed is False
    assert SECTION_EXPLORE_SET_VALUE in report.to_dict()["failed_by_section"]


def test_stale_explore_target_value_fails_the_full_audit_too():
    """The later coordinated publication cannot claim success while Explore is stale."""
    from backend.scripts.audit_pokemon_market_publication import run_market_publication_audit

    client = _publication_db(pokemon_explore_rankings_snapshot_latest=[
        _explore_row(targets=[_explore_target(checklistSetValue=93.5)])
    ])
    report = run_market_publication_audit(client)

    assert report.passed is False
    assert SECTION_EXPLORE_SET_VALUE in report.to_dict()["failed_by_section"]


def test_missing_explore_snapshot_fails_the_audit():
    from backend.scripts.audit_pokemon_market_publication import run_market_publication_audit

    report = run_market_publication_audit(
        _publication_db(pokemon_explore_rankings_snapshot_latest=[])
    )
    assert report.passed is False
    assert SECTION_EXPLORE_SET_VALUE in report.to_dict()["failed_by_section"]


def test_audit_reads_the_explore_and_sealed_source_tables():
    from backend.scripts.audit_pokemon_market_publication import run_market_publication_audit

    client = _publication_db()
    run_market_publication_audit(client)

    assert "pokemon_explore_rankings_snapshot_latest" in client.reads
    assert "sealed_product_price_observations" in client.reads


# --- sealed source freshness ---------------------------------------------------
def test_sealed_source_observation_for_the_promoted_date_fails_a_prior_day_snapshot():
    """The production case: >100 sealed snapshots behind their own source."""
    row = _audit(sealed_row={"market_date": PRIOR}, sealed_source_latest_date=DATE)
    verdict = _section(row, SECTION_SEALED_MARKET)

    assert verdict.applicable is True
    assert verdict.passed is False
    assert "sealed source has an observation" in verdict.detail


def test_sealed_source_and_snapshot_both_on_the_promoted_date_passes():
    row = _audit(sealed_row={"market_date": DATE}, sealed_source_latest_date=DATE)
    assert _section(row, SECTION_SEALED_MARKET).passed is True


def test_sealed_source_freshness_end_to_end_fails_post_scrape():
    from backend.scripts.audit_pokemon_market_publication import (
        PHASE_POST_SCRAPE,
        run_market_publication_audit,
    )

    client = _publication_db(pokemon_set_sealed_market_snapshot_latest=[
        {"set_id": "set-1", "market_date": PRIOR, "product_count": 1}
    ])
    report = run_market_publication_audit(client, phase=PHASE_POST_SCRAPE)

    assert report.passed is False
    assert SECTION_SEALED_MARKET in report.to_dict()["failed_by_section"]


def test_no_overview_eligible_product_leaves_sealed_non_applicable():
    from backend.scripts.audit_pokemon_market_publication import run_market_publication_audit

    client = _publication_db(
        # A collector chest is classified as NOT overview-eligible by the builder.
        sealed_products=[{"id": "sp-1", "set_id": "set-1", "name": "Test Set Collector Chest"}],
        pokemon_set_sealed_market_snapshot_latest=[],
    )
    report = run_market_publication_audit(client)
    sealed = next(v for v in report.rows[0].sections if v.section == SECTION_SEALED_MARKET)

    assert sealed.applicable is False
    assert report.passed, report.to_dict()["failed_by_section"]


def test_excluded_product_families_do_not_create_a_false_sealed_failure():
    """An excluded product with a fresh observation owes no Overview snapshot."""
    from backend.scripts.audit_pokemon_market_publication import run_market_publication_audit

    client = _publication_db(
        sealed_products=[{"id": "sp-1", "set_id": "set-1", "name": "Test Set Collector Chest"}],
        sealed_product_price_observations=[
            {"sealed_product_id": "sp-1", "captured_at": f"{DATE}T09:00:00Z"}
        ],
        pokemon_set_sealed_market_snapshot_latest=[
            {"set_id": "set-1", "market_date": PRIOR, "product_count": 1}
        ],
    )
    report = run_market_publication_audit(client)

    assert SECTION_SEALED_MARKET not in report.to_dict().get("failed_by_section", {})


def test_sealed_freshness_is_not_derived_from_card_or_dashboard_timestamps():
    """A fresh dashboard/cards row must not excuse a sealed snapshot."""
    row = _audit(
        dashboard_row=_dashboard(latest_market_date=DATE),
        cards_row=_cards(),
        sealed_row={"market_date": PRIOR},
        sealed_source_latest_date=DATE,
    )
    assert _section(row, SECTION_SEALED_MARKET).passed is False


# --- phase plumbing ------------------------------------------------------------
def test_report_records_its_phase_and_defaults_to_full():
    from backend.scripts.audit_pokemon_market_publication import (
        PHASE_FULL,
        PHASE_POST_SCRAPE,
        run_market_publication_audit,
    )

    assert run_market_publication_audit(_publication_db()).to_dict()["phase"] == PHASE_FULL
    assert (
        run_market_publication_audit(_publication_db(), phase=PHASE_POST_SCRAPE).to_dict()["phase"]
        == PHASE_POST_SCRAPE
    )


def test_cli_defaults_to_the_full_phase():
    from backend.scripts.audit_pokemon_market_publication import PHASE_FULL, build_parser

    assert build_parser().parse_args([]).phase == PHASE_FULL
    assert build_parser().parse_args(["--phase", "post-scrape"]).phase == "post-scrape"


def test_deferred_sections_are_stated_in_the_text_report():
    from backend.scripts.audit_pokemon_market_publication import (
        PHASE_POST_SCRAPE,
        format_report_lines,
        run_market_publication_audit,
    )

    client = _publication_db(pokemon_set_market_dashboard_snapshot_latest=[
        {"set_id": "set-1", "window_key": "365d",
         **_dashboard(performance_vs_cost_history_json=[
             {"date": PRIOR, "simulatedMeanPackValueVsPackCost": 1.1}])}
    ])
    report = run_market_publication_audit(client, phase=PHASE_POST_SCRAPE)
    text = "\n".join(format_report_lines(report))

    assert report.passed, report.to_dict()["failed_by_section"]
    assert "DEFERRED" in text
    assert SECTION_OPENING_PROFIT_VS_COST in text


# --------------------------------------------------------------------------
# Global Market Set Value snapshot - the artifact /Market's Set Value ladder
# actually renders. The Explore RIP rankings artifact above is a different
# public surface, and its health proves nothing about this one.
# --------------------------------------------------------------------------
def test_global_set_value_window_keys_match_the_builder_contract():
    """The audit's mirrored window list must never drift from the builder's."""
    from backend.db.services.pokemon_explore_set_value_service import WINDOWS

    assert EXPECTED_WINDOW_KEYS == tuple(key for key, _ in WINDOWS)


def test_missing_global_set_value_snapshot_fails_the_audit():
    """The exact production state: the table exists but holds zero rows."""
    from backend.scripts.audit_pokemon_market_publication import run_market_publication_audit

    report = run_market_publication_audit(
        _publication_db(pokemon_explore_set_value_snapshot_latest=[])
    )

    assert not report.passed
    assert SECTION_GLOBAL_SET_VALUE in report.to_dict()["failed_by_section"]
    detail = _section(report.rows[0], SECTION_GLOBAL_SET_VALUE).detail
    assert "no published global Market Set Value snapshot row" in detail


def test_explore_rankings_health_cannot_vouch_for_the_global_set_value_artifact():
    """A perfectly current RIP rankings snapshot must not excuse an absent one."""
    from backend.scripts.audit_pokemon_market_publication import run_market_publication_audit

    report = run_market_publication_audit(
        _publication_db(pokemon_explore_set_value_snapshot_latest=[])
    )

    assert _section(report.rows[0], SECTION_EXPLORE_SET_VALUE).passed is True
    assert _section(report.rows[0], SECTION_GLOBAL_SET_VALUE).passed is False
    assert not report.passed


def test_global_set_value_snapshot_on_the_wrong_market_date_fails():
    from backend.scripts.audit_pokemon_market_publication import run_market_publication_audit

    report = run_market_publication_audit(
        _publication_db(pokemon_explore_set_value_snapshot_latest=[
            _global_set_value_row(market_date=PRIOR)
        ])
    )

    assert not report.passed
    assert "does not match promoted market date" in _section(
        report.rows[0], SECTION_GLOBAL_SET_VALUE
    ).detail


def test_global_set_value_payload_date_behind_the_row_date_fails():
    """updated_at and the row column cannot vouch for a stale payload."""
    from backend.scripts.audit_pokemon_market_publication import run_market_publication_audit

    stale_payload = {
        "sets": [_global_set_value_target()],
        "meta": {"snapshot": {"marketDate": PRIOR}},
    }
    report = run_market_publication_audit(
        _publication_db(pokemon_explore_set_value_snapshot_latest=[
            _global_set_value_row(payload_json=stale_payload, set_count=1)
        ])
    )

    assert not report.passed
    assert "meta.snapshot.marketDate" in _section(report.rows[0], SECTION_GLOBAL_SET_VALUE).detail


def test_global_set_value_incomplete_cohort_fails():
    """An eligible set absent from the payload is a hard failure."""
    from backend.scripts.audit_pokemon_market_publication import run_market_publication_audit

    report = run_market_publication_audit(
        _publication_db(pokemon_explore_set_value_snapshot_latest=[
            _global_set_value_row(sets=[])
        ])
    )

    assert not report.passed
    assert "missing 1 eligible cohort set" in _section(
        report.rows[0], SECTION_GLOBAL_SET_VALUE
    ).detail


def test_global_set_value_out_of_cohort_set_fails():
    from backend.scripts.audit_pokemon_market_publication import run_market_publication_audit

    report = run_market_publication_audit(
        _publication_db(pokemon_explore_set_value_snapshot_latest=[
            _global_set_value_row(sets=[
                _global_set_value_target(),
                _global_set_value_target(setId="intruder-1", canonicalKey="intruder"),
            ])
        ])
    )

    assert not report.passed
    assert "out-of-cohort" in _section(report.rows[0], SECTION_GLOBAL_SET_VALUE).detail


def test_global_set_value_duplicate_set_id_fails():
    from backend.scripts.audit_pokemon_market_publication import run_market_publication_audit

    report = run_market_publication_audit(
        _publication_db(pokemon_explore_set_value_snapshot_latest=[
            _global_set_value_row(sets=[_global_set_value_target(), _global_set_value_target()])
        ])
    )

    assert not report.passed
    assert "duplicate setId" in _section(report.rows[0], SECTION_GLOBAL_SET_VALUE).detail


def test_global_set_value_set_count_disagreeing_with_payload_fails():
    from backend.scripts.audit_pokemon_market_publication import run_market_publication_audit

    report = run_market_publication_audit(
        _publication_db(pokemon_explore_set_value_snapshot_latest=[
            _global_set_value_row(set_count=99)
        ])
    )

    assert not report.passed
    assert "set_count" in _section(report.rows[0], SECTION_GLOBAL_SET_VALUE).detail


def test_global_set_value_malformed_sets_array_fails():
    from backend.scripts.audit_pokemon_market_publication import run_market_publication_audit

    report = run_market_publication_audit(
        _publication_db(pokemon_explore_set_value_snapshot_latest=[
            _global_set_value_row(payload_json={"sets": {}, "meta": {}})
        ])
    )

    assert not report.passed
    assert "is not an array" in _section(report.rows[0], SECTION_GLOBAL_SET_VALUE).detail


def test_global_set_value_non_positive_current_value_fails():
    row = _audit(global_set_value_target=_global_set_value_target(currentSetValue=0))
    assert SECTION_GLOBAL_SET_VALUE in row.failed_sections
    assert "not a finite positive number" in _section(row, SECTION_GLOBAL_SET_VALUE).detail


def test_global_set_value_stale_as_of_fails():
    row = _audit(global_set_value_target=_global_set_value_target(setValueAsOf=PRIOR))
    assert SECTION_GLOBAL_SET_VALUE in row.failed_sections
    assert "not the promoted market date" in _section(row, SECTION_GLOBAL_SET_VALUE).detail


def test_global_set_value_must_agree_with_canonical_history():
    row = _audit(
        global_set_value_target=_global_set_value_target(currentSetValue=123.45),
        canonical_set_value=100.0,
    )
    assert SECTION_GLOBAL_SET_VALUE in row.failed_sections
    assert "disagrees with the canonical" in _section(row, SECTION_GLOBAL_SET_VALUE).detail


def test_every_client_selectable_window_must_survive_into_the_snapshot():
    """A missing window key is a dead /Market pill, not a lazy computation."""
    for missing in EXPECTED_WINDOW_KEYS:
        windows = {key: {"amount": 1.0} for key in EXPECTED_WINDOW_KEYS if key != missing}
        row = _audit(global_set_value_target=_global_set_value_target(windows=windows))
        assert SECTION_GLOBAL_SET_VALUE in row.failed_sections, missing
        assert missing in _section(row, SECTION_GLOBAL_SET_VALUE).detail


def test_set_outside_the_global_cohort_is_non_applicable_not_failed():
    row = _audit(global_set_value_target=None, in_global_set_value_cohort=False)
    assert _section(row, SECTION_GLOBAL_SET_VALUE).applicable is False
    assert SECTION_GLOBAL_SET_VALUE not in row.failed_sections


def test_eligible_set_with_no_published_row_fails():
    row = _audit(global_set_value_target=None, in_global_set_value_cohort=True)
    assert SECTION_GLOBAL_SET_VALUE in row.failed_sections
    assert "publishes no snapshot row" in _section(row, SECTION_GLOBAL_SET_VALUE).detail


def test_global_cohort_is_computed_before_the_set_filter_is_applied():
    """`--set one-set` must not make an incomplete global snapshot look complete."""
    from backend.scripts.audit_pokemon_market_publication import run_market_publication_audit

    tables = dict(_publication_db().tables)
    tables["sets"] = list(tables["sets"]) + [
        {
            "id": "set-2",
            "name": "Second Set",
            "canonical_key": "secondSet",
            "ready_for_daily_scrape": True,
            "catalog_only": False,
            "supports_opening_simulation": True,
            "has_sealed_details_url": False,
        }
    ]
    report = run_market_publication_audit(_FakeClient(tables), canonical_keys=["testSet"])

    assert len(report.rows) == 1
    assert not report.passed
    assert "missing 1 eligible cohort set" in _section(
        report.rows[0], SECTION_GLOBAL_SET_VALUE
    ).detail


# --- _load_rows chunking tests -----------------------------------------------
def test_heavy_json_table_reads_use_bounded_chunks_below_full_cohort():
    """Chunk-size cohorts must generate multiple .in_('set_id', ...)
    requests, and no single request may exceed the configured bound."""
    from backend.scripts import audit_pokemon_market_publication as audit

    set_ids = [f"set-{i}" for i in range(25)]
    client = _FakeClient({
        "pokemon_set_market_dashboard_snapshot_latest": [
            {"set_id": sid, "top_chase_cards_json": []} for sid in set_ids
        ],
    })

    rows = audit._load_rows(
        client, "pokemon_set_market_dashboard_snapshot_latest",
        "set_id,top_chase_cards_json", set_ids, chunk_size=10,
    )

    in_calls = client.calls_for("pokemon_set_market_dashboard_snapshot_latest", "in_")
    assert len(in_calls) == 3  # 25 sets / 10 per request -> 3 requests
    assert all(len(call_args) <= 10 for call_args in in_calls)
    assert set(rows.keys()) == set(set_ids)  # full coverage, merged deterministically


def test_missing_sets_still_detected_across_chunked_reads():
    """Missing sets must still be detected even when reading in chunks."""
    from backend.scripts import audit_pokemon_market_publication as audit

    set_ids = [f"set-{i}" for i in range(15)]
    present_ids = set_ids[:12]  # 3 sets never come back
    client = _FakeClient({
        "pokemon_set_market_dashboard_snapshot_latest": [
            {"set_id": sid, "top_chase_cards_json": []} for sid in present_ids
        ],
    })

    rows = audit._load_rows(
        client, "pokemon_set_market_dashboard_snapshot_latest",
        "set_id,top_chase_cards_json", set_ids, chunk_size=10,
    )

    missing = set(set_ids) - set(rows.keys())
    assert missing == set(set_ids[12:])


def test_later_chunk_failure_raises_not_silently_partial():
    """A later chunk raising must fail the whole audit read, never return
    a partial success that could be mistaken for a clean cohort."""
    from backend.scripts import audit_pokemon_market_publication as audit
    import pytest

    set_ids = [f"set-{i}" for i in range(15)]
    client = _FailingSecondChunkClient(set_ids, fail_on_chunk_index=1)

    with pytest.raises(_SimulatedChunkFailure):
        audit._load_rows(
            client, "pokemon_set_market_dashboard_snapshot_latest",
            "set_id,top_chase_cards_json", set_ids, chunk_size=10,
        )
