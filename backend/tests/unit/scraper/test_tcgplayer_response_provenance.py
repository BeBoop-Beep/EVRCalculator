from types import SimpleNamespace
import hashlib
import importlib
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
        TCGPLAYER_SET_ABBREVIATION="EX",
        TCGPLAYER_EXPECTED_CARD_DENOMINATORS={"165"},
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
    assert report["response_card_denominators_raw"] == ["165"]
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


def test_expedition_rejects_mixed_102_and_165_denominators():
    with pytest.raises(TCGPlayerResponseProvenanceError, match="card denominators"):
        validate_card_response_provenance(
            _config(), {"result": [_row(), _row(number="001/102")]}, _transport()
        )


@pytest.mark.parametrize("raw", ["165", "0165", "00165"])
def test_expedition_numeric_zero_padding_is_equivalent(raw):
    report = validate_card_response_provenance(
        _config(), {"result": [_row(number=f"001/{raw}")]}, _transport()
    )
    assert report["response_card_denominators"] == ["165"]


@pytest.mark.parametrize(
    "raw_values,expected",
    [(["084"], "84"), (["086"], "86"), (["012"], "12"),
     (["073", "73"], "73"), (["083", "83"], "83"),
     (["017", "17"], "17")],
)
def test_numeric_denominator_evidence_is_normalized(raw_values, expected):
    config = SimpleNamespace(CARD_DETAILS_URL=URL, TCGPLAYER_SET_ID="1375")
    rows = [_row(number=f"001/{value}", set=None, setAbbrv=None) for value in raw_values]
    report = validate_card_response_provenance(config, {"result": rows}, _transport())
    assert report["response_card_denominators"] == [expected]
    assert report["response_card_denominators_raw"] == sorted(set(raw_values))


@pytest.mark.parametrize(
    "denominators",
    [["147", "127"], ["25", "102", "110"], ["17", "16"]],
)
def test_configs_without_explicit_contract_allow_legitimate_mixed_numbering(denominators):
    config = SimpleNamespace(
        CARD_DETAILS_URL=URL, TCGPLAYER_SET_ID="1375", PRINTED_TOTAL=147)
    rows = [_row(number=f"001/{value}") for value in denominators]
    report = validate_card_response_provenance(config, {"result": rows}, _transport())
    assert report["response_card_denominators"] == sorted(set(denominators), key=int)


@pytest.mark.parametrize(
    "module_name,class_name",
    [
        ("npEra.nintendoBlackStarPromos", "SetNintendoBlackStarPromosConfig"),
        ("blackAndWhiteEra.bwBlackStarPromos", "SetBwBlackStarPromosConfig"),
        ("heartGoldAndSoulSilverEra.hgssBlackStarPromos", "SetHgssBlackStarPromosConfig"),
        ("xyEra.xyBlackStarPromos", "SetXyBlackStarPromosConfig"),
        ("sunAndMoonEra.smBlackStarPromos", "SetSmBlackStarPromosConfig"),
        ("swordAndShieldEra.celebrationsClassicCollection", "SetCelebrationsClassicCollectionConfig"),
        ("eCardEra.aquapolis", "SetAquapolisConfig"),
        ("exEra.unseenForces", "SetUnseenForcesConfig"),
        ("popEra.popSeries6", "SetPopSeries6Config"),
    ],
)
def test_special_and_promo_configs_do_not_enforce_printed_total(module_name, class_name):
    module = importlib.import_module(f"backend.constants.tcg.pokemon.{module_name}")
    config = getattr(module, class_name)
    group_id = config.CARD_DETAILS_URL.split("/set/", 1)[1].split("/", 1)[0]
    rows = [
        {"productID": 1, "number": "001/102", "setID": group_id},
        {"productID": 2, "number": "002/147", "setID": group_id},
    ]
    report = validate_card_response_provenance(
        config, {"result": rows}, _transport(config.CARD_DETAILS_URL))
    assert report["response_card_denominators"] == ["102", "147"]


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
