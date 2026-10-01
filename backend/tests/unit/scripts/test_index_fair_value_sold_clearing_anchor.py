from __future__ import annotations

import copy
import json
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from backend.scripts import index_fair_value_sold_clearing_anchor as rules
from backend.scripts import run_index_fair_value_sold_clearing_anchor_v1 as harness

OBS = date(2026, 9, 30)


def _row(i: int, title: str = "Eevee ex 167/131 SIR NM", price: str = "100.00", sold_at: str = "2026-09-20", **kw):
    base = {
        "provider_listing_id": i, "provider_card_id": 7, "canonical_card_id": "c1",
        "title": title, "price": price, "currency": "USD", "grader": None, "grade": None,
        "graded": False, "attribution": "exact", "identity_state": "EXACT",
        "sold_at": sold_at, "ingested_at": "2026-09-25T00:00:00+00:00",
        "collected_at": "2026-09-25T01:00:00+00:00",
    }
    base.update(kw)
    return base


def _verdict(title: str, number: str = "167"):
    return rules.title_verdict(title, number)


# ---- exact eligibility ----------------------------------------------------
def test_eligible_title_passes():
    assert _verdict("Eevee ex 167/131 Prismatic Evolutions SIR NM") is None
    assert _verdict("Eevee ex #167 Near Mint") is None
    assert _verdict("Eevee ex 167/131 near-mint") is None


@pytest.mark.parametrize("title", [
    "Eevee ex 167/131 Prismatic Evolutions SIR",               # no NM cue
    "Eevee ex 167/131 Mint",                                   # mint is not near mint
    "Eevee ex Prismatic Evolutions SIR NM",                    # no card number
])
def test_missing_requirements_fail_closed(title):
    assert _verdict(title) is not None


def test_card_number_is_not_matched_inside_larger_tokens_or_denominators():
    assert rules.card_number_verdict("Umbreon 1610/131 NM", "161") == rules.CARD_NUMBER_ABSENT
    assert rules.card_number_verdict("Card 144/131 NM", "131") == rules.CARD_NUMBER_ABSENT
    assert rules.card_number_verdict("SV167 NM", "167") == rules.CARD_NUMBER_ABSENT
    assert rules.card_number_verdict("Eevee 063/191 NM", "63") is None   # leading zeros
    assert rules.card_number_verdict("Eevee TG05 NM", "TG05") == rules.CARD_NUMBER_ABSENT  # non-numeric


@pytest.mark.parametrize("title", [
    "Eevee ex 167/131 NM LP", "Eevee ex 167/131 NM Lightly Played",
    "Eevee ex 167/131 NM-MP", "Eevee ex 167/131 NM moderately played",
    "Eevee ex 167/131 NM HP", "Eevee ex 167/131 NM Heavily Played",
    "Eevee ex 167/131 NM damaged", "Eevee ex 167/131 NM DMG",
    "Eevee ex 167/131 NM crease on corner", "Eevee ex 167/131 NM torn", "Eevee ex 167/131 NM water damage",
])
def test_worse_or_conflicting_condition_rejected(title):
    assert _verdict(title) == rules.WORSE_CONDITION


@pytest.mark.parametrize("title", [
    "Eevee ex 167/131 NM PSA 10", "Eevee ex 167/131 NM BGS", "Eevee ex 167/131 NM Beckett 9.5",
    "Eevee ex 167/131 NM CGC 10", "Eevee ex 167/131 NM SGC", "Eevee ex 167/131 NM AGS",
    "Eevee ex 167/131 NM TAG 9", "Eevee ex 167/131 NM ACE 10", "Eevee ex 167/131 NM Gem Mint",
    "Eevee ex 167/131 NM Black Label", "Eevee ex 167/131 NM Pristine", "Eevee ex 167/131 NM psa-ready",
])
def test_grader_or_grade_evidence_rejected(title):
    assert _verdict(title) == rules.GRADE_EVIDENCE


def test_tag_and_ace_are_only_grades_with_a_numeric_grade():
    assert _verdict("Tag Team Eevee ex 167/131 NM") is None
    assert _verdict("Ace Spec Eevee ex 167/131 NM") is None


@pytest.mark.parametrize("title", [
    "Eevee ex 167/131 NM proxy", "Eevee ex 167/131 NM fan art", "Eevee ex 167/131 NM custom card",
    "Eevee ex 167/131 NM custom case", "Eevee ex 167/131 NM extended art case",
    "Eevee ex 167/131 NM no card", "Eevee ex 167/131 NM sticker", "Eevee ex 167/131 NM digital",
    "Eevee ex 167/131 NM code card", "Eevee ex 167/131 NM lot of 3", "Eevee ex 167/131 NM bundle",
    "Eevee ex 167/131 NM repack", "Eevee ex 167/131 NM metal card",
])
def test_wrong_object_rejected(title):
    assert _verdict(title) == rules.WRONG_OBJECT


def test_literal_hp_token_is_rejected_per_contract():
    # The contract treats HP as Heavily Played; hit-point titles are a known,
    # documented false-negative (fail closed), not silently exempted.
    assert _verdict("Eevee ex 167/131 NM 200 HP") == rules.WORSE_CONDITION


def test_conflicting_number_is_v1_accepted_but_detectable_and_strict_rejects():
    title = "Eevee ex 167/131 NM Condition 075/131"
    assert rules.title_verdict(title, "167") is None
    assert rules.title_has_conflicting_card_number(title, "167") is True
    assert rules.title_verdict(title, "167", reject_conflicting_numbers=True) == rules.CARD_NUMBER_CONFLICT


@pytest.mark.parametrize("overrides,reason", [
    ({"identity_state": "AMBIGUOUS"}, rules.IDENTITY_NOT_EXACT),
    ({"identity_state": None}, rules.IDENTITY_NOT_EXACT),
    ({"attribution": "shared"}, rules.ATTRIBUTION_NOT_EXACT),
    ({"attribution": "unknown"}, rules.ATTRIBUTION_NOT_EXACT),
    ({"graded": True}, rules.GRADED_FLAG),
    ({"graded": None}, rules.GRADED_FLAG),
    ({"currency": "EUR"}, rules.NON_USD),
    ({"price": "0"}, rules.INVALID_PRICE),
    ({"price": "abc"}, rules.INVALID_PRICE),
    ({"sold_at": "garbage"}, rules.INVALID_SOLD_DATE),
    ({"sold_at": "2026-10-02"}, rules.FUTURE_DATED),
])
def test_row_level_fail_closed(overrides, reason):
    comp, got = rules.classify_row(_row(1, **overrides), card_number="167", observation_date=OBS)
    assert comp is None and got == reason


# ---- leakage guard ----------------------------------------------------------
def test_target_price_keys_on_a_comp_row_are_refused():
    for key in ("target_market_price_usd", "market_price", "target_nm_market_price"):
        with pytest.raises(RuntimeError, match="TARGET_LEAKAGE_GUARD"):
            rules.classify_row(_row(1, **{key: 123.0}), card_number="167", observation_date=OBS)


def test_select_anchor_has_no_price_parameter():
    import inspect

    params = set(inspect.signature(rules.select_anchor).parameters)
    assert params == {"comps", "observation_date", "windows", "min_comps", "boundary_extra_days"}
    assert not any("price" in name or "target" in name for name in params)
    assert not any("price" in n or "target" in n for n in inspect.signature(harness._compute_anchors).parameters)


def test_anchor_is_invariant_to_target_price():
    rows = [_row(i, price=f"{100 + i}.00", sold_at=f"2026-09-{10 + i % 15:02d}") for i in range(1, 14)]
    a = rules.build_card_result(rows, card_number="167", observation_date=OBS)
    b = rules.build_card_result(copy.deepcopy(rows), card_number="167", observation_date=OBS)
    assert a == b


# ---- window selection -------------------------------------------------------
def _comps(n: int, sold_at: str, price: str = "10.00"):
    return [
        rules.Comp(i, Decimal(price), date.fromisoformat(sold_at), None, None, "t") for i in range(n)
    ]


def test_shortest_window_with_ten_comps_is_selected():
    comps = _comps(10, "2026-09-28")
    result = rules.select_anchor(comps, OBS)
    assert result["selected_window_days"] == 7 and result["comp_count"] == 10


def test_nine_comps_do_not_qualify_and_longer_window_is_used():
    comps = _comps(9, "2026-09-28") + _comps(1, "2026-09-10")
    result = rules.select_anchor(comps, OBS)
    assert result["selected_window_days"] == 30 and result["comp_count"] == 10
    assert result["eligible_counts_by_window"]["7"] == 9


def test_insufficient_when_no_window_reaches_ten():
    result = rules.select_anchor(_comps(9, "2026-09-28"), OBS)
    assert result["status"] == "INSUFFICIENT_COMPS" and result["anchor_usd"] is None


def test_window_boundary_is_exactly_n_calendar_days():
    # 7-day window = Sep 24..Sep 30 inclusive.
    assert rules.window_start(OBS, 7) == date(2026, 9, 24)
    inside = rules.select_anchor(_comps(10, "2026-09-24"), OBS)
    outside = rules.select_anchor(_comps(10, "2026-09-23"), OBS)
    assert inside["selected_window_days"] == 7
    assert outside["selected_window_days"] == 30


def test_comps_after_observation_date_are_excluded():
    comps = _comps(10, "2026-10-01")
    assert rules.select_anchor(comps, OBS)["status"] == "INSUFFICIENT_COMPS"


# ---- statistics ---------------------------------------------------------------
def test_median_even_odd_and_spread_statistics():
    prices = ["10", "20", "30", "40", "50", "60", "70", "80", "90", "100"]
    comps = [rules.Comp(i, Decimal(p), date(2026, 9, 28 - i % 3), None, None, "t") for i, p in enumerate(prices)]
    r = rules.select_anchor(comps, OBS)
    assert r["median"] == "55.0000" and r["median_usd_2dp"] == "55.00"
    assert r["q1"] == pytest.approx(32.5) and r["q3"] == pytest.approx(77.5) and r["iqr"] == pytest.approx(45.0)
    assert r["mad"] == "25.0000"
    assert r["distinct_sale_days"] == 3
    assert r["oldest_sold_at"] == "2026-09-26" and r["newest_sold_at"] == "2026-09-28"
    odd = rules.select_anchor(comps + [rules.Comp(99, Decimal("500"), date(2026, 9, 28), None, None, "t")], OBS)
    assert odd["median"] == "60.0000"


def test_half_cent_median_rounds_half_up_for_display_but_exact_value_is_kept():
    pair = rules.select_anchor(
        [rules.Comp(i, Decimal(p), date(2026, 9, 28), None, None, "t") for i, p in enumerate(
            ["1"] * 4 + ["276.02", "276.03"] + ["999"] * 4)], OBS)
    assert pair["median"] == "276.0250" and pair["median_usd_2dp"] == "276.03"


# ---- row-set behaviour, duplicates, forward-replay cutoff ----------------------
def test_duplicate_provider_listing_rows_are_counted_once():
    rows = [_row(1), _row(1)]
    r = rules.build_card_result(rows, card_number="167", observation_date=OBS)
    assert r["eligible_rows_all_time"] == 1
    assert r["exclusion_counts"][rules.DUPLICATE_LISTING] == 1


def test_retrospective_label_and_cutoff_enforcement():
    rows = [_row(i) for i in range(1, 12)]
    retro = rules.build_card_result(rows, card_number="167", observation_date=OBS)
    assert retro["evidence_semantics"] == "RETROSPECTIVE_BACKFILLED_EVIDENCE"
    assert retro["status"] == "ANCHORED"
    cutoff = datetime(2026, 9, 24, tzinfo=timezone.utc)  # all rows were collected 2026-09-25
    forward = rules.build_card_result(rows, card_number="167", observation_date=OBS, information_cutoff=cutoff)
    assert forward["evidence_semantics"] == "AS_KNOWN_AT_CUTOFF"
    assert forward["status"] == "INSUFFICIENT_COMPS"
    assert forward["exclusion_counts"][rules.NOT_YET_COLLECTED] == 11
    missing = rules.build_card_result(
        [_row(i, collected_at=None) for i in range(1, 12)], card_number="167",
        observation_date=OBS, information_cutoff=cutoff)
    assert missing["exclusion_counts"][rules.NOT_YET_COLLECTED] == 11  # unknown availability fails closed


def test_determinism():
    rows = [_row(i, price=f"{90 + i}.00") for i in range(1, 15)]
    a = json.dumps(rules.build_card_result(rows, card_number="167", observation_date=OBS), sort_keys=True)
    b = json.dumps(rules.build_card_result(list(reversed(rows)), card_number="167", observation_date=OBS), sort_keys=True)
    assert a == b


# ---- harness guards ---------------------------------------------------------------
def test_panel_fingerprint_is_reproduced_exactly():
    panel = harness.load_panel()
    assert panel["panel_fingerprint"] == "9e3068ffb2e644e3dab2f5c237271afa4efe061ed8f3139187dc9e8331bd1d1f"
    assert len(panel["rows"]) == 207


def test_tampered_panel_is_refused(tmp_path):
    panel = json.loads(harness.PANEL_MANIFEST.read_text(encoding="utf-8"))
    panel["rows"][0]["card_number"] = "999"
    path = tmp_path / "panel.json"
    path.write_text(json.dumps(panel), encoding="utf-8")
    with pytest.raises(RuntimeError, match="PANEL_FINGERPRINT_MISMATCH"):
        harness.load_panel(path)


class _FakeQuery:
    def __init__(self, log):
        self.log = log

    def __getattr__(self, name):
        self.log.append(name)
        return lambda *a, **k: self


class _FakeClient:
    def __init__(self):
        self.calls: list[str] = []

    def table(self, name):
        self.calls.append(f"table:{name}")
        return _FakeQuery(self.calls)


def test_read_only_client_blocks_every_write_surface():
    client = harness.ReadOnlyClient(_FakeClient())
    table = client.table("pkmnprices_ebay_sold_evidence_v1")
    for method in ("insert", "update", "upsert", "delete"):
        with pytest.raises(PermissionError, match="READ_ONLY_GUARD"):
            getattr(table, method)
    query = table.select("*")
    for method in ("insert", "update", "upsert", "delete", "rpc"):
        with pytest.raises(PermissionError, match="READ_ONLY_GUARD"):
            getattr(query, method)
    with pytest.raises(PermissionError, match="READ_ONLY_GUARD"):
        client.rpc("anything")
    query.eq("a", 1).order("b").range(0, 9).execute()
    assert client.read_requests == ["execute"]


def test_runner_module_has_no_write_or_provider_surface():
    import inspect
    import re

    source = inspect.getsource(harness) + inspect.getsource(rules)
    # Query-builder writes are always chained off a call result: `...).insert(`.
    assert not re.search(r"\)\s*\.(insert|update|upsert|delete|rpc)\(", source)
    assert ".rpc(" not in source
    for forbidden in ("PkmnPricesClient", "pkmnprices_client", "requests.", "httpx", "subprocess", "urllib"):
        assert forbidden not in source, forbidden


def _synthetic_snapshot(panel, price_scale: float):
    rows = panel["rows"]
    evidence, idents, prices, obs = [], [], [], []
    listing = 1
    for n, pr in enumerate(rows):
        cid, vid = pr["canonical_card_id"], pr["card_variant_id"]
        idents.append({"provider_card_id": 1000 + n, "canonical_card_id": cid, "tcgplayer_product_id": "1", "language": "English"})
        for k in range(12):
            evidence.append({
                "provider_listing_id": listing, "provider_card_id": 1000 + n, "canonical_card_id": cid,
                "title": f"{pr['card_name']} {pr['card_number']}/131 NM", "price": f"{20 + k}.00",
                "currency": "USD", "grader": None, "grade": None, "graded": False,
                "provider_variant": None, "attribution": "exact", "sold_at": f"2026-09-{20 + k % 9:02d}",
                "ingested_at": None, "collected_at": "2026-09-29T00:00:00+00:00",
                "identity_state": "EXACT", "fair_value_signal_eligible": True,
                "exclusion_reason": None, "run_id": "r"})
            listing += 1
        prices.append({"canonical_card_id": cid, "card_variant_id": vid, "condition_id": "nm", "market_price": 25.0 * price_scale,
                       "captured_at": "2026-09-30", "source": "TCGPlayer"})
        obs.append({"card_variant_id": vid, "condition_id": "nm", "market_price": 25.0 * price_scale,
                    "captured_at": "2026-09-30", "source": "TCGPlayer", "currency": "USD"})
    return {"panel_fingerprint": panel["panel_fingerprint"], "identities": idents, "evidence": evidence,
            "prices": prices, "observation_prices": obs, "fetched_at_utc": "x"}


def test_target_price_is_evaluation_only_end_to_end():
    panel = harness.load_panel()
    low = harness.analyze(_synthetic_snapshot(panel, 1.0), panel, include_structural=False)
    high = harness.analyze(_synthetic_snapshot(panel, 40.0), panel, include_structural=False)
    keys = ("status", "selected_window_days", "comp_count", "anchor_usd", "eligible_counts_by_window")
    for a, b in zip(low["card_results"], high["card_results"]):
        assert {k: a[k] for k in keys} == {k: b[k] for k in keys}
    assert low["price_band_evaluation"]["overall"] != high["price_band_evaluation"]["overall"]


def test_artifacts_are_byte_deterministic(tmp_path):
    panel = harness.load_panel()
    snap = _synthetic_snapshot(panel, 1.0)
    first = harness.write_artifacts(harness.analyze(snap, panel, include_structural=False, snapshot_sha256="s"), tmp_path / "a")
    second = harness.write_artifacts(harness.analyze(copy.deepcopy(snap), panel, include_structural=False, snapshot_sha256="s"), tmp_path / "b")
    assert first == second
