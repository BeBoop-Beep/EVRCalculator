from backend.db.clients.scrydex_public_artwork_client import ScrydexPublicArtworkClient


class _Response:
    status_code = 200
    headers = {}

    def __init__(self, text):
        self.text = text


class _Session:
    def __init__(self, html):
        self.html = html
        self.calls = []

    def get(self, url, headers=None, timeout=None):
        self.calls.append({"url": url, "headers": dict(headers or {}), "timeout": timeout})
        return _Response(self.html)


def test_public_expansion_page_yields_scrydex_card_ids_and_cdn_artwork():
    html = """
    <html><body>
      <a href="/pokemon/cards/pikachu/me55c-58">Pikachu #58 $30.73</a>
      <a href="/pokemon/cards/m-gardevoir-ex/me55c-106m">M Gardevoir-EX #106 $11.76</a>
      <a href="/pokemon/cards/palkia-lv-x/me55c-106p">Palkia LV.X #106 $13.25</a>
      <a href="/pokemon/cards/shining-celebi/me55c-106">Shining Celebi #106 $47.44</a>
      <a href="/pokemon/cards/pikachu/me55c-58"><img src="https://images.scrydex.com/pokemon/me55c-58/small"></a>
    </body></html>
    """
    session = _Session(html)
    client = ScrydexPublicArtworkClient(session=session, sleep=lambda _delay: None)

    rows = client.fetch_image_cards_for_set(
        set_name="ME: 30th Celebration Classic Collection",
        scrydex_set_id="me55c",
    )

    assert len(rows) == 4
    by_id = {row["pokemon_tcg_api_id"]: row for row in rows}
    assert by_id["me55c-58"]["name"] == "Pikachu"
    assert by_id["me55c-106m"]["name"] == "M Gardevoir EX"
    assert by_id["me55c-106p"]["name"] == "Palkia LV.X"
    assert by_id["me55c-106"]["number"] == "106"
    assert by_id["me55c-58"]["image_small_url"] == "https://images.scrydex.com/pokemon/me55c-58/small"
    assert by_id["me55c-58"]["image_large_url"] == "https://images.scrydex.com/pokemon/me55c-58/large"
    assert session.calls[0]["url"].endswith(
        "/pokemon/expansions/30th-celebration-classic-collection/me55c"
    )


def test_public_artwork_parser_keeps_duplicate_printed_numbers_distinct_by_scrydex_id():
    html = """
    <a href="/pokemon/cards/shining-celebi/me55c-106">Shining Celebi #106</a>
    <a href="/pokemon/cards/m-gardevoir-ex/me55c-106m">M Gardevoir-EX #106</a>
    <a href="/pokemon/cards/palkia-lv-x/me55c-106p">Palkia LV.X #106</a>
    """
    rows = ScrydexPublicArtworkClient(
        session=_Session(html), sleep=lambda _delay: None
    ).fetch_image_cards_for_set(
        set_name="ME: 30th Celebration Classic Collection",
        scrydex_set_id="me55c",
    )

    assert {row["pokemon_tcg_api_id"] for row in rows} == {
        "me55c-106", "me55c-106m", "me55c-106p",
    }
    assert {row["number"] for row in rows} == {"106"}
