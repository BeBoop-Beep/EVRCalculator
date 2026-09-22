from backend.db.clients.scrydex_pokemon_client import ScrydexPokemonClient


class _Response:
    def __init__(self, payload, status_code=200, headers=None):
        self._payload = payload
        self.status_code = status_code
        self.headers = headers or {}

    def json(self):
        return self._payload


class _Session:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.responses.pop(0)


def test_resolve_set_normalizes_me_prefix_and_provider_punctuation():
    session = _Session([
        _Response({
            "data": [{
                "id": "me55c",
                "name": "30th Celebration: Classic Collection",
                "series": "Mega Evolution",
            }]
        })
    ])
    client = ScrydexPokemonClient(
        session=session, max_attempts=1, sleep=lambda _delay: None, jitter=lambda _a, _b: 0.0,
    )

    row = client.resolve_set("ME: 30th Celebration Classic Collection")

    assert row == {"id": "me55c", "name": "30th Celebration: Classic Collection"}
    assert session.calls[0][0].endswith("/en/expansions")


def test_iter_cards_normalizes_front_images_and_pages_to_reported_total():
    session = _Session([
        _Response({
            "data": [{
                "id": "me55-1",
                "name": "Pikachu ex",
                "number": "1",
                "rarity": "Double Rare",
                "artist": "Artist",
                "images": [
                    {"type": "back", "small": "back-small"},
                    {"type": "front", "small": "front-small", "large": "front-large"},
                ],
                "expansion": {"id": "me55", "name": "30th Celebration"},
            }],
            "totalCount": 2,
        }),
        _Response({
            "data": [{
                "id": "me55-2",
                "name": "Mewtwo ex",
                "number": "2",
                "images": [{"type": "front", "small": "two-small", "medium": "two-medium"}],
                "expansion": {"id": "me55", "name": "30th Celebration"},
            }],
            "totalCount": 2,
        }),
    ])
    client = ScrydexPokemonClient(
        session=session, max_attempts=1, sleep=lambda _delay: None, jitter=lambda _a, _b: 0.0,
    )

    rows = list(client.iter_cards_for_set("me55", page_size=1, rate_limit_delay=0))

    assert [row["pokemon_tcg_api_id"] for row in rows] == ["me55-1", "me55-2"]
    assert rows[0]["image_small_url"] == "front-small"
    assert rows[0]["image_large_url"] == "front-large"
    assert rows[1]["image_large_url"] == "two-medium"
    assert all(row["metadata_provider"] == "scrydex" for row in rows)


def test_scrydex_auth_headers_are_optional_and_never_partial():
    unauth = _Session([_Response({"data": [{"id": "x", "name": "X"}]})])
    client = ScrydexPokemonClient(
        api_key="", team_id="", session=unauth, max_attempts=1,
        sleep=lambda _delay: None, jitter=lambda _a, _b: 0.0,
    )
    client.resolve_set("X")
    headers = unauth.calls[0][1]["headers"]
    assert "X-Api-Key" not in headers
    assert "X-Team-ID" not in headers

    auth = _Session([_Response({"data": [{"id": "x", "name": "X"}]})])
    client = ScrydexPokemonClient(
        api_key="secret", team_id="team", session=auth, max_attempts=1,
        sleep=lambda _delay: None, jitter=lambda _a, _b: 0.0,
    )
    client.resolve_set("X")
    headers = auth.calls[0][1]["headers"]
    assert headers["X-Api-Key"] == "secret"
    assert headers["X-Team-ID"] == "team"
