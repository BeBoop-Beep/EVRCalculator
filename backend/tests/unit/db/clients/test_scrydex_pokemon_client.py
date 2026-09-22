import json

from backend.db.clients.scrydex_pokemon_client import (
    ScrydexPokemonClient,
    project_card_to_pokemontcg,
    project_expansion_to_pokemontcg,
)


class _Response:
    def __init__(self, payload, status_code=200, headers=None):
        self._payload = payload
        self.status_code = status_code
        self.headers = headers or {}
        self.text = json.dumps(payload)

    def json(self):
        return self._payload


class _Session:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append({
            "url": url,
            "params": dict(params or {}),
            "headers": dict(headers or {}),
            "timeout": timeout,
        })
        return self.responses.pop(0)


def _scrydex_card(card_id="me55-1"):
    return {
        "id": card_id,
        "name": "Bulbasaur",
        "number": "1",
        "printed_number": "001/128",
        "supertype": "Pokémon",
        "subtypes": ["Basic"],
        "rarity": "Common",
        "artist": "Artist",
        "national_pokedex_numbers": [1],
        "images": [{
            "type": "front",
            "small": f"https://images.scrydex.com/pokemon/{card_id}/small",
            "medium": f"https://images.scrydex.com/pokemon/{card_id}/medium",
            "large": f"https://images.scrydex.com/pokemon/{card_id}/large",
        }],
        "expansion": {
            "id": "me55",
            "name": "30th Celebration",
            "series": "Mega Evolution",
            "total": 161,
            "printed_total": 128,
            "release_date": "2026/09/16",
        },
    }


def test_expansion_projection_matches_existing_onboarding_shape():
    row = project_expansion_to_pokemontcg({
        "id": "me55", "name": "30th Celebration", "series": "Mega Evolution",
        "code": "M3", "total": 161, "printed_total": 128,
        "release_date": "2026/09/16",
        "logo": "https://images.scrydex.com/pokemon/me55-logo/logo",
        "symbol": "https://images.scrydex.com/pokemon/me55-symbol/symbol",
    })
    assert row["id"] == "me55"
    assert row["releaseDate"] == "2026-09-16"
    assert row["printedTotal"] == 128
    assert row["total"] == 161
    assert row["images"]["logo"].endswith("/me55-logo/logo")


def test_card_projection_converts_image_array_and_expansion_fields():
    row = project_card_to_pokemontcg(_scrydex_card(), fallback_set_id="me55")
    assert row["id"] == "me55-1"
    assert row["images"]["small"].endswith("/me55-1/small")
    assert row["images"]["large"].endswith("/me55-1/large")
    assert row["set"]["id"] == "me55"
    assert row["set"]["printedTotal"] == 128
    assert row["nationalPokedexNumbers"] == [1]


def test_keyless_cards_fetch_is_paginated_and_normalized_for_image_sync():
    session = _Session([
        _Response({"status": "success", "data": [_scrydex_card("me55-1")], "page": 1, "pageSize": 1, "totalCount": 2}),
        _Response({"status": "success", "data": [_scrydex_card("me55-2")], "page": 2, "pageSize": 1, "totalCount": 2}),
    ])
    sleeps = []
    client = ScrydexPokemonClient(session=session, sleep=sleeps.append)

    # Force a tiny page in the fake by accepting the client's page requests; the
    # response totalCount is authoritative and drives a second request.
    rows = list(client.iter_image_cards_for_set("me55"))

    assert [row["pokemon_tcg_api_id"] for row in rows] == ["me55-1", "me55-2"]
    assert all(row["image_small_url"] for row in rows)
    assert len(session.calls) == 2
    assert "X-Api-Key" not in session.calls[0]["headers"]
    assert "X-Team-ID" not in session.calls[0]["headers"]
    assert sleeps == [2.1]


def test_authenticated_scrydex_requires_and_sends_key_and_team_together():
    session = _Session([
        _Response({"status": "success", "data": [_scrydex_card()], "page": 1, "pageSize": 100, "totalCount": 1}),
    ])
    client = ScrydexPokemonClient(
        api_key="secret",
        team_id="team-1",
        session=session,
        sleep=lambda _delay: None,
    )
    rows = client.fetch_cards_for_set("me55")
    assert len(rows) == 1
    assert session.calls[0]["headers"]["X-Api-Key"] == "secret"
    assert session.calls[0]["headers"]["X-Team-ID"] == "team-1"
