from __future__ import annotations

import io
import json
import urllib.error
from pathlib import Path

import pytest

from backend.pricing_pipeline.pkmnprices_client import PkmnPricesAPIError, PkmnPricesClient
from backend.pricing_pipeline.pkmnprices_credentials import (
    CredentialsUnavailable,
    load_pkmnprices_credentials,
)
from backend.pricing_pipeline.pkmnprices_sold import (
    normalize_sold_listing,
    parse_provider_variant,
    resolve_internal_variant,
)
from backend.pricing_pipeline.pkmnprices_sold_identity import classify_vintage_sold
from backend.pricing_pipeline.pkmnprices_store import _same_evidence, _same_transaction


class Response(io.BytesIO):
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


def opener_for(payloads):
    queue = list(payloads)
    seen = []

    def open_(request, timeout=30):
        seen.append(request)
        return Response(json.dumps(queue.pop(0)).encode())

    open_.seen = seen
    return open_


def test_credentials_precedence_and_redaction(tmp_path, monkeypatch):
    (tmp_path / "backend").mkdir()
    (tmp_path / "frontend").mkdir()
    (tmp_path / "backend/.env").write_text("PKMNPRICES_API_KEY=backend-key\n")
    (tmp_path / "frontend/.env.local").write_text("PKMNPRICES_API_KEY=frontend-key\n")
    c = load_pkmnprices_credentials({"PKMNPRICES_API_KEY": "process-key"}, repo_root=tmp_path)
    assert c.api_key == "process-key"
    assert c.source == "process-environment"
    assert "process-key" not in repr(c)


def test_credentials_fail_closed_without_frontend(tmp_path):
    (tmp_path / "backend").mkdir()
    (tmp_path / "frontend").mkdir()
    (tmp_path / "frontend/.env.local").write_text("PKMNPRICES_API_KEY=frontend-key\n")
    with pytest.raises(CredentialsUnavailable):
        load_pkmnprices_credentials({}, repo_root=tmp_path, allow_frontend_fallback=False)


def test_client_auth_is_header_not_url_and_card_lookup():
    opener = opener_for([{"data": [{"id": 77, "tcg_player_id": 89168}], "pagination": {}}])
    client = PkmnPricesClient("secret-key", opener=opener, sleep=lambda _: None)
    rows = client.cards_by_tcgplayer_id("89168")
    assert rows[0]["id"] == 77
    request = opener.seen[0]
    assert request.get_header("X-api-key") == "secret-key"
    assert "secret-key" not in request.full_url
    assert "tcg_player_id=89168" in request.full_url


def test_card_lookup_by_name_number_does_not_require_set_id():
    opener = opener_for([{
        "data": [{"id": 88, "name": "Mewtwo V", "number": "SWSH229"}],
        "pagination": {},
    }])
    client = PkmnPricesClient("secret-key", opener=opener, sleep=lambda _: None)
    rows = client.cards_by_name_number(name="Mewtwo V", number="SWSH229")
    assert rows[0]["id"] == 88
    url = opener.seen[0].full_url
    assert "name=Mewtwo+V" in url
    assert "number=SWSH229" in url
    assert "set_id=" not in url
    assert "per_page=100" in url




def test_tcgplayer_listings_probe_uses_exact_filters():
    opener = opener_for([{
        "data": [{
            "id": 1,
            "printing": "1st Edition Holofoil",
            "condition": "Near Mint",
            "price": 100,
            "shipping_price": 5,
        }],
        "pagination": {"has_more": False, "next_cursor": None},
    }])
    client = PkmnPricesClient("secret", opener=opener, sleep=lambda _: None)
    payload = client.tcgplayer_listings_page(
        77,
        condition="Near Mint",
        printing="1st Edition Holofoil",
        language="English",
        sort="total_asc",
        limit=1,
    )
    assert payload["data"][0]["printing"] == "1st Edition Holofoil"
    url = opener.seen[0].full_url
    assert "condition=Near+Mint" in url
    assert "printing=1st+Edition+Holofoil" in url
    assert "language=English" in url
    assert "sort=total_asc" in url
    assert "limit=1" in url


def test_cursor_walk_is_bounded_by_item_credit_cap():
    opener = opener_for([
        {"data": [{"id": i} for i in range(20)], "pagination": {"has_more": True, "next_cursor": "a"}},
        {"data": [{"id": 20 + i} for i in range(5)], "pagination": {"has_more": True, "next_cursor": "b"}},
    ])
    client = PkmnPricesClient("secret", opener=opener, sleep=lambda _: None)
    rows = client.ebay_sold(77, max_items=25)
    assert len(rows) == 25
    assert len(opener.seen) == 2
    assert "limit=5" in opener.seen[1].full_url


def test_sold_filters_support_combined_stream_grader_and_grade():
    opener = opener_for([{"data": [], "pagination": {"has_more": False}}])
    client = PkmnPricesClient("secret", opener=opener, sleep=lambda _: None)
    client.ebay_sold_collection(77, graded=None, grader="CGC", grade="10", max_items=20)
    url = opener.seen[0].full_url
    assert "graded=" not in url
    assert "grader=CGC" in url
    assert "grade=10" in url


def test_http_error_does_not_leak_key():
    body = io.BytesIO(json.dumps({"error": {"code": "forbidden", "message": "upgrade"}}).encode())

    def bad(request, timeout=30):
        raise urllib.error.HTTPError(request.full_url, 403, "Forbidden", {}, body)

    client = PkmnPricesClient("top-secret", opener=bad, sleep=lambda _: None)
    with pytest.raises(PkmnPricesAPIError) as exc:
        client.get("/v1/cards")
    assert exc.value.code == "forbidden"
    assert "top-secret" not in str(exc.value)


@pytest.mark.parametrize(
    ("label", "edition", "printing"),
    [
        ("1st Edition Holofoil", "1st-edition", "holo"),
        ("Shadowless", "shadowless", None),
        ("Unlimited Normal", "unlimited", "non-holo"),
        ("Reverse Holofoil", None, "reverse-holo"),
    ],
)
def test_provider_variant_parser(label, edition, printing):
    parsed = parse_provider_variant(label)
    assert parsed["edition"] == edition
    assert parsed["printing_type"] == printing


def test_variant_resolution_fails_closed_when_ambiguous():
    variants = [
        {"id": "a", "edition": "1st-edition", "printing_type": "holo"},
        {"id": "b", "edition": "1st-edition", "printing_type": "non-holo"},
    ]
    assert resolve_internal_variant("1st Edition", variants)["state"] == "AMBIGUOUS"
    exact = resolve_internal_variant("1st Edition Holofoil", variants)
    assert exact == {
        "state": "EXACT",
        "card_variant_id": "a",
        "parsed": {"raw": "1st Edition Holofoil", "edition": "1st-edition", "printing_type": "holo"},
    }


def test_sold_evidence_is_fair_value_signal_eligible_but_never_nm_by_default():
    row = {
        "id": 123,
        "title": "Shining Noctowl 1st Edition",
        "price": 500,
        "currency": "USD",
        "grader": None,
        "grade": None,
        "variant": "1st Edition Holofoil",
        "attribution": "exact",
        "sold_at": "2026-09-20",
        "ingested_at": "2026-09-21T04:00:00Z",
        "listing_url": "https://example.invalid/123",
    }
    out = normalize_sold_listing(
        row,
        provider_card_id=77,
        canonical_card_id="card",
        internal_variants=[{"id": "variant", "edition": "1st-edition", "printing_type": "holo"}],
        collected_at="2026-09-29T00:00:00Z",
    )
    assert out["card_variant_id"] == "variant"
    assert out["fair_value_signal_eligible"] is True
    assert out["set_value_nm_eligible"] is False
    assert out["condition_state"] == "UNKNOWN"


@pytest.mark.parametrize(
    ("grader", "grade", "qualifier"),
    [
        ("CGC", "10", "Pristine"),
        ("CGC", "10", None),
        ("BGS", "10", "Black Label"),
        ("BGS", "10", None),
        ("PSA", "8.5", None),
    ],
)
def test_graded_identity_preserves_qualifier_and_string_grade(grader, grade, qualifier):
    row = {
        "id": 900, "title": "graded card", "price": "100.00", "currency": "USD",
        "grader": grader, "grade": grade, "grade_qualifier": qualifier,
        "variant": "Holofoil", "attribution": "exact", "sold_at": "2026-09-20",
    }
    out = normalize_sold_listing(
        row, provider_card_id=77, canonical_card_id="card",
        internal_variants=[{"id": "variant", "edition": None, "printing_type": "holo"}],
        collected_at="2026-09-29T00:00:00Z",
    )
    assert out["grade"] == grade
    assert isinstance(out["grade"], str)
    assert out["grade_qualifier"] == qualifier
    assert out["graded"] is True
    assert out["fair_value_signal_eligible"] is False
    assert out["set_value_nm_eligible"] is False


def test_grade_qualifier_is_part_of_replay_evidence_identity():
    base = {
        "provider_listing_id": 1, "provider_card_id": 2, "canonical_card_id": "card",
        "title": "Card", "price": "10.00", "currency": "USD", "grader": "CGC",
        "grade": "10", "grade_qualifier": "Pristine", "graded": True,
        "provider_variant": "Holofoil", "attribution": "exact", "sold_at": "2026-09-20",
        "ingested_at": None, "listing_url": None,
    }
    assert _same_evidence(base, dict(base)) is True
    assert _same_evidence(base, dict(base, grade_qualifier=None)) is False


def test_shared_attribution_is_stored_but_not_fair_value_signal_eligible():
    row = {
        "id": 124, "title": "card", "price": 10, "currency": "USD",
        "grader": None, "grade": None, "variant": "Holofoil",
        "attribution": "shared", "sold_at": "2026-09-20",
        "ingested_at": "2026-09-21T04:00:00Z", "listing_url": None,
    }
    out = normalize_sold_listing(
        row,
        provider_card_id=77,
        canonical_card_id="card",
        internal_variants=[{"id": "variant", "edition": None, "printing_type": "holo"}],
        collected_at="2026-09-29T00:00:00Z",
    )
    assert out["fair_value_signal_eligible"] is False
    assert out["exclusion_reason"] == "ATTRIBUTION_SHARED"


def test_client_tracks_provider_credit_headers():
    class HeaderResponse(Response):
        headers = {
            "x-credits-charged": "3",
            "x-credits-limit": "20000",
            "x-rate-remaining": "57",
        }

    def open_(request, timeout=30):
        return HeaderResponse(json.dumps({"data": []}).encode())

    client = PkmnPricesClient("secret", opener=open_, sleep=lambda _: None)
    client.get("/v1/cards")
    assert client.credits_charged == 3
    assert client.credits_limit == 20000
    assert client.rate_remaining == 57


def test_raw_sold_condition_is_never_inferred_from_title():
    row = {
        "id": 125,
        "title": "NM Shining Noctowl 1st Edition",
        "price": 500,
        "currency": "USD",
        "grader": None,
        "grade": None,
        "variant": "1st Edition Holofoil",
        "attribution": "exact",
        "sold_at": "2026-09-20",
        "ingested_at": "2026-09-21T04:00:00Z",
        "listing_url": "https://example.invalid/125",
    }
    out = normalize_sold_listing(
        row,
        provider_card_id=77,
        canonical_card_id="card",
        internal_variants=[
            {"id": "variant", "edition": "1st-edition", "printing_type": "holo"}
        ],
        collected_at="2026-09-29T00:00:00Z",
    )
    assert out["condition_state"] == "UNKNOWN"
    assert out["set_value_nm_eligible"] is False


def _vintage_target(*, edition="1st-edition", variant_id="v1", set_name="Base", number="5/102"):
    return {
        "card_name": "Clefairy",
        "card_number": number,
        "set_name": set_name,
        "gap_variants": [{
            "card_variant_id": variant_id,
            "effective_edition": edition,
            "printing_type": "holo",
        }],
    }


def test_strict_vintage_identity_accepts_explicit_first_edition():
    out = classify_vintage_sold(
        _vintage_target(),
        {
            "title": "Pokemon Clefairy 5/102 Base Set 1st Edition Holo",
            "variant": "Holofoil",
            "attribution": "exact",
            "grader": None,
            "grade": None,
        },
    )
    assert out["state"] == "EXACT"
    assert out["card_variant_id"] == "v1"


def test_strict_vintage_identity_rejects_unlimited_for_first_edition_target():
    out = classify_vintage_sold(
        _vintage_target(),
        {
            "title": "Pokemon Clefairy 5/102 Base Set Unlimited Holo",
            "variant": "Holofoil",
            "attribution": "exact",
            "grader": None,
            "grade": None,
        },
    )
    assert out["state"] == "NO_MATCH"
    assert out["reason"] == "WRONG_EDITION"


def test_strict_vintage_identity_rejects_base_set_2_fraction():
    target = {
        "card_name": "Chansey",
        "card_number": "3/102",
        "set_name": "Base",
        "gap_variants": [{
            "card_variant_id": "shadow",
            "effective_edition": "shadowless",
            "printing_type": "holo",
        }],
    }
    out = classify_vintage_sold(
        target,
        {
            "title": "Chansey Holo Base Set 2 3/130 Shadowless",
            "variant": "Holofoil",
            "attribution": "exact",
            "grader": None,
            "grade": None,
        },
    )
    assert out["state"] == "NO_MATCH"
    assert out["reason"] in {"WRONG_CARD_NUMBER", "WRONG_SET"}


def test_strict_vintage_identity_accepts_explicit_shadowless():
    target = {
        "card_name": "Chansey",
        "card_number": "3/102",
        "set_name": "Base",
        "gap_variants": [{
            "card_variant_id": "shadow",
            "effective_edition": "shadowless",
            "printing_type": "holo",
        }],
    }
    out = classify_vintage_sold(
        target,
        {
            "title": "Pokemon Chansey 3/102 Base Set Shadowless Holo",
            "variant": "Holofoil",
            "attribution": "exact",
            "grader": None,
            "grade": None,
        },
    )
    assert out["state"] == "EXACT"
    assert out["card_variant_id"] == "shadow"


def test_strict_vintage_identity_refuses_missing_edition():
    out = classify_vintage_sold(
        _vintage_target(),
        {
            "title": "Pokemon Clefairy 5/102 Base Set Holo",
            "variant": "Holofoil",
            "attribution": "exact",
            "grader": None,
            "grade": None,
        },
    )
    assert out["state"] == "AMBIGUOUS"
    assert out["reason"] == "EDITION_NOT_EXPLICIT"


def test_sold_collection_reports_resume_cursor():
    opener = opener_for([
        {
            "data": [{"id": 1}],
            "pagination": {"has_more": True, "next_cursor": "next-page"},
        }
    ])
    client = PkmnPricesClient("secret", opener=opener, sleep=lambda _: None)
    result = client.ebay_sold_collection(
        77, max_items=1, initial_cursor="resume-here"
    )
    assert [row["id"] for row in result["rows"]] == [1]
    assert result["has_more"] is True
    assert result["next_cursor"] == "next-page"
    assert "cursor=resume-here" in opener.seen[0].full_url


def test_sold_replay_timestamp_z_and_utc_offset_are_equivalent():
    base = {
        "provider_listing_id": 1,
        "provider_card_id": 2,
        "canonical_card_id": "card",
        "title": "Card",
        "price": "10.00",
        "currency": "USD",
        "grader": None,
        "grade": None,
        "graded": False,
        "provider_variant": "Holofoil",
        "attribution": "exact",
        "sold_at": "2026-09-20",
        "ingested_at": "2026-09-21T02:08:14.188257Z",
        "listing_url": "https://example.invalid/1",
    }
    replay = dict(base, ingested_at="2026-09-21T02:08:14.188257+00:00")
    assert _same_evidence(base, replay) is True


def test_sold_transaction_identity_tolerates_provider_enrichment_drift():
    first = {
        "provider_listing_id": 7,
        "provider_card_id": 8,
        "canonical_card_id": "card",
        "title": "Original title",
        "price": "19.99",
        "currency": "USD",
        "sold_at": "2026-09-23",
    }
    revised = dict(
        first,
        title="Provider-enriched title",
        attribution="exact",
        grader="PSA",
    )
    assert _same_transaction(first, revised) is True
    assert _same_evidence(first, revised) is False


def test_sold_transaction_identity_rejects_price_revision():
    first = {
        "provider_listing_id": 7,
        "provider_card_id": 8,
        "canonical_card_id": "card",
        "price": "19.99",
        "currency": "USD",
        "sold_at": "2026-09-23",
    }
    changed = dict(first, price="29.99")
    assert _same_transaction(first, changed) is False
