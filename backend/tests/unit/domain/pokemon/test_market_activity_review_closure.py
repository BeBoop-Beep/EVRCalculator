"""FMA-0.1 review closure: reproduction tests for the six FMA-0 review findings.

Each test in this module was written FIRST against the unmodified FMA-0 module
(commit 36a15dc0) and observed to fail (see FMA0_REVIEW_CLOSURE.md for the
recorded red run). Inputs are built through the generator's own fixture
builders so the same test source exercises the real assembler shapes.

Findings:
  F1  observed facts preserved when coverage receipts are absent
  F2  malformed / future / unbound completeness proof fails closed
  F3  unconfirmed offers never set a current asking price; unknown pagination
  F4  dated chart series contract (sparse daily, zero-vs-missing, axes)
  F5  independent activity-generation pin, roster ref, opaque cursor, POST
  F6  full-roster aggregation, rank integrity, unique/bound peers, row checks
"""
from __future__ import annotations

import copy
import json
import socket
from datetime import datetime, timezone
from pathlib import Path

import pytest

from backend.domain.pokemon import market_activity as ma
from backend.scripts import build_market_activity_v1_contract_artifacts as gen

ROOT = Path(__file__).resolve().parents[5]
OUT = ROOT / "docs" / "research" / "market_activity_v1"
CONTRACTS = OUT / "contracts"
NOW = datetime(2026, 9, 30, 12, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    def refuse(*_args, **_kwargs):
        raise AssertionError("review-closure tests attempted network/DB egress")
    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket.socket, "connect_ex", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)


def _schema(name):
    return json.loads((CONTRACTS / name).read_text(encoding="utf-8"))


def _base_sold():
    return copy.deepcopy(gen._detail()["sold"])


def _window(detail, days):
    return next(w for w in detail["sales"]["windows"] if w["days"] == days)


# ---------------------------------------------------------------------------
# F1. Preserve observed facts when coverage receipts are absent
# ---------------------------------------------------------------------------
def test_f1_legacy_rows_without_walk_receipts_keep_observed_counts():
    sold = dict(_base_sold(), walks=[])
    detail = ma.assemble_instrument_detail(gen._detail(sold=sold))
    w30 = _window(detail, 30)
    # 8 eligible raw rows fall in the 30d window (fixture 01 proves the same 8).
    assert w30["observedCount"] == 8
    assert w30["provenCount"] is None
    assert w30["priceSummary"] is not None and w30["priceSummary"]["recordCount"] == 8
    assert w30["readiness"]["state"] != "PROVEN"
    caps = detail["capabilities"]
    assert caps["observedSales"]["available"] is True
    assert caps["saleCount"]["available"] is False
    assert caps["activityPercentile"]["available"] is False


def test_f1_missing_collection_differs_from_known_collection_with_zero_matches():
    missing = ma.assemble_instrument_detail(gen._detail(sold=dict(_base_sold(), records=[], walks=[])))
    assert all(w["observedCount"] is None for w in missing["sales"]["windows"])
    assert missing["capabilities"]["observedSales"]["available"] is False
    # A known collection (rows exist for this provider card) with no row in the
    # 7d window is an observed zero, not "not collected".
    old_only = [r for r in gen._raw_records() if r["soldAt"] < "2026-09-01"]
    known = ma.assemble_instrument_detail(gen._detail(sold=dict(_base_sold(), records=old_only, walks=[])))
    assert _window(known, 7)["observedCount"] == 0
    assert _window(known, 7)["provenCount"] is None


# ---------------------------------------------------------------------------
# F2. Fail closed on malformed / future completeness proof
# ---------------------------------------------------------------------------
def _with_walk(mutate):
    sold = _base_sold()
    walk = copy.deepcopy(sold["walks"][0])
    mutate(walk)
    sold["walks"] = [walk]
    return ma.assemble_instrument_detail(gen._detail(sold=sold))


def test_f2_future_right_edge_is_never_proven():
    detail = _with_walk(lambda w: w["rightEdge"].update(reconciledThrough="2027-01-01T00:00:00Z"))
    for window in detail["sales"]["windows"]:
        assert window["readiness"]["state"] != "PROVEN"
        assert window["provenCount"] is None


def test_f2_unknown_has_more_is_not_exhaustion():
    def truncate(walk):
        walk["pages"] = walk["pages"][:1]
        walk["pages"][0]["hasMore"] = None
    detail = _with_walk(truncate)
    w180 = _window(detail, 180)
    assert w180["readiness"]["state"] != "PROVEN"
    assert w180["readiness"]["exhausted"] is False


@pytest.mark.parametrize("label,mutate", [
    ("wrong_card", lambda w: w.update(providerCardId="999999")),
    ("right_edge_wrong_card", lambda w: w["rightEdge"].update(providerCardId="999999")),
    ("right_edge_wrong_filter", lambda w: w["rightEdge"].update(filterFingerprint="f-other")),
    ("right_edge_wrong_tier", lambda w: w["rightEdge"].update(stream="GRADE_FILTERED", graderFilter="PSA",
                                                               gradeFilter="10")),
    ("uncommitted_collection", lambda w: w.update(committed=False)),
    ("missing_row_count", lambda w: w["pages"][1].pop("rowCount")),
    ("negative_row_count", lambda w: w["pages"][1].update(rowCount=-5)),
    ("string_has_more", lambda w: w["pages"][0].update(hasMore="true")),
    ("inverted_dates", lambda w: w["pages"][1].update(minSoldAt="2026-08-25", maxSoldAt="2026-08-20")),
    ("missing_output_cursor", lambda w: w["pages"][0].update(outputCursorHash=None)),
    ("right_edge_completed_not_bool", lambda w: w["rightEdge"].update(completed="yes")),
])
def test_f2_malformed_or_unbound_receipts_fail_closed(label, mutate):
    detail = _with_walk(mutate)
    w30 = _window(detail, 30)
    assert w30["readiness"]["state"] != "PROVEN", label
    assert w30["provenCount"] is None, label


def test_f2_unknown_pagination_never_advances_a_checkpoint():
    walk = {"order": "sold_desc", "sort": "date_desc", "startedFromHead": True, "filterFingerprint": "f1",
            "pages": [{"pageIndex": 0, "inputCursorHash": None, "outputCursorHash": None, "hasMore": None,
                       "maxSoldAt": "2026-09-29", "minSoldAt": "2026-09-01", "rowCount": 2,
                       "filterFingerprint": "f1", "ingestedAts": ["2026-09-29T01:00:00Z"]}]}
    decision = ma.checkpoint_advance_decision(walk)
    assert decision["allowed"] is False and decision["watermark"] is None


# ---------------------------------------------------------------------------
# F3. Unconfirmed offers never set a current asking price
# ---------------------------------------------------------------------------
def _offer(price, confirmed, ship="0.00", ship_prov="EXPLICIT", qty=1, qty_prov="EXPLICIT"):
    return {"itemPrice": price, "shippingPrice": ship, "shippingProvenance": ship_prov, "quantity": qty,
            "quantityProvenance": qty_prov, "providerSnapshotAt": confirmed, "listingUpdatedAt": None}


def _snap(offers, **extra):
    snap = {"observationState": "OBSERVED", "observedAt": "2026-09-30T11:59:00Z", "hasMore": False,
            "offers": offers}
    snap.update(extra)
    return snap


def test_f3_unconfirmed_offer_cannot_set_current_lowest_ask():
    snap = _snap([_offer("10.00", "2026-09-30T08:00:00Z"), _offer("1.00", None)])
    result = ma.evaluate_supply_snapshot(snap, evaluated_at=NOW)
    assert result["state"] != "FRESH"
    assert (result["lowestAsk"] or {}).get("price") != {"amount": "1.00", "currency": "USD"}
    caps = ma.feature_capabilities(fatal=[], window=None, identity_ok=True, summary=None, peers=None,
                                   asks=result)
    assert caps["currentAsks"]["available"] is False
    assert caps["askDepth"]["available"] is False


def test_f3_unconfirmed_offer_never_counts_toward_depth():
    snap = _snap([_offer("10.00", "2026-09-30T08:00:00Z"), _offer("1.00", None, qty=5)])
    result = ma.evaluate_supply_snapshot(snap, evaluated_at=NOW)
    assert result["capturedListingCount"] == 1
    assert result["capturedQuantity"]["value"] == 1
    assert result["depth"] != "COMPLETE_AT_SOURCE"


def test_f3_missing_has_more_is_unknown_depth():
    snap = _snap([_offer("10.00", "2026-09-30T08:00:00Z")])
    del snap["hasMore"]
    result = ma.evaluate_supply_snapshot(snap, evaluated_at=NOW)
    assert result["depth"] != "COMPLETE_AT_SOURCE"
    caps = ma.feature_capabilities(fatal=[], window=None, identity_ok=True, summary=None, peers=None,
                                   asks=result)
    assert caps["askDepth"]["available"] is False


@pytest.mark.parametrize("has_more", [True, None, "false"])
def test_f3_empty_response_with_contradictory_or_unknown_pagination_is_not_zero(has_more):
    snap = _snap([], hasMore=has_more, sourceConfirmedAt="2026-09-30T07:00:00Z")
    result = ma.evaluate_supply_snapshot(snap, evaluated_at=NOW)
    assert result["state"] != "ZERO_PROVEN"
    assert result["capturedListingCount"] is None


def test_f3_current_ask_capability_expires_with_provider_confirmation():
    detail = ma.assemble_instrument_detail(gen._detail())
    cap = detail["capabilities"]["currentAsks"]
    assert cap["available"] is True
    assert cap["expiresAt"] == "2026-10-01T08:00:00Z"   # providerConfirmedAt + 24h
    later = ma.reevaluate_capabilities(detail["capabilities"], at="2026-10-01T08:00:01Z")
    assert later["currentAsks"]["available"] is False
    assert "ASKS_STALE" in later["currentAsks"]["reasons"]


# ---------------------------------------------------------------------------
# F4. The chart contract: dated series
# ---------------------------------------------------------------------------
def test_f4_group_and_instrument_responses_define_dated_series():
    group = _schema("activity_response.schema.json")
    detail = _schema("instrument_detail_response.schema.json")
    assert "series" in group["properties"]
    assert "series" in detail["properties"]
    common = _schema("common.schema.json")["$defs"]
    assert {"GroupSeries", "InstrumentSeries"} <= set(common)


def test_f4_instrument_series_is_sparse_daily_and_never_repeats_window_totals():
    detail = ma.assemble_instrument_detail(gen._detail())
    series = detail["series"]
    points = series["sales"]["counts"]["points"]
    assert [p["date"] for p in points] == sorted({p["date"] for p in points})
    assert sum(p["observedCount"] for p in points) == _window(detail, 180)["observedCount"]
    assert all(p["observedCount"] >= 1 for p in points)          # sparse: no stored zeros


# ---------------------------------------------------------------------------
# F5. Pin evidence, roster and pagination separately
# ---------------------------------------------------------------------------
def test_f5_constituent_request_pins_activity_generation_roster_and_cursor():
    request = _schema("constituent_page_request.schema.json")
    props = request["properties"]
    assert {"activityGenerationId", "rosterRef", "cursor"} <= set(props)
    assert "afterRank" not in props
    page = _schema("constituent_page_response.schema.json")
    next_cursor = page["properties"]["page"]["anyOf"][0]["properties"]["nextCursor"]
    assert "integer" not in json.dumps(next_cursor)


def test_f5_activity_refresh_under_unchanged_market_generation_is_rejected():
    inputs = gen._roster_inputs({"limit": 2})
    inputs["request"]["activityGenerationId"] = "11111111-1111-4111-8111-111111111111"
    inputs["activityGeneration"] = {"activityGenerationId": "22222222-2222-4222-8222-222222222222",
                                    "state": "SERVING"}
    page = ma.assemble_constituent_page(inputs)
    assert page["availability"]["state"] == "UNAVAILABLE"
    assert "ACTIVITY_GENERATION_MISMATCH" in page["availability"]["reasons"]


def test_f5_next_cursor_is_opaque_and_revision_bound():
    first = ma.assemble_constituent_page(gen._roster_inputs({"limit": 2}))
    cursor = first["page"]["nextCursor"]
    assert isinstance(cursor, str) and not cursor.isdigit()


def test_f5_docs_use_post_reads_and_sha256_fingerprint_with_separate_activity_id():
    contract = (OUT / "CONTRACT.md").read_text(encoding="utf-8")
    decision = (OUT / "SCHEMA_DECISION.md").read_text(encoding="utf-8")
    assert "GET /market/explorer/activity" not in contract
    assert "POST /market/explorer/activity" in contract
    assert "echo `activity_generation_id` in `evidenceFingerprint`" not in decision.replace("\n", " ")
    for bucket in ("FMA-1", "FMA-2", "FMA-3"):
        assert bucket in contract


# ---------------------------------------------------------------------------
# F6. Full-roster and peer integrity
# ---------------------------------------------------------------------------
def _member(rank, variant):
    return {"rank": rank, "cardVariantId": variant, "instrumentKey": f"card:{variant}:raw",
            "detailInputs": {"canonicalCardId": None,
                             "sold": {"candidateScope": "FULL_CARD_VARIANT_SET",
                                      "candidates": [{"id": variant, "edition": None, "printingType": "holo"}],
                                      "records": [], "walks": []},
                             "asks": None, "peers": None}}


def _big_roster_inputs(count, *, order=None):
    inputs = gen._roster_inputs({})
    members = [_member(r, f"00000000-0000-4000-8000-{r:012d}") for r in range(1, count + 1)]
    if order is not None:
        members = [members[i] for i in order]
    inputs["members"] = members
    inputs["roster"] = dict(inputs["roster"], denominator=count)
    return inputs


@pytest.mark.parametrize("count", [101, 207])
def test_f6_group_aggregation_covers_rosters_larger_than_one_page(count):
    group = ma.aggregate_group_activity(_big_roster_inputs(count))
    assert group["coverage"]["rosterDenominator"] == count
    assert group["coverage"]["notCollected"] == count


def test_f6_pages_are_rank_sorted_even_when_members_arrive_shuffled():
    inputs = _big_roster_inputs(5, order=[4, 2, 0, 3, 1])
    inputs["request"] = dict(inputs["request"], limit=2)
    page = ma.assemble_constituent_page(inputs)
    assert [row["rank"] for row in page["rows"]] == [1, 2]


def test_f6_duplicate_or_gapped_ranks_are_rejected():
    inputs = _big_roster_inputs(3)
    inputs["members"][2]["rank"] = 2
    page = ma.assemble_constituent_page(dict(inputs, request=dict(inputs["request"], limit=3)))
    assert page["availability"]["state"] == "UNAVAILABLE"


def test_f6_thirty_copies_of_one_peer_are_one_peer():
    key = "pop"
    peers = [{"instrumentKey": "p0", "populationKey": key, "value": 3}] * 30
    result = ma.activity_percentile("t", 5, peers, population_key=key)
    assert result["eligibleOtherPeerCount"] == 1
    assert result["state"] == "INSUFFICIENT_PEERS"


def test_f6_conflicting_peer_observations_are_quarantined():
    key = "pop"
    peers = [{"instrumentKey": f"p{i}", "populationKey": key, "value": i % 7} for i in range(30)]
    peers.append({"instrumentKey": "p0", "populationKey": key, "value": 99})
    result = ma.activity_percentile("t", 5, peers, population_key=key)
    assert result["eligibleOtherPeerCount"] == 29
    assert result["state"] == "INSUFFICIENT_PEERS"


def test_f6_peers_from_a_different_date_window_with_the_same_duration_are_excluded():
    duration_only = "30d|pkmnprices_ebay_sold|USD|RAW|PROVEN"
    rows = [{"instrumentKey": f"card:00000000-0000-4000-8000-{i:012d}:raw", "populationKey": duration_only,
             "value": i % 9} for i in range(35)]
    peers = dict(gen._detail()["peers"], values=rows)
    detail = ma.assemble_instrument_detail(gen._detail(peers=peers))
    assert detail["peers"]["state"] != "AVAILABLE"
    assert detail["peers"]["eligibleOtherPeerCount"] == 0


def test_f6_invalid_rows_are_quarantined_before_deduplication():
    valid = {"source": ma.SOLD_SOURCE, "providerCardId": "1", "listingId": "1", "price": "10.00",
             "currency": "USD", "soldAt": "2026-09-20", "collectedAt": "2026-09-30T00:00:00Z"}
    bad_money = dict(valid, listingId="2", price="ten dollars")
    no_listing = dict(valid, listingId=None)
    kept, excluded = ma.dedupe_sold_records([valid, bad_money, no_listing, dict(valid)])
    assert [r["listingId"] for r in kept] == ["1"]
    assert excluded == {"EVIDENCE_DUPLICATE": 1, "INVALID_EVIDENCE_ROW": 2}


# ---------------------------------------------------------------------------
# Additional FMA-0.1 coverage (written after the fix; not part of the red run)
# ---------------------------------------------------------------------------
def test_f1_explicit_collection_record_is_observation_not_proof():
    record = {"collected": True, "providerCardId": gen.PROVIDER_A, "source": "pkmnprices_sold_sync_state_v1"}
    detail = ma.assemble_instrument_detail(gen._detail(sold=dict(_base_sold(), records=[], walks=[],
                                                                 collectionRecord=record)))
    assert detail["sales"]["observation"]["basis"] == "COLLECTION_RECORD"
    assert all(w["observedCount"] == 0 and w["provenCount"] is None for w in detail["sales"]["windows"])
    assert all(w["readiness"]["reasons"] == ["COMPLETENESS_RECEIPT_MISSING"] for w in detail["sales"]["windows"])
    # A record for another provider card is not collection evidence for this one.
    other = dict(record, providerCardId="123")
    missing = ma.assemble_instrument_detail(gen._detail(sold=dict(_base_sold(), records=[], walks=[],
                                                                  collectionRecord=other)))
    assert missing["sales"]["observation"]["state"] == "NOT_COLLECTED"


def test_f2_bound_valid_receipt_still_proves():
    detail = ma.assemble_instrument_detail(gen._detail())
    assert all(w["readiness"]["state"] == "PROVEN" for w in detail["sales"]["windows"])


def test_f3_unconfirmed_offers_keep_their_provenance_separately():
    snap = _snap([_offer("10.00", "2026-09-30T08:00:00Z"),
                  _offer("1.00", None, ship=None, ship_prov="UNKNOWN", qty_prov="DEFAULTED")])
    result = ma.evaluate_supply_snapshot(snap, evaluated_at=NOW)
    assert result["state"] == "PARTIALLY_CONFIRMED" and result["offerQualification"] == "NOT_CURRENT"
    unconfirmed = result["unconfirmedOffers"]
    assert unconfirmed["lowestAsk"] == {"basis": "ITEM_ONLY", "price": {"amount": "1.00", "currency": "USD"}}
    assert unconfirmed["reasons"] == ["SHIPPING_UNKNOWN", "QUANTITY_DEFAULTED"]
    assert result["lowestAsk"]["price"]["amount"] == "10.00"


def test_f5_custom_market_maps_by_published_revision_without_the_query_builder():
    fp = "ab" * 32
    ref = {"kind": "QUERY_CACHE_PUBLISHED_REVISION", "queryFingerprint": fp,
           "revisionId": "33333333-3333-4333-8333-333333333333", "computedThrough": "2026-09-29"}
    inputs = gen._roster_inputs({"limit": 3, "cursor": None, "rosterRef": ref,
                                 "marketKey": ma.custom_market_key(fp)},
                                activity_generation=dict(gen.ACTIVITY_GENERATION, rosterRef=ref))
    page = ma.assemble_constituent_page(inputs)
    assert page["availability"]["state"] == "AVAILABLE"
    assert page["roster"]["rosterRevision"] == ref
    wrong_key = ma.assemble_constituent_page(dict(inputs, request=dict(inputs["request"], marketKey="set:x")))
    assert wrong_key["availability"]["reasons"] == ["ROSTER_REVISION_MISMATCH"]
    bare = dict(inputs, request=dict(inputs["request"], rosterRef={"kind": "QUERY_CACHE_FINGERPRINT",
                                                                  "queryFingerprint": fp}))
    assert "QUERY_FINGERPRINT_IS_NOT_A_REVISION" in ma.assemble_constituent_page(bare)["availability"]["reasons"]


def test_f5_tampered_or_rebound_cursor_is_rejected():
    first = ma.assemble_constituent_page(gen._roster_inputs({"limit": 1, "cursor": None}))
    cursor = first["page"]["nextCursor"]
    tampered = cursor[:-1] + ("0" if cursor[-1] != "0" else "1")
    bad = ma.assemble_constituent_page(gen._roster_inputs({"limit": 1, "cursor": tampered}))
    assert bad["availability"]["reasons"] == ["CURSOR_INVALID"]
    other_window = ma.assemble_constituent_page(gen._roster_inputs({"limit": 1, "cursor": cursor, "windowDays": 90}))
    assert other_window["availability"]["reasons"] == ["CURSOR_MISMATCH"]


@pytest.mark.parametrize("count,limit", [(101, 100), (207, 100), (207, 37)])
def test_f6_pages_concatenate_to_the_full_roster_and_match_the_group_oracle(count, limit):
    inputs = _big_roster_inputs(count, order=list(reversed(range(count))))
    for member in inputs["members"][::20]:
        variant = member["cardVariantId"]
        member["detailInputs"]["sold"] = {"providerCardId": f"p{member['rank']}", "collectionRecord": None,
                                          "candidateScope": "FULL_CARD_VARIANT_SET",
                                          "candidates": [{"id": variant, "edition": None, "printingType": "holo"}],
                                          "records": [gen._record(member["rank"], "2026-09-20", "2.00",
                                                                  providerCardId=f"p{member['rank']}")],
                                          "walks": []}
    ranks, observed, cursor = [], 0, None
    while True:
        page = ma.assemble_constituent_page(dict(inputs, request=dict(inputs["request"], limit=limit, cursor=cursor)))
        assert page["availability"]["state"] == "AVAILABLE"
        ranks += [r["rank"] for r in page["rows"]]
        observed += sum(r["observedCount"] or 0 for r in page["rows"])
        cursor = page["page"]["nextCursor"]
        if cursor is None:
            break
    assert ranks == list(range(1, count + 1))
    group = ma.aggregate_group_activity(inputs)
    assert group["totals"]["observedSaleCountLowerBound"] == observed
    assert group["coverage"]["rosterDenominator"] == count


def test_f6_duplicate_variant_in_roster_is_rejected():
    inputs = _big_roster_inputs(3)
    inputs["members"][1] = dict(inputs["members"][1], cardVariantId=inputs["members"][0]["cardVariantId"],
                                instrumentKey=inputs["members"][0]["instrumentKey"])
    group = ma.aggregate_group_activity(inputs)
    assert group["availability"] == {"state": "UNAVAILABLE", "reasons": ["ROSTER_INTEGRITY_VIOLATION"]}


def test_f6_market_roster_peer_scope_is_bound_to_roster_and_activity_generation():
    scope = ma.peer_scope({"kind": "MARKET_ROSTER", "rosterRef": gen.ROSTER_REF,
                           "cohortRevision": gen.ACTIVITY_GEN}, roster_ref=gen.ROSTER_REF,
                          activity_generation_id=gen.ACTIVITY_GEN)
    assert scope["scopeLabel"] == ma.MARKET_ROSTER_SCOPE_LABEL and scope["claimsAllPokemon"] is False
    with pytest.raises(ValueError):
        ma.peer_scope({"kind": "MARKET_ROSTER", "rosterRef": gen.ROSTER_REF, "cohortRevision": gen.ACTIVITY_GEN_NEXT},
                      roster_ref=gen.ROSTER_REF, activity_generation_id=gen.ACTIVITY_GEN)
    with pytest.raises(ValueError):
        ma.peer_scope({"kind": "ALL_POKEMON", "cohortRevision": "x"})
    research = ma.peer_scope_key(ma.peer_scope(gen._peer_scope()))
    assert ma.peer_scope_key(scope) != research
