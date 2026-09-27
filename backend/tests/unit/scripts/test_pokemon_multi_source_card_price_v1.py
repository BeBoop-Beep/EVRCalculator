import itertools
import re
from datetime import date
from pathlib import Path

import pytest

from backend.scripts import freeze_ebay_active_ask_v1 as p4c
from backend.scripts import pokemon_multi_source_card_price_v1 as pol
from backend.scripts import p5b_cohort_builder as cb

ROOT = Path(__file__).resolve().parents[4]
MIGRATION = "20260921010000_p5b_multi_source_card_prices_shadow_v1.sql"
D = date(2026, 9, 20)
NM = "4f8d1181-670e-4aea-937c-4d98d2e531a6"


def tcg(price="26.49", observed="2026-09-19", variant="v1", card="c1"):
    return {"canonical_card_id": card, "card_variant_id": variant, "market_price": price, "captured_at": observed}


def ebay(price="28.49", depth="SUFFICIENT", variant="v1", card="c1", version=pol.EBAY_ESTIMATOR_VERSION):
    return {"canonical_card_id": card, "card_variant_id": variant, "estimated_price": price, "depth_state": depth,
            "estimator_version": version, "distinct_seller_count": 5, "eligible_listing_count": 5,
            "market_date": "2026-09-20", "estimator_fingerprint": "f" * 64}


@pytest.mark.parametrize("age,expected", [(0, "FRESH"), (1, "FRESH"), (2, "AGING"), (7, "AGING"), (8, "STALE"), (162, "STALE")])
def test_freshness_classification(age, expected):
    assert pol.classify_freshness(age, "1.00") == expected


def test_freshness_missing_when_no_price_or_date():
    assert pol.classify_freshness(None, "1.00") == "MISSING"
    assert pol.classify_freshness(1, None) == "MISSING"


def test_agreement_classification_bands_and_dollar_floor():
    assert pol.classify_agreement("100.00", "107.00")["state"] == "AGREE"
    assert pol.classify_agreement("100.00", "120.00")["state"] == "MODERATE_DISAGREEMENT"
    assert pol.classify_agreement("100.00", "136.00")["state"] == "SEVERE_DISAGREEMENT"
    assert pol.classify_agreement("100.00", "60.00")["state"] == "SEVERE_DISAGREEMENT"
    # shipping-scale dollar differences on cheap cards are not disagreement
    assert pol.classify_agreement("0.17", "0.99")["state"] == "AGREE"
    assert pol.classify_agreement("0.25", "2.35")["state"] == "SEVERE_DISAGREEMENT"
    assert pol.classify_agreement("10.00", None)["state"] == "SINGLE_SOURCE_ONLY"
    assert pol.classify_agreement(None, "10.00")["state"] == "SINGLE_SOURCE_ONLY"


def test_fresh_tcg_is_primary_without_ebay():
    row = pol.decide(tcg(), None, D, NM)
    assert (row["decision_state"], row["selected_price_source"], row["selected_price"]) == ("TCGPLAYER_PRIMARY", "TCGPLAYER", "26.49")


def test_fresh_tcg_with_agreeing_ebay_is_corroborated_and_price_stays_tcg():
    row = pol.decide(tcg("26.49"), ebay("28.49"), D, NM)
    assert row["decision_state"] == "TCGPLAYER_PRIMARY_EBAY_CORROBORATED"
    assert row["selected_price"] == "26.49" and row["selected_price_source"] == "TCGPLAYER"


def test_moderate_and_severe_disagreement_keep_tcg_and_expose_state():
    moderate = pol.decide(tcg("312.61"), ebay("419.43"), D, NM)  # high-value case, +34.2%
    assert moderate["decision_state"] == "TCGPLAYER_PRIMARY_EBAY_MODERATE_DISAGREEMENT"
    severe = pol.decide(tcg("300.00"), ebay("500.00"), D, NM)
    assert severe["decision_state"] == "TCGPLAYER_PRIMARY_SOURCE_DISAGREEMENT"
    assert severe["selected_price"] == "300.00" and severe["selected_price_source"] == "TCGPLAYER"
    assert severe["source_agreement_state"] == "SEVERE_DISAGREEMENT"


def test_missing_tcg_with_sufficient_ebay_falls_back():
    row = pol.decide(None, ebay("14.99", card="c9", variant="v9"), D, NM)
    assert (row["decision_state"], row["selected_price_source"], row["selected_price"]) == ("EBAY_ACTIVE_ASK_FALLBACK", "EBAY_ACTIVE_ASK", "14.99")
    assert row["tcgplayer_freshness_state"] == "MISSING" and row["source_agreement_state"] == "SINGLE_SOURCE_ONLY"


@pytest.mark.parametrize("depth", ["THIN", "INSUFFICIENT"])
def test_thin_or_insufficient_ebay_never_fills(depth):
    row = pol.decide(None, ebay(None, depth=depth, card="c9", variant="v9"), D, NM)
    assert row["decision_state"] == "UNPRICED" and row["selected_price"] is None and row["selected_price_source"] is None


def test_thin_ebay_with_numeric_price_still_never_fills():
    row = pol.decide(None, ebay("9.99", depth="THIN", card="c9", variant="v9"), D, NM)
    assert row["decision_state"] == "UNPRICED"


def test_stale_and_aging_tcg_are_retained_without_ebay_override():
    stale = pol.decide(tcg("51.17", "2026-08-17"), ebay("55.94"), D, NM)
    assert stale["decision_state"] == "TCGPLAYER_STALE_RETAINED" and stale["selected_price_source"] == "TCGPLAYER"
    aging = pol.decide(tcg("51.17", "2026-09-15"), ebay("55.94"), D, NM)
    assert aging["decision_state"] == "TCGPLAYER_AGING_RETAINED" and aging["selected_price"] == "51.17"


def test_exact_variant_join_and_no_cross_variant_comparison():
    row = pol.decide(tcg(variant="v1"), ebay("40.00", variant="OTHER"), D, NM)
    assert row["source_agreement_state"] == "SINGLE_SOURCE_ONLY" and row["source_ratio"] is None
    assert "EBAY_VARIANT_MISMATCH" in row["decision_reason"]
    assert row["selected_price_source"] == "TCGPLAYER"
    assert pol.decide(None, ebay("14.99", variant="OTHER"), D, NM)["selected_price_source"] == "EBAY_ACTIVE_ASK"
    unresolved = pol.decide(None, ebay("14.99", variant=None), D, NM)
    assert unresolved["decision_state"] == "UNPRICED" and "EBAY_VARIANT_UNRESOLVED" in unresolved["decision_reason"]


def test_ebay_estimator_version_mismatch_is_not_usable():
    row = pol.decide(None, ebay("14.99", version="some_other_estimator"), D, NM)
    assert row["decision_state"] == "UNPRICED"


def test_no_fabricated_numeric_blend():
    tcg_prices = ["0.25", "3.63", "26.49", "312.61", "2283.14", None]
    ebay_prices = ["0.99", "4.75", "28.49", "419.43", "2450.00", None]
    for tp, ep, observed, depth in itertools.product(tcg_prices, ebay_prices, ["2026-09-19", "2026-08-01", None], ["SUFFICIENT", "THIN"]):
        row = pol.decide(tcg(tp, observed) if tp else None, ebay(ep, depth) if ep else None, D, NM)
        allowed = {None, row["tcgplayer_price"], row["ebay_price"]}
        assert row["selected_price"] in allowed
        assert row["selected_price_source"] in (None, "TCGPLAYER", "EBAY_ACTIVE_ASK")
        assert row["selected_price_source"] != "BLENDED"
        if row["selected_price_source"] == "EBAY_ACTIVE_ASK":
            assert row["tcgplayer_price"] is None and row["ebay_depth_state"] == "SUFFICIENT"


def test_decisions_are_deterministic_and_fingerprints_track_inputs():
    a = pol.decide(tcg(), ebay(), D, NM)
    b = pol.decide(tcg(), ebay(), D, NM)
    assert a == b and len(a["input_fingerprint"]) == 64 and len(a["decision_fingerprint"]) == 64
    changed = pol.decide(tcg(), ebay("28.50"), D, NM)
    assert changed["input_fingerprint"] != a["input_fingerprint"]
    assert changed["decision_fingerprint"] != a["decision_fingerprint"]


def test_shadow_build_is_idempotent_and_order_independent():
    tcg_rows = [tcg(card="c1", variant="v1"), tcg("5.00", card="c2", variant="v2")]
    ebay_rows = [ebay(card="c3", variant="v3"), ebay("5.20", card="c2", variant="v2")]
    first = pol.build_shadow_rows(tcg_rows, ebay_rows, D, NM)
    assert first == pol.build_shadow_rows(list(reversed(tcg_rows)), list(reversed(ebay_rows)), D, NM)
    assert [r["canonical_card_id"] for r in first] == ["c1", "c2", "c3"]
    assert next(r for r in first if r["canonical_card_id"] == "c3")["decision_state"] == "EBAY_ACTIVE_ASK_FALLBACK"


def test_identity_unresolved_cards_are_not_persisted():
    rows = pol.build_shadow_rows([], [ebay(None, depth="INSUFFICIENT", card="c9", variant=None)], D, NM)
    assert rows == []


def test_policy_contract_frozen():
    contract = pol.frozen_contract()
    assert contract["numeric_blend"] is False and contract["ebay_required_depth"] == "SUFFICIENT"
    assert contract["policy_version"] == "pokemon_multi_source_card_price_v1"
    assert len(pol.POLICY_FINGERPRINT) == 64


def test_p4c_estimator_unchanged_replay_fingerprint():
    # P4C freeze document records this replay fingerprint for the frozen estimator.
    assert p4c.replay()["fingerprint"] == "c1f8d1675c7143193e0c0112450215e3a9523a2cbf46aade2fca1e813219c737"


def test_policy_module_never_touches_providers_or_database():
    source = (ROOT / "backend/scripts/pokemon_multi_source_card_price_v1.py").read_text(encoding="utf-8")
    assert not re.search(r"supabase|\.insert\(|\.upsert\(|\.update\(|card_variant_price_(observations|events|current)", source)


def test_migration_is_shadow_only_and_leaves_provider_and_canonical_objects_alone():
    sql = (ROOT / "backend/db/migrations" / MIGRATION).read_text(encoding="utf-8").lower()
    assert sql.count("create table") == 1 and "public.pokemon_multi_source_card_prices_v1" in sql
    for forbidden in ("alter table public.card_variant_price", "insert into public.card_variant_price",
                      "pokemon_canonical_card_market_prices_latest", "create or replace view", "create view",
                      "alter table public.ebay_active_ask", "create or replace function", "grant select on"):
        assert forbidden not in sql
    assert "revoke all on public.pokemon_multi_source_card_prices_v1 from public, anon, authenticated, service_role" in sql
    assert "grant select, insert on public.pokemon_multi_source_card_prices_v1 to service_role" in sql
    assert "anon" not in sql.split("grant select, insert")[1] and "to authenticated" not in sql
    assert "blended" not in sql


def test_migration_trees_byte_identical():
    assert (ROOT / "backend/db/migrations" / MIGRATION).read_bytes() == (ROOT / "supabase/migrations" / MIGRATION).read_bytes()


def test_cohort_price_band_and_status_classification():
    assert [cb.price_band(v) for v in (0.5, 5, 19.99, 20, 50, 100, 249.99, 250, None)] == [
        "lt5", "5_20", "5_20", "20_50", "50_100", "100_250", "100_250", "250_plus", "missing"]
    assert cb.tcg_status(1, 3.0) == "fresh" and cb.tcg_status(2, 3.0) == "stale" and cb.tcg_status(None, None) == "missing"


def test_cohort_selection_is_deterministic_and_respects_exclusions():
    universe = [{"canonical_card_id": f"c{i}", "card_variant_id": f"v{i}", "card_name": "n", "card_number": "1", "set_id": "s", "set_name": "S",
                 "era_id": "e", "era": "E%d" % (i % 3), "rarity": "Rare", "catalog_role": "main", "opening_eligible": True,
                 "set_value_eligible": True, "review_status": "approved", "tcgplayer_market_price": 3.0, "tcgplayer_captured_at": "2026-09-19",
                 "tcgplayer_age_days": 1, "tcg_status": "fresh", "price_band": "lt5", "structure": "rare_holo"} for i in range(12)]
    quotas = {"fresh": {"lt5": 5}}
    first = cb.select_cohort(universe, "2026-09-20", quotas)
    assert first == cb.select_cohort(universe, "2026-09-20", quotas)
    excluded = {first[0]["canonical_card_id"]}
    again = cb.select_cohort(universe, "2026-09-20", quotas, exclude=excluded)
    assert len(again) == 5 and first[0]["canonical_card_id"] not in {r["canonical_card_id"] for r in again}
