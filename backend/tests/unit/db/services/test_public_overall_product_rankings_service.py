from backend.db.services import public_overall_product_rankings_service as service
from backend.calculations.evr import budget_normalized_product_ranking as bnpr


def test_overall_projection_preserves_loose_pack_artwork_identity(monkeypatch):
    monkeypatch.setattr(service, "load_latest_snapshot", lambda _client: {"full_market_budget": 150.0})
    monkeypatch.setattr(service, "load_full_market_ranking", lambda _client, **_kwargs: {
        "rows": [{
            "sealed_product_id": "pack-1", "set_id": "set-1", "product_family": "loose_booster_pack",
            "budget_rank": 1, "budget_cohort_size": 1, "quantity": 1,
            "actual_committed_capital": 10, "unused_capital": 140,
            "overall_rip_v10_score": 50, "financial_rip_v4_score": 40,
            "collector_appeal_score": 30, "product_market_price": 10,
            "expected_value": 8, "chance_to_recover_capital": .25,
        }],
        "authority": {},
    })
    monkeypatch.setattr(service, "public_budget_cohort_presentation", lambda _rows, _snapshot: {"pack-1": {
        "publicTier": "S", "overallRipLeaderScore": 100, "financialRipLeaderScore": 100,
        "overallRipScore": 50, "budgetRank": 1, "budgetCohortSize": 1,
    }})
    family_payload = {"families": {"loose_booster_pack": {"products": [{
        "sealedProductId": "pack-1", "productName": "Alpha Booster Pack", "setName": "Alpha",
        "productFamilyLabel": "Loose Booster Pack", "productImageUrl": None,
        "setCanonicalKey": "alphaSet", "familyRank": 1, "familySize": 1,
        "chaseAccessibility": {"value": 0.02, "percent": 2.0, "setRank": 3, "setCohortSize": 10},
    }]}}}

    result = service.read_public_overall_product_rankings(
        product_family_rankings=family_payload, client=object()
    )

    assert result["available"] is True
    assert result["rows"][0]["setCanonicalKey"] == "alphaSet"
    assert result["rows"][0]["productFamily"] == "loose_booster_pack"


# The budget/"All Products" overall projection must carry the SAME set-level
# Chase Accessibility authority block as the per-family projection
# (product_family_rankings_service.py), lifted verbatim off the identity index
# this function already builds from `product_family_rankings` — no new query.
def test_overall_projection_carries_chase_accessibility_authority_block(monkeypatch):
    monkeypatch.setattr(service, "load_latest_snapshot", lambda _client: {"full_market_budget": 150.0})
    monkeypatch.setattr(service, "load_full_market_ranking", lambda _client, **_kwargs: {
        "rows": [{
            "sealed_product_id": "pack-1", "set_id": "set-1", "product_family": "loose_booster_pack",
            "budget_rank": 1, "budget_cohort_size": 1, "quantity": 1,
            "actual_committed_capital": 10, "unused_capital": 140,
            "overall_rip_v10_score": 50, "financial_rip_v4_score": 40,
            "collector_appeal_score": 30, "product_market_price": 10,
            "expected_value": 8, "chance_to_recover_capital": .25,
        }],
        "authority": {},
    })
    monkeypatch.setattr(service, "public_budget_cohort_presentation", lambda _rows, _snapshot: {"pack-1": {
        "publicTier": "S", "overallRipLeaderScore": 100, "financialRipLeaderScore": 100,
        "overallRipScore": 50, "budgetRank": 1, "budgetCohortSize": 1,
    }})
    chase_block = {"value": 0.02, "percent": 2.0, "setRank": 3, "setCohortSize": 10}
    family_payload = {"families": {"loose_booster_pack": {"products": [{
        "sealedProductId": "pack-1", "productName": "Alpha Booster Pack", "setName": "Alpha",
        "productFamilyLabel": "Loose Booster Pack", "productImageUrl": None,
        "setCanonicalKey": "alphaSet", "familyRank": 1, "familySize": 1,
        "chaseAccessibility": chase_block,
    }]}}}

    result = service.read_public_overall_product_rankings(
        product_family_rankings=family_payload, client=object()
    )

    assert result["rows"][0]["chaseAccessibility"] == chase_block


def _authority_case(monkeypatch, *, v12_authority, v12_score, v12_rank, v12_size):
    snapshot = {
        "full_market_budget": 150.0,
        "ranked_under_v12_authority": v12_authority,
    }
    row = {
        "sealed_product_id": "pack-1", "set_id": "set-1",
        "product_family": "loose_booster_pack", "quantity": 1,
        "actual_committed_capital": 10, "unused_capital": 140,
        "overall_rip_v10_score": 10, "budget_rank": 9, "budget_cohort_size": 10,
        "overall_rip_v12_score": v12_score, "budget_rank_v12": v12_rank,
        "budget_cohort_size_v12": v12_size, "financial_rip_v4_score": 40,
        "collector_appeal_score": 30, "product_market_price": 10,
        "expected_value": 8, "chance_to_recover_capital": .25,
    }
    monkeypatch.setattr(service, "load_latest_snapshot", lambda _client: snapshot)
    monkeypatch.setattr(service, "load_full_market_ranking", lambda _client, **_kwargs: {
        "rows": [row], "authority": {"rankedUnderV12Authority": v12_authority},
    })
    return service.read_public_overall_product_rankings(
        product_family_rankings={"families": {"loose_booster_pack": {"products": [{
            "sealedProductId": "pack-1", "productName": "Alpha Booster Pack",
            "setName": "Alpha", "productFamilyLabel": "Loose Booster Pack",
        }]}}},
        client=object(),
    )


def test_live_v12_budget_read_uses_v12_generic_score_rank_and_cohort(monkeypatch):
    result = _authority_case(
        monkeypatch, v12_authority=True, v12_score=90, v12_rank=1, v12_size=7,
    )
    assert result["available"] is True
    assert result["rows"][0]["overallRipScore"] == 90
    assert result["rows"][0]["overallRipAbsoluteScore"] == 90
    assert result["rows"][0]["budgetRank"] == 1
    assert result["rows"][0]["budgetCohortSize"] == 7
    assert "O_budget" not in result["rows"][0]
    assert "ECE" not in result["rows"][0]


def test_live_historical_v10_budget_read_remains_readable(monkeypatch):
    result = _authority_case(
        monkeypatch, v12_authority=False, v12_score=90, v12_rank=1, v12_size=7,
    )
    assert result["available"] is True
    assert result["rows"][0]["overallRipScore"] == 10
    assert result["rows"][0]["budgetRank"] == 9
    assert result["rows"][0]["budgetCohortSize"] == 10


def test_live_malformed_v12_budget_read_fails_closed_without_mixing_authority(monkeypatch):
    result = _authority_case(
        monkeypatch, v12_authority=True, v12_score=90, v12_rank=None, v12_size=7,
    )
    assert result == {"available": False, "reason": "public_projection_incomplete", "rows": []}


def test_live_v12_budget_read_missing_score_fails_closed(monkeypatch):
    result = _authority_case(
        monkeypatch, v12_authority=True, v12_score=None, v12_rank=1, v12_size=7,
    )
    assert result == {"available": False, "reason": "public_projection_incomplete", "rows": []}


# --- Prepared Budget Product Rankings DB contract: median_value /
# top1_outcome_value_share / averageReturn (source-side bridge) ----------


def _prepared_row(**overrides):
    row = {
        "sealed_product_id": "pack-1", "set_id": "set-1", "product_family": "loose_booster_pack",
        "budget_rank": 1, "budget_cohort_size": 1, "quantity": 1,
        "actual_committed_capital": 20.0, "unused_capital": 5.0,
        "overall_rip_v10_score": 50, "financial_rip_v4_score": 40,
        "collector_appeal_score": 30, "product_market_price": 10,
        "expected_value": 30.0, "chance_to_recover_capital": .25,
        "median_value": 28.0, "top1_outcome_value_share": 0.12,
    }
    row.update(overrides)
    return row


def _prepared_read(monkeypatch, row):
    monkeypatch.setattr(service, "load_latest_snapshot", lambda _client: {"full_market_budget": 150.0})
    monkeypatch.setattr(service, "load_full_market_ranking", lambda _client, **_kwargs: {
        "rows": [row], "authority": {},
    })
    monkeypatch.setattr(service, "public_budget_cohort_presentation", lambda _rows, _snapshot: {"pack-1": {
        "publicTier": "S", "overallRipLeaderScore": 100, "financialRipLeaderScore": 100,
        "overallRipScore": 50, "budgetRank": 1, "budgetCohortSize": 1,
    }})
    family_payload = {"families": {"loose_booster_pack": {"products": [{
        "sealedProductId": "pack-1", "productName": "Alpha Booster Pack", "setName": "Alpha",
        "productFamilyLabel": "Loose Booster Pack", "productImageUrl": None,
        "setCanonicalKey": "alphaSet", "familyRank": 1, "familySize": 1,
    }]}}}
    return service.read_public_overall_product_rankings(product_family_rankings=family_payload, client=object())


def test_prepared_read_exposes_persisted_median_and_top1_outcome_value_share_round_trip(monkeypatch):
    """Requirement 4: the reader exposes exactly the persisted values, not a
    recomputation — round-trip proof."""
    row = _prepared_row(median_value=27.5, top1_outcome_value_share=0.137)
    result = _prepared_read(monkeypatch, row)
    assert result["rows"][0]["medianValue"] == 27.5
    assert result["rows"][0]["topOneOutcomeValueShare"] == 0.137


def test_prepared_read_average_return_denominator_is_actual_committed_capital(monkeypatch):
    """Requirement 3: Average Return = expected_value / actual_committed_capital,
    never the target budget band or a one-unit price."""
    row = _prepared_row(expected_value=30.0, actual_committed_capital=20.0, product_market_price=10.0)
    result = _prepared_read(monkeypatch, row)
    assert result["rows"][0]["averageReturn"] == 30.0 / 20.0
    assert result["rows"][0]["averageReturn"] != 30.0 / 10.0  # not one-unit price
    assert result["rows"][0]["averageReturn"] != 30.0 / 25.0  # not a target-budget band


def test_prepared_read_never_calls_score_budget_strategy(monkeypatch):
    """Requirement 6: no request-time strategy scoring on the read path."""
    def _forbidden(*_args, **_kwargs):
        raise AssertionError("score_budget_strategy must never be called from the read path")

    monkeypatch.setattr(bnpr, "score_budget_strategy", _forbidden)
    row = _prepared_row()
    result = _prepared_read(monkeypatch, row)
    assert result["available"] is True
    assert result["rows"][0]["medianValue"] == row["median_value"]


def test_prepared_read_legacy_row_missing_new_fields_degrades_soft(monkeypatch):
    """Requirement 7: a legacy/latest snapshot row published before this
    contract (median_value/top1_outcome_value_share/actual_committed_capital
    NULL/missing) must NOT crash and must NOT drop the row from the table —
    only these three fields degrade to unavailable/null."""
    row = _prepared_row(median_value=None, top1_outcome_value_share=None)
    del row["median_value"]
    del row["top1_outcome_value_share"]
    result = _prepared_read(monkeypatch, row)

    assert result["available"] is True
    assert len(result["rows"]) == 1
    assert result["rows"][0]["medianValue"] is None
    assert result["rows"][0]["topOneOutcomeValueShare"] is None
    # Every other pre-existing field on the row keeps working.
    assert result["rows"][0]["expectedValue"] == 30.0
    assert result["rows"][0]["overallRipScore"] == 50


# --- Best-Open Price V2 dual-field attachment (RIP + Financial axes) ----


def _best_open_read(monkeypatch, row, *, budget="full_market", method_version=None):
    monkeypatch.setattr(service, "load_latest_snapshot", lambda _client: {
        "id": "snap-1", "full_market_budget": 150.0, "published_at": "t",
        "market_date": "2026-09-01", "cohort_fingerprint": "fp-1",
    })
    monkeypatch.setattr(service, "load_full_market_ranking", lambda _client, **_kwargs: {
        "rows": [{
            "sealed_product_id": "p1", "set_id": "set-1", "product_family": "loose_booster_pack",
            "budget_rank": 1, "budget_cohort_size": 1, "quantity": 1,
            "actual_committed_capital": 10, "unused_capital": 140,
            "overall_rip_v10_score": 50, "financial_rip_v4_score": 40,
            "collector_appeal_score": 30, "product_market_price": 10,
            "expected_value": 8, "chance_to_recover_capital": .25,
        }],
        "authority": {},
    })
    monkeypatch.setattr(service, "public_budget_cohort_presentation", lambda _rows, _snapshot: {"p1": {
        "publicTier": "S", "overallRipLeaderScore": 100, "financialRipLeaderScore": 100,
        "overallRipScore": 50, "budgetRank": 1, "budgetCohortSize": 1,
    }})
    monkeypatch.setattr(service, "load_best_open_price_ranking", lambda _client, **_kwargs: {
        "available": True, "reason": None,
        "id": "snap-1", "sourceBudgetSnapshotId": "snap-1", "sourceBudgetPublishedAt": "t",
        "sourceMarketDate": "2026-09-01", "sourceCohortFingerprint": "fp-1",
        "methodVersion": method_version,
        "resolvedCount": 1, "unresolvedCount": 0,
        "rows": [row],
    })
    family_payload = {"families": {"loose_booster_pack": {"products": [{
        "sealedProductId": "p1", "productName": "Alpha Booster Box", "setName": "Alpha",
        "productFamilyLabel": "Booster Box", "productImageUrl": None,
        "setCanonicalKey": "alphaSet", "familyRank": 1, "familySize": 1,
    }]}}}
    result = service.read_public_overall_product_rankings(
        budget=budget, product_family_rankings=family_payload, client=object(),
    )
    return next(r for r in result["rows"] if r["sealedProductId"] == "p1")


def test_v2_full_market_projection_attaches_both_rip_and_financial_fields(monkeypatch):
    row = {
        "sealed_product_id": "p1", "status": "exact", "best_open_price": 145.0,
        "price_gap_dollars": 5.0, "price_gap_percent": 0.03,
        "financial_best_open_price": 150.0, "financial_status": "exact",
        "financial_price_gap_dollars": 10.0, "financial_price_gap_percent": 0.06,
    }
    projected = _best_open_read(monkeypatch, row, method_version=service.BEST_OPEN_PRICE_V2_METHOD_VERSION)
    assert projected["bestOpenPrice"] == projected["ripBestOpenPrice"] == 145.0
    assert projected["financialBestOpenPrice"] == 150.0
    assert projected["financialBestOpenPriceStatus"] == "exact"
    assert projected["financialBestOpenPriceGapDollars"] == 10.0
    assert projected["financialBestOpenPriceGapPercent"] == 0.06


def test_v1_full_market_projection_never_exposes_financial_fields(monkeypatch):
    row = {
        "sealed_product_id": "p1", "status": "exact", "best_open_price": 100.0,
        "price_gap_dollars": 1.0, "price_gap_percent": 0.01,
    }
    projected = _best_open_read(monkeypatch, row, method_version=service.BEST_OPEN_PRICE_METHOD_VERSION)
    assert projected["bestOpenPrice"] == 100.0
    assert "financialBestOpenPrice" not in projected or projected["financialBestOpenPrice"] is None
    # Finding 2: a V1 publication must not carry the new rip* aliases either
    # -- those are new response-shape additions gated to V2 exactly like the
    # financial_* fields.
    assert "ripBestOpenPrice" not in projected


def test_current_rankings_requests_v2_first(monkeypatch):
    """Finding 1 test A: the current/live-serving Product Rankings call site
    must attempt the V2 method version before ever falling back to V1."""
    monkeypatch.setattr(service, "load_latest_snapshot", lambda _client: {
        "id": "snap-1", "full_market_budget": 150.0, "published_at": "t",
        "market_date": "2026-09-01", "cohort_fingerprint": "fp-1",
    })
    monkeypatch.setattr(service, "load_full_market_ranking", lambda _client, **_kwargs: {"rows": [], "authority": {}})
    monkeypatch.setattr(service, "public_budget_cohort_presentation", lambda _rows, _snapshot: {})

    calls = []

    def fake_load(_client, *, best_open_price_method_version):
        calls.append(best_open_price_method_version)
        return {"available": False, "reason": "no_published_snapshot", "rows": []}

    monkeypatch.setattr(service, "load_best_open_price_ranking", fake_load)
    service.read_public_overall_product_rankings(
        budget="full_market", product_family_rankings={}, client=object(),
    )
    assert calls[0] == service.BEST_OPEN_PRICE_V2_METHOD_VERSION


def test_stale_v1_cannot_mask_current_v2_rankings(monkeypatch):
    """Finding 1 test E: a current V2 publication wins even though a V1
    publication also exists -- V1 must never be consulted once V2 succeeds."""
    v1_consulted = []
    v2_available = {
        "available": True, "reason": None,
        "id": "snap-1", "sourceBudgetSnapshotId": "snap-1", "sourceBudgetPublishedAt": "t",
        "sourceMarketDate": "2026-09-01", "sourceCohortFingerprint": "fp-1",
        "methodVersion": service.BEST_OPEN_PRICE_V2_METHOD_VERSION,
        "resolvedCount": 0, "unresolvedCount": 0, "rows": [],
    }

    def fake_load(_client, *, best_open_price_method_version):
        if best_open_price_method_version == service.BEST_OPEN_PRICE_V2_METHOD_VERSION:
            return dict(v2_available)
        v1_consulted.append(True)
        return {"available": False, "reason": "stale_source_publication", "rows": []}

    monkeypatch.setattr(service, "load_latest_snapshot", lambda _client: {
        "id": "snap-1", "full_market_budget": 150.0, "published_at": "t",
        "market_date": "2026-09-01", "cohort_fingerprint": "fp-1",
    })
    monkeypatch.setattr(service, "load_full_market_ranking", lambda _client, **_kwargs: {"rows": [], "authority": {}})
    monkeypatch.setattr(service, "public_budget_cohort_presentation", lambda _rows, _snapshot: {})
    monkeypatch.setattr(service, "load_best_open_price_ranking", fake_load)

    result = service.read_public_overall_product_rankings(
        budget="full_market", product_family_rankings={}, client=object(),
    )
    assert result["bestOpenPrice"]["methodVersion"] == service.BEST_OPEN_PRICE_V2_METHOD_VERSION
    assert v1_consulted == []


def test_missing_v2_falls_back_to_current_v1_rankings(monkeypatch):
    """Finding 1 test D: when no V2 publication exists, a current, complete
    V1 publication is served (it independently passes the same currentness
    rule, since the same loader/checks are reused for either method)."""
    calls = []
    v1_available = {
        "available": True, "reason": None,
        "id": "snap-1", "sourceBudgetSnapshotId": "snap-1", "sourceBudgetPublishedAt": "t",
        "sourceMarketDate": "2026-09-01", "sourceCohortFingerprint": "fp-1",
        "methodVersion": service.BEST_OPEN_PRICE_METHOD_VERSION,
        "resolvedCount": 0, "unresolvedCount": 0, "rows": [],
    }

    def fake_load(_client, *, best_open_price_method_version):
        calls.append(best_open_price_method_version)
        if best_open_price_method_version == service.BEST_OPEN_PRICE_V2_METHOD_VERSION:
            return {"available": False, "reason": "no_published_snapshot", "rows": []}
        return dict(v1_available)

    monkeypatch.setattr(service, "load_latest_snapshot", lambda _client: {
        "id": "snap-1", "full_market_budget": 150.0, "published_at": "t",
        "market_date": "2026-09-01", "cohort_fingerprint": "fp-1",
    })
    monkeypatch.setattr(service, "load_full_market_ranking", lambda _client, **_kwargs: {"rows": [], "authority": {}})
    monkeypatch.setattr(service, "public_budget_cohort_presentation", lambda _rows, _snapshot: {})
    monkeypatch.setattr(service, "load_best_open_price_ranking", fake_load)

    result = service.read_public_overall_product_rankings(
        budget="full_market", product_family_rankings={}, client=object(),
    )
    assert calls == [service.BEST_OPEN_PRICE_V2_METHOD_VERSION, service.BEST_OPEN_PRICE_METHOD_VERSION]
    assert result["bestOpenPrice"]["methodVersion"] == service.BEST_OPEN_PRICE_METHOD_VERSION


def test_rankings_stay_available_when_best_open_is_unavailable(monkeypatch):
    """Rankings must never depend on Best-Open success."""
    monkeypatch.setattr(service, "load_latest_snapshot", lambda _client: {
        "id": "snap-1", "full_market_budget": 150.0, "published_at": "t",
        "market_date": "2026-09-01", "cohort_fingerprint": "fp-1",
    })
    monkeypatch.setattr(service, "load_full_market_ranking", lambda _client, **_kwargs: {
        "rows": [{
            "sealed_product_id": "p1", "set_id": "set-1", "product_family": "loose_booster_pack",
            "budget_rank": 1, "budget_cohort_size": 1, "quantity": 1,
            "actual_committed_capital": 10, "unused_capital": 140,
            "overall_rip_v10_score": 50, "financial_rip_v4_score": 40,
            "collector_appeal_score": 30, "product_market_price": 10,
            "expected_value": 8, "chance_to_recover_capital": .25,
        }],
        "authority": {},
    })
    monkeypatch.setattr(service, "public_budget_cohort_presentation", lambda _rows, _snapshot: {"p1": {
        "publicTier": "S", "overallRipLeaderScore": 100, "financialRipLeaderScore": 100,
        "overallRipScore": 50, "budgetRank": 1, "budgetCohortSize": 1,
    }})

    def _boom(_client, **_kwargs):
        raise RuntimeError("prepared store unreachable")

    monkeypatch.setattr(service, "load_best_open_price_ranking", _boom)
    family_payload = {"families": {"loose_booster_pack": {"products": [{
        "sealedProductId": "p1", "productName": "Alpha Booster Box", "setName": "Alpha",
        "productFamilyLabel": "Booster Box", "productImageUrl": None,
        "setCanonicalKey": "alphaSet", "familyRank": 1, "familySize": 1,
    }]}}}
    result = service.read_public_overall_product_rankings(
        product_family_rankings=family_payload, client=object(),
    )
    assert result["available"] is True
    assert len(result["rows"]) == 1
    assert result["bestOpenPrice"]["available"] is False
    row = result["rows"][0]
    assert "bestOpenPrice" not in row or row.get("bestOpenPrice") is None


def test_prepared_read_legacy_row_missing_committed_capital_makes_average_return_unavailable(monkeypatch):
    """Transitional safety: a legacy row missing actual_committed_capital must
    not throw and must not silently report a computed-looking zero — Average
    Return degrades to unavailable (None), the rest of the row still works."""
    row = _prepared_row()
    del row["actual_committed_capital"]
    result = _prepared_read(monkeypatch, row)

    assert result["available"] is True
    assert result["rows"][0]["averageReturn"] is None
    assert result["rows"][0]["medianValue"] == row["median_value"]
