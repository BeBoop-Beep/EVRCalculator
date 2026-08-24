from types import SimpleNamespace
import hashlib
import json

import pytest

from backend.Scraper.services.orchestrators.tcg_player_orchestrator import (
    TCGScraper,
    TCGPlayerResponseProvenanceError,
    validate_card_response_provenance,
)
from backend.Scraper.clients.tcgplayer_client import TCGPlayerClient


URL = "https://infinite-api.tcgplayer.com/priceguide/set/1375/cards/?rows=5000&productTypeID=1"


def _config():
    return SimpleNamespace(
        CARD_DETAILS_URL=URL,
        TCGPLAYER_SET_ID="1375",
        TCGPLAYER_SET_NAME="Expedition",
        SET_ABBREVIATION="EX",
        PRINTED_TOTAL=165,
    )


def _row(**overrides):
    row = {
        "productID": 85123,
        "productName": "Alakazam",
        "number": "001/165",
        "setID": 1375,
        "set": "Expedition",
        "setAbbrv": "EX",
    }
    row.update(overrides)
    return row


def _transport(final_url=URL):
    return {
        "requested_url": URL,
        "final_url": final_url,
        "redirect_history": [],
        "response_body_sha256": "abc123",
    }


def test_expedition_provenance_passes_for_group_1375_ex_and_165():
    report = validate_card_response_provenance(
        _config(), {"result": [_row()]}, _transport()
    )
    assert report["requested_group_id"] == "1375"
    assert report["response_set_ids"] == ["1375"]
    assert report["response_set_labels"] == ["Expedition"]
    assert report["response_abbreviations"] == ["EX"]
    assert report["response_card_denominators"] == ["165"]
    assert report["representative_products"][0]["productID"] == 85123
    assert report["response_body_sha256"] == "abc123"


@pytest.mark.parametrize(
    "row,needle",
    [
        (_row(setID=604), "response set IDs"),
        (_row(set="Base Set", setAbbrv="BS"), "response set labels"),
        (_row(number="001/102"), "card denominators"),
    ],
)
def test_expedition_provenance_rejects_present_contradictions(row, needle):
    with pytest.raises(TCGPlayerResponseProvenanceError, match=needle):
        validate_card_response_provenance(_config(), {"result": [row]}, _transport())


def test_expedition_provenance_rejects_mixed_response_identity():
    with pytest.raises(TCGPlayerResponseProvenanceError, match="mixed response"):
        validate_card_response_provenance(
            _config(), {"result": [_row(), _row(setID=604, set="Base Set", setAbbrv="BS")]},
            _transport(),
        )


def test_expedition_provenance_rejects_redirect_to_different_group():
    final_url = "https://infinite-api.tcgplayer.com/priceguide/set/604/cards/?productTypeID=1"
    with pytest.raises(TCGPlayerResponseProvenanceError, match="final response group 604"):
        validate_card_response_provenance(
            _config(), {"result": [_row()]}, _transport(final_url)
        )


def test_omitted_upstream_fields_are_not_required():
    row = {"productID": 85123, "productName": "Alakazam", "number": "001"}
    report = validate_card_response_provenance(
        _config(), {"result": [row]}, _transport()
    )
    assert report["response_set_ids"] == []
    assert report["response_card_denominators"] == []


def test_http_client_preserves_final_url_redirects_and_body_hash(monkeypatch):
    body = {"result": [_row()]}
    redirect = SimpleNamespace(
        status_code=302,
        url=URL,
        headers={"Location": URL},
    )
    response = SimpleNamespace(
        status_code=200,
        url=URL,
        history=[redirect],
        headers={"Content-Type": "application/json"},
        json=lambda: body,
        text="",
    )
    client = TCGPlayerClient()
    client.request_delay_min = client.request_delay_max = 0
    monkeypatch.setattr(client.session, "request", lambda **_kwargs: response)

    assert client.fetch_price_data(URL) == body
    expected_hash = hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    assert client.last_response_provenance == {
        "requested_url": URL,
        "final_url": URL,
        "redirect_history": [{"status_code": 302, "url": URL, "location": URL}],
        "response_body_sha256": expected_hash,
    }


def test_base_response_fails_before_dto_or_ingest_controller():
    class Client:
        last_response_provenance = _transport()

        def fetch_price_data(self, _url):
            return {"result": [_row(
                productID=42346, number="001/102", setID=604,
                set="Base Set", setAbbrv="BS",
            )]}

    class IngestController:
        calls = 0

        def ingest(self, _payload):
            self.calls += 1
            raise AssertionError("ingestion must not be reached")

    scraper = TCGScraper(enable_db_ingestion=False, target_market_date="2026-08-23")
    scraper.enable_db_ingestion = True
    scraper.client = Client()
    scraper.ingest_controller = IngestController()

    with pytest.raises(TCGPlayerResponseProvenanceError):
        scraper.scrape(_config(), "unused.xlsx")
    assert scraper.ingest_controller.calls == 0
