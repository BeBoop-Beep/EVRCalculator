from types import SimpleNamespace

import backend.db.services.pokemon_post_scrape_card_enrichment as enrichment


class _UpdateQuery:
    def __init__(self, sink, payload):
        self.sink = sink
        self.payload = payload
        self.row_id = None

    def eq(self, field, value):
        assert field == "id"
        self.row_id = value
        return self

    def execute(self):
        self.sink.append((self.row_id, self.payload))
        return SimpleNamespace(data=[{"id": self.row_id}])


class _CanonicalTable:
    def __init__(self, sink):
        self.sink = sink

    def update(self, payload):
        return _UpdateQuery(self.sink, payload)


class _Client:
    def __init__(self):
        self.updates = []

    def table(self, name):
        assert name == "pokemon_canonical_cards"
        return _CanonicalTable(self.updates)


def test_candidate_api_names_normalize_me_prefix_and_classic_collection():
    assert enrichment._candidate_api_names("ME: 30th Celebration") == [
        "ME: 30th Celebration",
        "30th Celebration",
    ]
    assert enrichment._candidate_api_names("ME: 30th Celebration Classic Collection") == [
        "ME: 30th Celebration Classic Collection",
        "30th Celebration Classic Collection",
        "30th Celebration: Classic Collection",
    ]


def test_hydration_updates_existing_fallback_uuid_in_place(monkeypatch):
    client = _Client()
    canonical = {
        "id": "canonical-uuid-stays",
        "set_id": "set-1",
        "pokemon_tcg_api_card_id": "fallback:set-1:1:pikachu",
        "name": "Pikachu",
        "number": "1",
        "printed_number": "001/128",
        "image_small_url": None,
        "image_large_url": None,
        "source": enrichment.FALLBACK_CANONICAL_SOURCE,
        "source_payload": {"source_card_id": "legacy-1"},
    }
    monkeypatch.setattr(enrichment, "_load_canonical_rows", lambda *_a, **_k: [canonical])
    monkeypatch.setattr(
        enrichment,
        "_load_legacy_cards",
        lambda *_a, **_k: {
            "legacy-1": {
                "id": "legacy-1",
                "pokemon_tcg_api_id": "me55-1",
            }
        },
    )
    monkeypatch.setattr(enrichment, "_api_owners", lambda *_a, **_k: {})

    api_card = {
        "id": "me55-1",
        "name": "Pikachu",
        "number": "1",
        "supertype": "Pokémon",
        "subtypes": ["Basic"],
        "rarity": "Common",
        "artist": "Artist",
        "nationalPokedexNumbers": [25],
        "images": {"small": "small.png", "large": "large.png"},
        "set": {"id": "me55"},
    }
    report = enrichment._hydrate_existing_canonical_rows(
        client=client,
        set_id="set-1",
        api_set_id="me55",
        api_set={"id": "me55", "printedTotal": 128},
        api_cards=[api_card],
    )

    assert report["status"] == "hydrated"
    assert report["updated"] == 1
    assert client.updates[0][0] == "canonical-uuid-stays"
    payload = client.updates[0][1]
    assert payload["pokemon_tcg_api_card_id"] == "me55-1"
    assert payload["image_small_url"] == "small.png"
    assert payload["image_large_url"] == "large.png"
    assert payload["source"] == "pokemon_tcg_api"
    assert "set_id" not in payload


def test_complete_canonical_metadata_short_circuits_all_provider_work(monkeypatch):
    rows = [{
        "id": "canonical-1",
        "pokemon_tcg_api_card_id": "me55-1",
        "source": "pokemon_tcg_api",
        "image_small_url": "small.png",
        "image_large_url": "large.png",
    }]
    monkeypatch.setattr(enrichment, "_load_canonical_rows", lambda *_a, **_k: rows)
    monkeypatch.setattr(
        enrichment,
        "_resolve_api_set_id",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("provider should not run")),
    )

    report = enrichment.enrich_scraped_set_card_metadata(
        set_id="set-1",
        set_name="30th Celebration",
        canonical_key="me30thCelebration",
        cards_scraped=158,
        client=object(),
    )
    assert report["status"] == "already_complete"
    assert report["canonical_rows"] == 1


def test_no_cards_skips_without_touching_database():
    report = enrichment.enrich_scraped_set_card_metadata(
        set_id="set-1",
        set_name="Delta Reign",
        canonical_key="me06DeltaReign",
        cards_scraped=0,
        client=object(),
    )
    assert report == {"status": "skipped_no_cards", "cards_scraped": 0}
