"""FMA-0: executable rules for Explorer Focused Market Activity V1.

Every group below maps to an acceptance bullet in
docs/research/market_activity_v1/CONTRACT.md. Negative cases matter most: each
asserts that missing proof yields an explicit state instead of a number.
"""
from __future__ import annotations

import ast
import socket
import subprocess
import sys
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from backend.domain.pokemon import market_activity as ma

ROOT = Path(__file__).resolve().parents[5]
MODULES = [ROOT / "backend/domain/pokemon/market_activity.py",
           ROOT / "backend/domain/pokemon/market_activity_contract.py"]
V1 = "00000000-0000-4000-8000-0000000000a1"
V2 = "00000000-0000-4000-8000-0000000000a2"
V3 = "00000000-0000-4000-8000-0000000000a3"
NOW = datetime(2026, 9, 30, 12, 0, tzinfo=timezone.utc)
RAW = ma.classify_grading(None, None, None)
PSA10 = ma.classify_grading("PSA", "10")


# ---------------------------------------------------------------------------
# Provider-egress tripwire
# ---------------------------------------------------------------------------
class EgressAttempt(AssertionError):
    pass


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    def refuse(*_args, **_kwargs):
        raise EgressAttempt("market_activity attempted network/DB egress")
    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket.socket, "connect_ex", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)
    yield


def test_egress_tripwire_is_armed():
    with pytest.raises(EgressAttempt):
        socket.create_connection(("api.pkmnprices.com", 443))


def test_fresh_import_opens_no_connection_and_loads_no_client_modules():
    probe = (
        "import socket, sys\n"
        "def refuse(*a, **k): raise SystemExit('EGRESS')\n"
        "socket.socket.connect = refuse; socket.create_connection = refuse; socket.getaddrinfo = refuse\n"
        "import backend.domain.pokemon.market_activity as ma\n"
        "import backend.domain.pokemon.market_activity_contract as mc\n"
        "import backend.scripts.build_market_activity_v1_contract_artifacts as gen\n"
        "gen.render()\n"
        "bad = sorted(m for m in sys.modules if m.split('.')[0] in {'requests','psycopg2','psycopg','supabase',"
        "'postgrest','httpx','urllib3','aiohttp'} or m in {'urllib.request','http.client'} "
        "or m.startswith('backend.db') or m.startswith('backend.pricing_pipeline'))\n"
        "print('LOADED', bad)\n"
        "raise SystemExit(1 if bad else 0)\n"
    )
    result = subprocess.run([sys.executable, "-c", probe], cwd=str(ROOT), capture_output=True, text=True,
                            timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "LOADED []" in result.stdout


@pytest.mark.parametrize("path", MODULES, ids=lambda p: p.name)
def test_domain_modules_import_only_the_standard_library(path):
    allowed = {"__future__", "hashlib", "json", "re", "dataclasses", "datetime", "decimal", "typing",
               "pathlib", "backend.domain.pokemon.market_activity"}
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module)
    assert imported <= allowed, imported - allowed


# ---------------------------------------------------------------------------
# Reason codes, versions, policy
# ---------------------------------------------------------------------------
def test_reason_lists_are_deterministic_and_registered():
    assert ma.reasons("ASKS_STALE", ["NOT_COLLECTED", "ASKS_STALE"]) == ["NOT_COLLECTED", "ASKS_STALE"]
    with pytest.raises(ValueError):
        ma.reasons("SOMETHING_NEW")
    assert len(set(ma.REASON_CODES)) == len(ma.REASON_CODES)


def test_policy_defaults_are_named_operations_policy():
    policy = ma.DEFAULT_POLICY.as_contract()
    assert policy == {"version": "fma_display_policy_v1", "askConfirmationMaxAgeHours": 24,
                      "soldHeadReceiptMaxAgeHours": 36, "priceSummaryMinRecords": 5,
                      "percentileMinOtherPeers": 30, "futureTimestampSkewSeconds": 300,
                      "tiePolicy": "midrank_v1"}


def test_timestamps_parse_postgres_short_offsets_and_reject_naive():
    assert ma.parse_timestamp("2026-09-29 06:03:34.402935+00") == datetime(2026, 9, 29, 6, 3, 34, 402935,
                                                                          tzinfo=timezone.utc)
    assert ma.parse_timestamp("2026-09-29T06:03:34Z").tzinfo is not None
    assert ma.parse_timestamp(None) is None and ma.parse_timestamp("") is None
    with pytest.raises(ValueError):
        ma.parse_timestamp("2026-09-29T06:03:34")


def test_money_is_exact_cents_and_never_float():
    assert str(ma.money("9.5")) == "9.50"
    with pytest.raises(ValueError):
        ma.money(9.5)
    with pytest.raises(ValueError):
        ma.money("1.005")
    assert ma.money_json(Decimal("3")) == {"amount": "3.00", "currency": "USD"}


# ---------------------------------------------------------------------------
# Exact instrument keys and grading safeguards
# ---------------------------------------------------------------------------
def test_instrument_keys_round_trip_and_preserve_string_grades():
    assert ma.instrument_key(V1, RAW) == f"card:{V1}:raw"
    bgs = ma.classify_grading("bgs", "9.5", "black label")
    key = ma.instrument_key(V1, bgs)
    assert key == f"card:{V1}:graded:BGS:9.5:Black%20Label"
    parsed = ma.parse_instrument_key(key)
    assert parsed["grading"].grade == "9.5" and parsed["grading"].qualifier == "Black Label"
    assert ma.parse_instrument_key(f"card:{V1}:raw")["stream"] == "RAW"
    for bad in ("card:not-a-uuid:raw", f"card:{V1}:graded:PSA:10.0:-", f"sealed:{V1}:raw",
                f"card:{V1}:graded:XYZ:10:-"):
        with pytest.raises(ValueError):
            ma.parse_instrument_key(bad)


def test_grades_are_opaque_strings():
    assert ma.classify_grading("CGC", "9.5").grade == "9.5"
    assert ma.classify_grading("PSA", "10.0").state == "UNRECOGNIZED"   # "10.0" is not "10"
    assert ma.classify_grading("PSA", "Authentic").state == "UNRECOGNIZED"


@pytest.mark.parametrize("grader,grade,qualifier,flag", [
    ("PSA", None, None, True),       # missing grade
    (None, "10", None, True),        # missing grader
    (None, None, "Pristine", True),  # qualifier only
    (None, None, None, True),        # provider says graded, no slab fields
])
def test_incomplete_grading_never_falls_back_to_raw(grader, grade, qualifier, flag):
    grading = ma.classify_grading(grader, grade, qualifier, provider_graded_flag=flag)
    assert grading.state == "INCOMPLETE" and not grading.certified_tier
    assert grading.reasons == ("GRADING_INCOMPLETE",)
    with pytest.raises(ValueError):
        ma.instrument_key(V1, grading)


def test_unknown_qualifier_never_becomes_a_certified_ordinary_tier():
    unknown = ma.classify_grading("PSA", "10", "Gem+")
    assert unknown.state == "UNRECOGNIZED" and "QUALIFIER_UNRECOGNIZED" in unknown.reasons
    known = ma.classify_grading("CGC", "10", "pristine")
    assert known.state == "GRADED_QUALIFIED" and known.qualifier == "Pristine"
    assert ma.tier_key(known) != ma.tier_key(ma.classify_grading("CGC", "10"))


# ---------------------------------------------------------------------------
# Exact identity: attribution + internal variant proof
# ---------------------------------------------------------------------------
VINTAGE = [{"id": V1, "edition": "1st-edition", "printingType": "holo"},
           {"id": V2, "edition": "unlimited", "printingType": "holo"},
           {"id": V3, "edition": "shadowless", "printingType": "holo"}]
MODERN = [{"id": V1, "edition": None, "printingType": "holo"},
          {"id": V2, "edition": None, "printingType": "reverse-holo"},
          {"id": V3, "edition": None, "printingType": "non-holo"}]


def _resolve(variant, candidates, attribution="exact", scope="FULL_CARD_VARIANT_SET", currency="USD"):
    return ma.resolve_exact_identity(attribution=attribution, provider_variant=variant, candidates=candidates,
                                     candidate_scope=scope, currency=currency)


@pytest.mark.parametrize("variant,expected", [
    ("1st Edition Holofoil", V1), ("First Edition Holo", V1), ("Unlimited Holofoil", V2),
    ("Shadowless Holofoil", V3),
])
def test_vintage_editions_resolve_only_when_stated(variant, expected):
    decision = _resolve(variant, VINTAGE)
    assert decision.state == "EXACT" and decision.publishable and decision.card_variant_id == expected


def test_unstated_edition_is_not_proof_by_elimination():
    decision = _resolve("Holofoil", VINTAGE)
    assert decision.state == "AMBIGUOUS" and "IDENTITY_EDITION_UNPROVEN" in decision.reasons
    # The audited production pattern: one edition-bearing candidate and an
    # edition-less provider label. Unique, but still not proven.
    lone = _resolve("Holofoil", [VINTAGE[1]])
    assert lone.state == "UNPROVEN" and lone.reasons == ("IDENTITY_EDITION_UNPROVEN",)
    assert not lone.publishable


@pytest.mark.parametrize("variant,expected", [
    ("Holofoil", V1), ("Reverse Holofoil", V2), ("Reverse Holo", V2), ("Non-Holo", V3),
    ("Non Holo", V3), ("Normal", V3),
])
def test_printings_including_non_holo_resolve_exactly(variant, expected):
    decision = _resolve(variant, MODERN)
    assert decision.publishable and decision.card_variant_id == expected


def test_audit_legacy_parser_reads_non_holo_as_holo():
    """Audit evidence (not a fix): the legacy regex order matches Holo inside Non-Holo."""
    from backend.pricing_pipeline.pkmnprices_sold import parse_provider_variant
    assert parse_provider_variant("Non-Holo")["printing_type"] == "holo"
    assert parse_provider_variant("Non Holo")["printing_type"] == "holo"
    assert ma.parse_provider_variant_strict("Non-Holo")["printingType"] == "non-holo"


def test_audit_legacy_one_candidate_shortcut_resolves_without_proof():
    """Audit evidence: the legacy resolver returns EXACT for a lone target candidate."""
    from backend.pricing_pipeline.pkmnprices_sold import resolve_internal_variant
    lone = [{"id": V2, "edition": "unlimited", "printing_type": "holo"}]
    assert resolve_internal_variant("Holofoil", lone)["state"] == "EXACT"
    assert resolve_internal_variant(None, lone)["state"] == "EXACT"
    assert _resolve("Holofoil", lone, scope="TARGET_ONLY").reasons == (
        "CANDIDATE_SET_INCOMPLETE", "IDENTITY_EDITION_UNPROVEN")
    assert _resolve(None, [MODERN[0]]).reasons == ("PROVIDER_VARIANT_MISSING",)


@pytest.mark.parametrize("attribution,code", [
    ("shared", "ATTRIBUTION_SHARED"), ("unknown", "ATTRIBUTION_UNKNOWN"), (None, "ATTRIBUTION_MISSING"),
    ("", "ATTRIBUTION_MISSING"), ("weird", "ATTRIBUTION_UNKNOWN"),
])
def test_attribution_other_than_exact_is_never_publishable(attribution, code):
    decision = _resolve("Holofoil", [MODERN[0]], attribution=attribution)
    assert not decision.publishable and code in decision.reasons


def test_internal_ambiguity_no_match_and_unparsed_tokens():
    twins = [{"id": V1, "edition": None, "printingType": "holo"}, {"id": V2, "edition": None, "printingType": "holo"}]
    assert _resolve("Holofoil", twins).state == "AMBIGUOUS"
    assert _resolve("Reverse Holofoil", [MODERN[0]]).state == "NO_MATCH"
    stamped = _resolve("Holofoil Staff Stamp", [MODERN[0]])
    assert "PROVIDER_VARIANT_UNPARSED_TOKENS" in stamped.reasons and not stamped.publishable
    special = _resolve("Holofoil", [{"id": V1, "edition": None, "printingType": "holo", "specialType": "stamped"}])
    assert "IDENTITY_SPECIAL_TYPE_UNSUPPORTED" in special.reasons
    assert "CURRENCY_UNSUPPORTED" in _resolve("Holofoil", [MODERN[0]], currency="EUR").reasons


def test_legacy_rows_are_evaluated_never_rewritten():
    stored = {"identity_state": "EXACT", "attribution": "exact", "currency": "USD",
              "provider_variant": "Holofoil", "card_variant_id": V2}
    before = dict(stored)
    siblings = [{"id": V1, "edition": "1st-edition", "printingType": "holo"},
                {"id": V2, "edition": "unlimited", "printingType": "holo"}]
    result = ma.evaluate_legacy_sold_row(stored, candidates=siblings, candidate_scope="FULL_CARD_VARIANT_SET")
    assert result["legacyExactUsd"] is True and result["fmaPublishable"] is False
    assert result["agrees"] is False and result["rewritten"] is False
    assert stored == before
    ok = ma.evaluate_legacy_sold_row({**stored, "card_variant_id": V1, "provider_variant": "Holofoil"},
                                     candidates=[MODERN[0]], candidate_scope="FULL_CARD_VARIANT_SET")
    assert ok["agrees"] is True and ok["fmaPublishable"] is True


# ---------------------------------------------------------------------------
# Duplicate and conflicting evidence
# ---------------------------------------------------------------------------
def _sold(listing, price="10.00", sold="2026-09-20", collected="2026-09-30T00:00:00Z", **extra):
    return {"source": ma.SOLD_SOURCE, "providerCardId": "1", "listingId": str(listing), "price": price,
            "currency": "USD", "soldAt": sold, "collectedAt": collected, **extra}


def test_duplicates_keep_first_seen_and_conflicts_exclude_every_copy():
    rows = [_sold(1, collected="2026-09-30T02:00:00Z", title="later"),
            _sold(1, collected="2026-09-30T01:00:00Z", title="first"),
            _sold(2, price="10.00"), _sold(2, price="11.00"),
            _sold(3), _sold(3, sold="2026-09-21")]
    kept, excluded = ma.dedupe_sold_records(rows)
    assert [r["listingId"] for r in kept] == ["1"] and kept[0]["title"] == "first"
    assert excluded == {"EVIDENCE_DUPLICATE": 1, "EVIDENCE_CONFLICT": 4}


# ---------------------------------------------------------------------------
# Window readiness
# ---------------------------------------------------------------------------
def _page(i, hi, lo, rows=20, more=True, fp="f1"):
    return {"pageIndex": i, "inputCursorHash": None if i == 0 else f"c{i - 1}",
            "outputCursorHash": f"c{i}" if more else None, "hasMore": more, "maxSoldAt": hi,
            "minSoldAt": lo, "rowCount": rows, "filterFingerprint": fp}


def _walk(pages, stream="COMBINED", reconciled="2026-09-30T06:00:00Z", **extra):
    walk = {"stream": stream, "combinedSemanticsVerified": True, "sort": "date_desc", "startedFromHead": True,
            "filterFingerprint": "f1", "pages": pages,
            "rightEdge": {"completed": reconciled is not None, "reconciledThrough": reconciled}}
    walk.update(extra)
    return walk


def _eval(walk, days=30, grading=RAW, ingested=(), now=NOW):
    start, end = ma.closed_window("2026-09-29", days)
    return ma.evaluate_walk_for_window(walk, window_start=start, window_end=end, grading=grading,
                                       evaluated_at=now, window_ingested_ats=list(ingested))


def test_closed_windows_have_explicit_inclusive_dates():
    assert ma.closed_window("2026-09-29", 7) == (date(2026, 9, 23), date(2026, 9, 29))
    assert ma.closed_window("2026-09-29", 180) == (date(2026, 4, 3), date(2026, 9, 29))
    with pytest.raises(ValueError):
        ma.closed_window("2026-09-29", 14)


def test_recent_window_proven_without_lifetime_exhaustion():
    result = _eval(_walk([_page(0, "2026-09-29", "2026-09-05"), _page(1, "2026-09-05", "2026-08-20")]))
    assert result.state == "PROVEN" and not result.exhausted
    assert result.proven_lower_bound_date == "2026-08-21"


def test_partially_fetched_boundary_date_is_partial_not_proven():
    walk = _walk([_page(0, "2026-09-29", "2026-08-31")])  # 30d window starts 2026-08-31
    result = _eval(walk)
    assert result.state == "PARTIAL" and result.reasons == ("BOUNDARY_DATE_PARTIALLY_FETCHED",)
    assert _eval(_walk([_page(0, "2026-09-29", "2026-09-15")])).reasons == ("LOWER_BOUNDARY_NOT_REACHED",)


def test_exhausted_stream_proves_older_windows():
    result = _eval(_walk([_page(0, "2026-09-29", "2026-09-20", rows=4, more=False)]), days=180)
    assert result.state == "PROVEN" and result.exhausted


def test_raw_only_stream_cannot_prove_graded_windows():
    raw_walk = _walk([_page(0, "2026-09-29", "2026-08-01")], stream="RAW_ONLY")
    assert _eval(raw_walk).state == "PROVEN"
    graded = _eval(raw_walk, grading=PSA10)
    assert graded.state == "UNPROVEN" and graded.reasons == ("STREAM_DOES_NOT_COVER_TIER",)


def test_combined_stream_requires_verified_semantics_and_grade_filter_must_match():
    combined = _walk([_page(0, "2026-09-29", "2026-08-01")], combinedSemanticsVerified=False)
    assert _eval(combined).reasons == ("COMBINED_STREAM_SEMANTICS_UNPROVEN",)
    psa10 = _walk([_page(0, "2026-09-29", "2026-08-01")], stream="GRADE_FILTERED", graderFilter="PSA",
                  gradeFilter="10")
    assert _eval(psa10, grading=PSA10).state == "PROVEN"
    assert _eval(psa10, grading=ma.classify_grading("PSA", "9")).reasons == ("STREAM_DOES_NOT_COVER_TIER",)
    assert _eval(psa10, grading=RAW).reasons == ("STREAM_DOES_NOT_COVER_TIER",)


@pytest.mark.parametrize("mutate,code", [
    (lambda w: w.update(sort="date_asc"), "WALK_SORT_NOT_DATE_DESC"),
    (lambda w: w.update(startedFromHead=False), "WALK_HEAD_UNKNOWN"),
    (lambda w: w["pages"][1].update(inputCursorHash="zzz"), "WALK_CURSOR_CHAIN_BROKEN"),
    (lambda w: w["pages"][1].update(filterFingerprint="f2"), "WALK_FILTER_UNSTABLE"),
    (lambda w: w["pages"][1].update(maxSoldAt="2026-09-29"), "WALK_NOT_DATE_DESCENDING"),
])
def test_walk_must_be_auditable(mutate, code):
    walk = _walk([_page(0, "2026-09-29", "2026-09-10"), _page(1, "2026-09-10", "2026-08-01")])
    mutate(walk)
    result = _eval(walk)
    assert result.state == "UNPROVEN" and code in result.reasons


def test_right_edge_must_be_reconciled_after_the_window_closed_and_fresh():
    pages = [_page(0, "2026-09-29", "2026-08-01")]
    assert _eval(_walk(pages, reconciled=None)).reasons == ("RIGHT_EDGE_UNRECONCILED",)
    assert _eval(_walk(pages, reconciled="2026-09-29T23:00:00Z")).reasons == ("RIGHT_EDGE_DAY_OPEN",)
    stale = _eval(_walk(pages), now=datetime(2026, 10, 2, 0, 0, tzinfo=timezone.utc))
    assert stale.state == "PARTIAL" and stale.reasons == ("RIGHT_EDGE_STALE",)


def test_late_ingestion_after_reconciliation_is_partial():
    late = [datetime(2026, 9, 30, 9, 0, tzinfo=timezone.utc)]
    result = _eval(_walk([_page(0, "2026-09-29", "2026-08-01")]), ingested=late)
    assert result.state == "PARTIAL" and result.reasons == ("LATE_INGESTION_AFTER_RECONCILIATION",)


def test_completeness_is_never_inferred_from_sync_state_counts_or_oldest_date():
    for status in ("CURRENT", "PARTIAL", "NEVER"):
        state = ma.readiness_from_sync_state({"status": status, "rows_seen": 320,
                                              "metadata": {"core_panel_backfill_complete": True}})
        assert state.state == "UNPROVEN" and state.reasons == ("SYNC_STATUS_NOT_PROOF",)
    assert ma.readiness_from_sync_state(None).state == "NOT_COLLECTED"
    import inspect
    params = set(inspect.signature(ma.evaluate_walk_for_window).parameters)
    assert not params & {"oldest_stored_date", "stored_count", "sync_status"}


def test_best_readiness_prefers_proof_deterministically():
    good = _walk([_page(0, "2026-09-29", "2026-08-01")])
    bad = _walk([_page(0, "2026-09-29", "2026-09-20")])
    start, end = ma.closed_window("2026-09-29", 30)
    best = ma.best_window_readiness([bad, good], window_start=start, window_end=end, grading=RAW, evaluated_at=NOW)
    assert best.state == "PROVEN"
    assert ma.best_window_readiness([], window_start=start, window_end=end, grading=RAW,
                                    evaluated_at=NOW).state == "NOT_COLLECTED"


def test_checkpoint_rules_never_skip_pending_or_same_timestamp_pages():
    sold_desc = {"order": "sold_desc", "sort": "date_desc", "startedFromHead": True, "filterFingerprint": "f1",
                 "pages": [dict(_page(0, "2026-09-29", "2026-09-01"),
                                ingestedAts=["2026-09-29T01:00:00Z", "2026-09-28T01:00:00Z"])]}
    assert ma.checkpoint_advance_decision(sold_desc)["reasons"] == ["CHECKPOINT_PAGES_PENDING"]
    drained = {**sold_desc, "pages": [dict(sold_desc["pages"][0], hasMore=False, outputCursorHash=None)]}
    assert ma.checkpoint_advance_decision(drained) == {"allowed": True, "watermark": "2026-09-29T01:00:00Z",
                                                       "reasons": []}
    same = {**sold_desc, "order": "ingested_asc",
            "pages": [dict(_page(0, "2026-09-29", "2026-09-01"),
                           ingestedAts=["2026-09-29T01:00:00Z", "2026-09-29T01:00:00Z"])]}
    assert ma.checkpoint_advance_decision(same) == {"allowed": False, "watermark": None,
                                                    "reasons": ["SAME_INGESTION_TIMESTAMP_UNDRAINED"]}
    mixed = {**same, "pages": [dict(same["pages"][0],
                                    ingestedAts=["2026-09-28T01:00:00Z", "2026-09-29T01:00:00Z"])]}
    assert ma.checkpoint_advance_decision(mixed)["watermark"] == "2026-09-28T01:00:00Z"


# ---------------------------------------------------------------------------
# Supply provenance and source freshness
# ---------------------------------------------------------------------------
def _offer(price="10.00", ship="0.00", ship_prov="EXPLICIT", qty=1, qty_prov="EXPLICIT",
           confirmed="2026-09-30T08:00:00Z", updated=None):
    return {"itemPrice": price, "shippingPrice": ship, "shippingProvenance": ship_prov, "quantity": qty,
            "quantityProvenance": qty_prov, "providerSnapshotAt": confirmed, "listingUpdatedAt": updated}


def _snap(offers, **extra):
    snap = {"observationState": "OBSERVED", "observedAt": "2026-09-30T11:59:00Z", "hasMore": False,
            "offers": offers}
    snap.update(extra)
    return snap


def test_ask_freshness_uses_provider_confirmation_not_collection_or_updated_at():
    stale = ma.evaluate_supply_snapshot(
        _snap([_offer(confirmed="2026-09-24T02:06:10Z", updated="2026-09-30T11:00:00Z")]), evaluated_at=NOW)
    assert stale["state"] == "STALE" and "ASKS_STALE" in stale["reasons"]
    assert stale["collectedAt"] == "2026-09-30T11:59:00Z"   # labelled fact, not freshness
    fresh = ma.evaluate_supply_snapshot(_snap([_offer()]), evaluated_at=NOW)
    assert fresh["state"] == "FRESH" and fresh["providerConfirmedAt"] == "2026-09-30T08:00:00Z"
    assert fresh["confirmationAgeHours"] == "4.0"


def test_null_future_mixed_and_repeated_confirmations():
    null = ma.evaluate_supply_snapshot(_snap([_offer(confirmed=None)]), evaluated_at=NOW)
    assert null["state"] == "CONFIRMATION_MISSING"
    future = ma.evaluate_supply_snapshot(_snap([_offer(confirmed="2026-10-05T00:00:00Z")]), evaluated_at=NOW)
    assert future["state"] == "CONFIRMATION_INVALID" and "SOURCE_CONFIRMATION_IN_FUTURE" in future["reasons"]
    mixed = ma.evaluate_supply_snapshot(
        _snap([_offer(confirmed="2026-09-30T08:00:00Z"), _offer(confirmed="2026-09-29T08:00:00Z"),
               _offer(confirmed=None), _offer(confirmed="2026-10-05T00:00:00Z")]), evaluated_at=NOW)
    assert mixed["providerConfirmedAt"] == "2026-09-29T08:00:00Z"   # oldest valid wins
    assert {"SOURCE_CONFIRMATION_MIXED", "SOURCE_CONFIRMATION_MISSING",
            "SOURCE_CONFIRMATION_IN_FUTURE"} <= set(mixed["reasons"])
    assert mixed["capturedListingCount"] == 3                      # future offer excluded
    repeated = ma.evaluate_supply_snapshot(_snap([_offer()]), evaluated_at=NOW,
                                           previous_confirmation="2026-09-30T08:00:00Z")
    assert "SOURCE_CONFIRMATION_REPEATED" in repeated["reasons"]


def test_empty_response_needs_source_freshness_to_prove_zero():
    unproven = ma.evaluate_supply_snapshot(_snap([]), evaluated_at=NOW)
    assert unproven["state"] == "ZERO_UNPROVEN" and unproven["capturedListingCount"] is None
    proven = ma.evaluate_supply_snapshot(_snap([], sourceConfirmedAt="2026-09-30T07:00:00Z"), evaluated_at=NOW)
    assert proven["state"] == "ZERO_PROVEN" and proven["capturedListingCount"] == 0
    assert ma.evaluate_supply_snapshot(None, evaluated_at=NOW)["state"] == "NOT_COLLECTED"
    failed = ma.evaluate_supply_snapshot({"observationState": "TARGET_FAILED"}, evaluated_at=NOW)
    assert failed["state"] == "COLLECTION_FAILED"


def test_unknown_shipping_is_not_free_shipping():
    free = ma.classify_offer_provenance({"price": "10.00", "shipping_price": "0", "quantity": 2})
    unknown = ma.classify_offer_provenance({"price": "10.00", "quantity": 2})
    assert free["shippingProvenance"] == "EXPLICIT" and free["shippingPrice"] == Decimal("0.00")
    assert unknown["shippingProvenance"] == "UNKNOWN" and unknown["shippingPrice"] is None
    snap = ma.evaluate_supply_snapshot(_snap([_offer(ship=None, ship_prov="UNKNOWN")]), evaluated_at=NOW)
    assert snap["lowestAsk"]["basis"] == "ITEM_ONLY" and "SHIPPING_UNKNOWN" in snap["reasons"]
    landed = ma.evaluate_supply_snapshot(_snap([_offer(price="10.00", ship="2.50")]), evaluated_at=NOW)
    assert landed["lowestAsk"] == {"basis": "LANDED_PROVEN", "price": {"amount": "12.50", "currency": "USD"}}


def test_quantity_defaults_are_not_proven_quantity():
    defaulted = ma.classify_offer_provenance({"price": "10.00", "shipping_price": "1.00"})
    assert defaulted["quantity"] == 1 and defaulted["quantityProvenance"] == "DEFAULTED"
    with pytest.raises(ValueError):
        ma.classify_offer_provenance({"price": "10.00", "quantity": 0})
    snap = ma.evaluate_supply_snapshot(_snap([_offer(qty_prov="DEFAULTED"), _offer(qty=3)]), evaluated_at=NOW)
    assert snap["capturedQuantity"] == {"value": 4, "provenance": "DEFAULTED_LOWER_BOUND"}


def test_legacy_offer_rows_stay_unverified_and_audit_existing_normalizer_defaults():
    from backend.pricing_pipeline.active_supply import normalize_listing
    key = "k" * 32
    missing = normalize_listing({"id": 1, "price": "5.00", "seller": {"id": "s"}}, rank=1, seller_hash_key=key)
    explicit_zero = normalize_listing({"id": 2, "price": "5.00", "shipping_price": "0.00", "quantity": 0,
                                       "seller": {"id": "s"}}, rank=2, seller_hash_key=key)
    # Audit evidence (no fix here): unknown shipping and explicit free shipping
    # are stored identically; quantity 0 and missing quantity both become 1.
    assert missing["shipping_price"] == explicit_zero["shipping_price"] == "0.00"
    assert missing["quantity"] == explicit_zero["quantity"] == 1
    legacy = ma.legacy_offer_provenance({"item_price": "5.00", "shipping_price": "0.00", "quantity": 1,
                                         "source_payload": {}})
    assert legacy["shippingProvenance"] == "LEGACY_UNVERIFIED" and legacy["shippingPrice"] is None
    assert legacy["quantityProvenance"] == "LEGACY_UNVERIFIED"
    stamped = ma.legacy_offer_provenance({"item_price": "5.00", "shipping_price": "0.00", "quantity": 1,
                                          "source_payload": {"shipping_provenance": "EXPLICIT",
                                                             "quantity_provenance": "EXPLICIT"}})
    assert stamped["shippingPrice"] == Decimal("0.00") and stamped["quantityProvenance"] == "EXPLICIT"


def test_truncated_depth_is_a_lower_bound():
    snap = ma.evaluate_supply_snapshot(_snap([_offer()], hasMore=True), evaluated_at=NOW)
    assert snap["depth"] == "LOWER_BOUND" and "DEPTH_TRUNCATED" in snap["reasons"]
    assert snap["state"] == "FRESH"


# ---------------------------------------------------------------------------
# Membership and revisions
# ---------------------------------------------------------------------------
def test_query_fingerprint_is_a_specification_not_a_revision():
    fp = "a" * 64
    assert ma.validate_roster_revision({"kind": "QUERY_CACHE_FINGERPRINT", "queryFingerprint": fp}) == [
        "ROSTER_REVISION_UNSTABLE", "QUERY_FINGERPRINT_IS_NOT_A_REVISION"]
    assert ma.validate_roster_revision({"kind": "QUERY_CACHE_PUBLISHED_REVISION", "queryFingerprint": fp,
                                        "revisionId": V1, "computedThrough": "2026-09-29"}) == []
    assert ma.validate_roster_revision({"kind": "SURFACE_V2_GENERATION", "generationId": V1,
                                        "marketKey": "set:x"}) == []
    assert ma.validate_roster_revision(None) == ["ROSTER_REVISION_UNSTABLE"]


def test_roster_contract_is_labelled_current_roster_retrospective():
    roster = ma.roster_contract(revision={"kind": "SURFACE_V2_GENERATION", "generationId": V1, "marketKey": "m"},
                                roster_as_of="2026-09-29", roster_denominator=207)
    assert roster["membershipMode"] == "CURRENT_ROSTER_RETROSPECTIVE"
    assert roster["label"] == "Activity for current constituents"
    assert roster["rosterDenominator"] == 207 and roster["rosterAsOf"] == "2026-09-29"


def test_unsupported_sealed_and_generation_mismatch():
    assert ma.check_asset("sealed") == ["UNSUPPORTED_ASSET"]
    assert ma.check_asset("graded") == ["UNSUPPORTED_ASSET"]
    assert ma.check_asset("cards") == []
    assert ma.check_generation(V1, V2) == ["GENERATION_MISMATCH"]
    assert ma.check_generation(V1, None) == ["GENERATION_MISMATCH"]
    assert ma.check_generation(V1, V1.upper()) == []


# ---------------------------------------------------------------------------
# Metrics and peers
# ---------------------------------------------------------------------------
def test_price_summary_thresholds_and_even_median():
    assert ma.price_summary([])["state"] == "NO_RECORDS"
    thin = ma.price_summary(["1.00"] * 4)
    assert thin["state"] == "THIN" and thin["median"] is None and thin["recordCount"] == 4
    even = ma.price_summary(["1.00", "2.00", "3.00", "4.00", "5.00", "6.01"])
    assert even["median"] == {"amount": "3.50", "currency": "USD"}
    assert even["low"]["amount"] == "1.00" and even["high"]["amount"] == "6.01"


KEY = ma.peer_population_key(window_days=30, source=ma.SOLD_SOURCE, currency="USD", tier="RAW", coverage="PROVEN")


def _peer_rows(values, key=KEY):
    return [{"instrumentKey": f"p{i}", "populationKey": key, "value": v} for i, v in enumerate(values)]


def test_percentile_midrank_strict_below_and_target_exclusion():
    peers = _peer_rows([1] * 10 + [5] * 10 + [9] * 10) + [{"instrumentKey": "t", "populationKey": KEY, "value": 5}]
    result = ma.activity_percentile("t", 5, peers, population_key=KEY)
    assert result["eligibleOtherPeerCount"] == 30 and result["tieCount"] == 10
    assert result["activityPercentile"] == "50.0"      # (10 + 0.5*10) / 30
    assert result["strictBelowPct"] == "33.3"          # strictly below only
    assert result["label"] == "Activity percentile" and result["claimsAllPokemon"] is False


def test_peers_must_share_the_exact_population_key():
    other = KEY.replace("|RAW|", "|GRADED:PSA:10:-|")
    peers = _peer_rows([1] * 29) + _peer_rows([1] * 10, key=other)
    result = ma.activity_percentile("t", 3, peers, population_key=KEY)
    assert result["state"] == "INSUFFICIENT_PEERS" and result["eligibleOtherPeerCount"] == 29


def test_thin_all_zero_tied_and_empty_peer_groups():
    assert ma.activity_percentile("t", 3, [], population_key=KEY)["state"] == "NO_PEERS"
    assert ma.activity_percentile("t", 0, _peer_rows([0] * 40), population_key=KEY)["state"] == "ALL_ZERO"
    tied = ma.activity_percentile("t", 4, _peer_rows([4] * 40), population_key=KEY)
    assert tied["state"] == "ALL_TIED" and tied["activityPercentile"] is None
    unproven = ma.activity_percentile("t", None, _peer_rows([4] * 40), population_key=KEY)
    assert unproven["state"] == "UNAVAILABLE" and unproven["reasons"] == ["WINDOW_NOT_PROVEN"]
    # Zero target against non-zero peers is a real, reportable position.
    low = ma.activity_percentile("t", 0, _peer_rows([0] * 10 + [2] * 30), population_key=KEY)
    assert low["state"] == "AVAILABLE" and low["activityPercentile"] == "12.5" and low["strictBelowPct"] == "0.0"


def test_zero_versus_missing_and_zero_baseline():
    assert ma.window_change(None, 3)["state"] == "UNAVAILABLE"
    assert ma.window_change(3, None)["reasons"] == ["BASELINE_MISSING"]
    assert ma.window_change(0, 0)["state"] == "NO_ACTIVITY"
    assert ma.window_change(4, 0) == {"state": "ZERO_BASELINE", "changePct": None, "reasons": ["ZERO_BASELINE"]}
    assert ma.window_change(3, 4)["changePct"] == "-25.0"


def test_no_all_pokemon_claim_for_the_research_panel():
    assert ma.population_scope(ma.RESEARCH_PANEL_ID)["claimsAllPokemon"] is False
    with pytest.raises(ValueError):
        ma.population_scope("all_pokemon")


def test_disabled_features_are_explicit():
    caps = ma.feature_capabilities(fatal=[], window=None, identity_ok=True, summary=None, peers=None, asks=None)
    assert caps["supplyTurnover"] == {"available": False, "reasons": ["FEATURE_DISABLED_V1"]}
    assert caps["inferredSalesFromListings"] == {"available": False, "reasons": ["FEATURE_DISABLED_V1"]}
    assert caps["saleCount"] == {"available": False, "reasons": ["NOT_COLLECTED"]}


def test_not_collected_counts_are_null_while_proven_zero_is_zero():
    from backend.scripts.build_market_activity_v1_contract_artifacts import scenarios
    specs = {s["scenario"]: s for s in scenarios()}
    missing = ma.assemble_instrument_detail(specs["not_collected"]["inputs"])
    zero = ma.assemble_instrument_detail(specs["zero_with_proof"]["inputs"])
    assert all(w["observedCount"] is None and w["provenCount"] is None for w in missing["sales"]["windows"])
    assert all(w["provenCount"] == 0 for w in zero["sales"]["windows"])
    assert zero["asks"]["state"] == "ZERO_PROVEN" and missing["asks"]["state"] == "NOT_COLLECTED"
