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
