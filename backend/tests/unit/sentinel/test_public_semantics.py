from __future__ import annotations

from datetime import datetime, timezone

from backend.sentinel.checks.public_semantics import (
    check_backend_health,
    check_homepage_rankings,
    check_market_public_snapshot,
    check_rankings_lens,
    check_representative_set_page,
    check_tcg_directory,
)
from backend.sentinel.models import CheckOutcome, RunnerIdentity
from backend.sentinel.registry import CheckContext


BASE = "https://api.example.test"
NOW = datetime(2026, 9, 11, 20, 0, tzinfo=timezone.utc)
CTX = CheckContext(
    now=NOW,
    runner_identity=RunnerIdentity(component="sentinel", host="test", build_sha="sha"),
)


class _Response:
    def __init__(self, status_code=200, payload=None, text=None, json_error=None):
        self.status_code = status_code
        self._payload = payload
        self.text = text if text is not None else "{}"
        self._json_error = json_error

    def json(self):
        if self._json_error:
            raise self._json_error
        return self._payload


def _getter(routes):
    calls = []

    def get(url, **kwargs):
        calls.append((url, kwargs))
        response = routes.get(url)
        if isinstance(response, Exception):
            raise response
        if response is None:
            raise AssertionError(f"unexpected URL {url}")
        return response

    get.calls = calls
    return get


def _set_target(set_id="set-1", rank=1, score=91.2):
    return {
        "target_type": "set",
        "target_id": set_id,
        "name": "Test Set",
        "setRipV1": {"rank": rank, "score": score, "tier": "S", "rankable": True},
    }


def _public_set_target(set_id="set-1", rank=1, score=91.2):
    return {
        "target_type": "set",
        "target_id": set_id,
        "name": "Test Set",
        "setRipV1": {"rank": rank, "publicScore": score, "tier": "S", "rankable": True},
    }


def test_backend_health_requires_ok_and_build():
    getter = _getter({f"{BASE}/health": _Response(payload={"status": "ok", "build": "abc123"})})
    result = check_backend_health(CTX, base_url=BASE, http_get=getter)
    assert result.outcome == CheckOutcome.HEALTHY
    assert result.authority_identity == "abc123"
    assert "authorization" not in {k.lower() for k in getter.calls[0][1]["headers"]}
    assert "cookie" not in {k.lower() for k in getter.calls[0][1]["headers"]}


def test_backend_health_200_with_bad_contract_fails():
    getter = _getter({f"{BASE}/health": _Response(payload={"status": "ok", "build": None})})
    result = check_backend_health(CTX, base_url=BASE, http_get=getter)
    assert result.failure_code == "public_backend_health_contract_invalid"


def test_backend_health_network_failure_is_classified():
    getter = _getter({f"{BASE}/health": RuntimeError("network down")})
    result = check_backend_health(CTX, base_url=BASE, http_get=getter)
    assert result.failure_code == "public_backend_unreachable"


def test_market_snapshot_healthy_contract():
    payload = {
        "sets": [
            {"setId": "a", "currentSetValue": 100.0},
            {"setId": "b", "currentSetValue": 50.0},
        ],
        "meta": {"snapshot": {"marketDate": "2026-09-11"}},
    }
    getter = _getter({f"{BASE}/explore/set-value-market": _Response(payload=payload)})
    result = check_market_public_snapshot(CTX, base_url=BASE, http_get=getter)
    assert result.outcome == CheckOutcome.HEALTHY
    assert result.observed["set_count"] == 2


def test_market_snapshot_zero_sets_fails_even_on_200():
    payload = {"sets": [], "meta": {"snapshot": {"marketDate": "2026-09-11"}}}
    getter = _getter({f"{BASE}/explore/set-value-market": _Response(payload=payload)})
    assert check_market_public_snapshot(CTX, base_url=BASE, http_get=getter).failure_code == "public_market_empty"


def test_market_snapshot_missing_date_and_bad_values_fail():
    bad_date = {"sets": [{"setId": "a", "currentSetValue": 100.0}], "meta": {"snapshot": {}}}
    getter = _getter({f"{BASE}/explore/set-value-market": _Response(payload=bad_date)})
    assert check_market_public_snapshot(CTX, base_url=BASE, http_get=getter).failure_code == "public_market_date_missing"

    bad_value = {"sets": [{"setId": "a", "currentSetValue": 0}], "meta": {"snapshot": {"marketDate": "2026-09-11"}}}
    getter = _getter({f"{BASE}/explore/set-value-market": _Response(payload=bad_value)})
    assert check_market_public_snapshot(CTX, base_url=BASE, http_get=getter).failure_code == "public_market_rows_invalid"


def test_homepage_rankings_require_public_rankable_set():
    payload = {"targets": [_set_target()], "meta": {"snapshot": {"builtAt": "2026-09-11T19:00:00Z"}}}
    getter = _getter({f"{BASE}/explore/rankings/homepage-summary?limit=60": _Response(payload=payload)})
    result = check_homepage_rankings(CTX, base_url=BASE, http_get=getter)
    assert result.outcome == CheckOutcome.HEALTHY
    assert result.observed["top_target_id"] == "set-1"


def test_homepage_rankings_empty_or_unrankable_fails():
    payload = {"targets": [{"target_id": "set-1", "name": "Set", "setRipV1": None}], "meta": {}}
    getter = _getter({f"{BASE}/explore/rankings/homepage-summary?limit=60": _Response(payload=payload)})
    assert check_homepage_rankings(CTX, base_url=BASE, http_get=getter).failure_code == "public_homepage_rankings_empty"


def test_sets_rankings_lens_nonempty():
    # The live anonymous/Base sets lens exposes the narrow public contract:
    # publicScore, not the legacy/full-payload score field.
    payload = {"targets": [_public_set_target()], "meta": {"snapshot": {"marketDate": "2026-09-11"}}}
    getter = _getter({f"{BASE}/explore/rankings/lens/sets?limit=60": _Response(payload=payload)})
    result = check_rankings_lens(CTX, base_url=BASE, lens="sets", http_get=getter)
    assert result.outcome == CheckOutcome.HEALTHY
    assert result.observed["row_count"] == 1


def test_eras_rankings_lens_nonempty():
    payload = {"eraSetStrengthV1": {"eras": [{"eraName": "Scarlet & Violet", "rank": 1}]}, "meta": {}}
    getter = _getter({f"{BASE}/explore/rankings/lens/eras?limit=60": _Response(payload=payload)})
    result = check_rankings_lens(CTX, base_url=BASE, lens="eras", http_get=getter)
    assert result.outcome == CheckOutcome.HEALTHY
    assert result.observed["row_count"] == 1


def test_products_rankings_lens_nonempty():
    payload = {
        "productFamilyRankings": {
            "families": {
                "booster_box": {"products": [{"sealedProductId": "p-1", "productName": "Box"}]},
                "elite_trainer_box": {"products": []},
            }
        },
        "meta": {},
    }
    getter = _getter({f"{BASE}/explore/rankings/lens/products?limit=60": _Response(payload=payload)})
    result = check_rankings_lens(CTX, base_url=BASE, lens="products", http_get=getter)
    assert result.outcome == CheckOutcome.HEALTHY
    assert result.observed["row_count"] == 1


def test_each_rankings_lens_fails_when_semantically_empty():
    cases = {
        "sets": {"targets": [], "meta": {}},
        "eras": {"eraSetStrengthV1": {"eras": []}, "meta": {}},
        "products": {"productFamilyRankings": {"families": {"booster_box": {"products": []}}}, "meta": {}},
    }
    for lens, payload in cases.items():
        getter = _getter({f"{BASE}/explore/rankings/lens/{lens}?limit=60": _Response(payload=payload)})
        result = check_rankings_lens(CTX, base_url=BASE, lens=lens, http_get=getter)
        assert result.failure_code == f"public_rankings_{lens}_empty"


def test_tcg_directory_requires_pokemon():
    payload = {"tcgs": [{"id": "1", "name": "Pokémon"}, {"id": "2", "name": "Magic"}]}
    getter = _getter({f"{BASE}/profile/tcgs": _Response(payload=payload)})
    result = check_tcg_directory(CTX, base_url=BASE, http_get=getter)
    assert result.outcome == CheckOutcome.HEALTHY
    assert result.observed["pokemon_present"] is True


def test_tcg_directory_empty_or_missing_pokemon_fails():
    getter = _getter({f"{BASE}/profile/tcgs": _Response(payload={"tcgs": []})})
    assert check_tcg_directory(CTX, base_url=BASE, http_get=getter).failure_code == "public_tcgs_empty"

    getter = _getter({f"{BASE}/profile/tcgs": _Response(payload={"tcgs": [{"name": "Magic"}]})})
    assert check_tcg_directory(CTX, base_url=BASE, http_get=getter).failure_code == "public_tcgs_pokemon_missing"


def test_representative_set_page_uses_current_public_top_ranked_set():
    rankings_url = f"{BASE}/explore/rankings/homepage-summary?limit=60"
    page_url = f"{BASE}/tcgs/pokemon/sets/set-1/page"
    getter = _getter({
        rankings_url: _Response(payload={
            "targets": [
                {"target_type": "set", "target_id": "set-0", "name": "Unranked", "setRipV1": {"rankable": False}},
                _set_target("set-2", rank=2, score=88.0),
                _set_target("set-1", rank=1, score=91.2),
            ],
            "meta": {},
        }),
        page_url: _Response(payload={"target": {"id": "set-1", "target_id": "set-1"}, "set": {}, "meta": {}}),
    })
    result = check_representative_set_page(CTX, base_url=BASE, http_get=getter)
    assert result.outcome == CheckOutcome.HEALTHY
    assert result.observed["set_id"] == "set-1"
    assert [call[0] for call in getter.calls] == [rankings_url, page_url]


def test_representative_set_page_missing_public_identity_fails():
    getter = _getter({
        f"{BASE}/explore/rankings/homepage-summary?limit=60": _Response(payload={"targets": [_set_target()], "meta": {}}),
        f"{BASE}/tcgs/pokemon/sets/set-1/page": _Response(payload={"target": {}, "set": {}, "meta": {}}),
    })
    result = check_representative_set_page(CTX, base_url=BASE, http_get=getter)
    assert result.failure_code == "public_setpage_identity_missing"


def test_non_200_and_non_json_are_not_healthy():
    getter = _getter({f"{BASE}/profile/tcgs": _Response(status_code=503, payload={"message": "down"})})
    assert check_tcg_directory(CTX, base_url=BASE, http_get=getter).failure_code == "public_tcgs_http_error"

    getter = _getter({f"{BASE}/profile/tcgs": _Response(status_code=200, text="not-json", json_error=ValueError("bad json"))})
    assert check_tcg_directory(CTX, base_url=BASE, http_get=getter).failure_code == "public_tcgs_payload_invalid"
