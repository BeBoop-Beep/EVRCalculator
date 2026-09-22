import json

from backend.db.clients.tcgdex_pokemon_client import TCGdexPokemonClient


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

    def get(self, url, headers=None, timeout=None):
        self.calls.append({"url": url, "headers": dict(headers or {}), "timeout": timeout})
        if not self.responses:
            raise AssertionError(f"unexpected extra request: {url}")
        return self.responses.pop(0)


SETS = [
    {"id": "30th", "name": "30th Celebration", "cardCount": {"official": 128, "total": 158}},
    {"id": "30th-c", "name": "30th Classic Collection", "cardCount": {"official": 0, "total": 30}},
    {"id": "cel25cc", "name": "Celebrations Classic Collection", "cardCount": {"official": 25, "total": 25}},
]


def _set_detail(set_id="30th", name="30th Celebration", image=True):
    prefix = "https://assets.tcgdex.net/en/me/30th"
    return {
        "id": set_id,
        "name": name,
        "releaseDate": "2026-09-16",
        "serie": {"id": "me", "name": "Mega Evolution"},
        "cardCount": {"official": 128 if set_id == "30th" else 0, "total": 2},
        "cards": [
            {"id": f"{set_id}-001", "localId": "001", "name": "Exeggcute",
             "image": f"{prefix}/001" if image else None},
            {"id": f"{set_id}-002", "localId": "002", "name": "Alolan Exeggutor",
             "image": f"{prefix}/002" if image else None},
        ],
    }


def test_resolve_set_strips_me_prefix_and_finds_exact_parent():
    session = _Session([_Response(SETS)])
    client = TCGdexPokemonClient(session=session, sleep=lambda _delay: None)

    row = client.resolve_set("ME: 30th Celebration")

    assert row["id"] == "30th"
    assert "X-Api-Key" not in session.calls[0]["headers"]


def test_resolve_set_safely_matches_classic_name_with_extra_celebration_token():
    session = _Session([_Response(SETS)])
    client = TCGdexPokemonClient(session=session, sleep=lambda _delay: None)

    row = client.resolve_set("ME: 30th Celebration Classic Collection")

    assert row["id"] == "30th-c"


def test_image_projection_uses_documented_low_and_high_webp_asset_urls():
    session = _Session([_Response(SETS), _Response(_set_detail())])
    client = TCGdexPokemonClient(session=session, sleep=lambda _delay: None)

    cards = list(client.iter_image_cards_for_set_name("ME: 30th Celebration"))

    assert len(cards) == 2
    assert cards[0]["pokemon_tcg_api_id"] is None
    assert cards[0]["tcgdex_card_id"] == "30th-001"
    assert cards[0]["image_small_url"].endswith("/001/low.webp")
    assert cards[0]["image_large_url"].endswith("/001/high.webp")


def test_image_projection_preserves_complete_rows_when_tcgdex_has_no_artwork():
    session = _Session([
        _Response(SETS),
        _Response(_set_detail(set_id="30th-c", name="30th Classic Collection", image=False)),
    ])
    client = TCGdexPokemonClient(session=session, sleep=lambda _delay: None)

    cards = list(client.iter_image_cards_for_set_name("ME: 30th Celebration Classic Collection"))

    assert len(cards) == 2
    assert cards[0]["image_small_url"] is None
    assert cards[0]["image_large_url"] is None


def test_full_detail_projection_carries_collector_metadata_without_claiming_legacy_api_id():
    detail = _set_detail()
    card1 = {
        "id": "30th-001", "localId": "001", "name": "Exeggcute",
        "image": "https://assets.tcgdex.net/en/me/30th/001",
        "category": "Pokemon", "stage": "Basic", "suffix": None,
        "rarity": "Common", "illustrator": "Nelnal", "dexId": [102],
    }
    card2 = {
        "id": "30th-002", "localId": "002", "name": "Alolan Exeggutor",
        "image": "https://assets.tcgdex.net/en/me/30th/002",
        "category": "Pokemon", "stage": "Stage1", "suffix": "ex",
        "rarity": "Rare", "illustrator": "Artist", "dexId": None,
    }
    session = _Session([
        _Response(SETS), _Response(detail), _Response(card1), _Response(card2),
    ])
    sleeps = []
    client = TCGdexPokemonClient(
        session=session,
        sleep=sleeps.append,
        detail_delay_seconds=0.01,
    )

    rows = client.fetch_card_details_for_set_name("ME: 30th Celebration")

    assert rows[0]["supertype"] == "Pokémon"
    assert rows[0]["subtypes"] == ["Basic"]
    assert rows[0]["artist"] == "Nelnal"
    assert rows[0]["national_pokedex_numbers"] == [102]
    assert rows[0]["source_payload"]["id"] == "30th-001"
    assert rows[1]["subtypes"] == ["Stage1", "ex"]
    assert rows[1]["national_pokedex_numbers"] == []
    assert sleeps == [0.01]
