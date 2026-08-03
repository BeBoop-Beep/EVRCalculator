"""Historical TCGplayer-only catalogs borrow images from reviewed API sets.

They have no Pokemon API identity of their own, so the sync must read images from
their reviewed image-source ids without ever treating those ids as the catalog's
pokemon_api_set_id.
"""

import pytest

from backend.db.services import pokemon_tcg_image_sync_service as sync_module


class _FakeClient:
    def __init__(self, cards_by_set_id=None):
        self._cards_by_set_id = cards_by_set_id or {}
        self.resolved_names = []
        self.requested_set_ids = []

    def resolve_set(self, set_name):
        self.resolved_names.append(set_name)
        return {"id": f"resolved-{set_name}", "name": set_name}

    def iter_cards_for_set(self, api_set_id):
        self.requested_set_ids.append(api_set_id)
        return list(self._cards_by_set_id.get(api_set_id, []))


def _api_card(number, name, api_set_id):
    return {
        "pokemon_tcg_api_id": f"{api_set_id}-{number}",
        "name": name,
        "number": number,
        "image_small_url": f"https://images.pokemontcg.io/{api_set_id}/{number}.png",
        "image_large_url": f"https://images.pokemontcg.io/{api_set_id}/{number}_hires.png",
    }


@pytest.fixture
def wired(monkeypatch):
    """Wire the repository layer to in-memory rows so sync_set can run offline."""

    def _wire(set_row, internal_cards):
        monkeypatch.setattr(sync_module, "get_set_id_by_name", lambda _name: set_row["id"])
        monkeypatch.setattr(
            sync_module, "get_set_by_name",
            lambda _name: type("R", (), {"data": set_row})(),
        )
        monkeypatch.setattr(sync_module, "get_all_cards_for_set", lambda _set_id: internal_cards)
        monkeypatch.setattr(sync_module, "get_card_variants_by_card_ids", lambda _ids: [])

    return _wire


def test_catalog_with_a_reviewed_image_source_reads_from_that_api_set(wired):
    wired(
        {"id": "set-1", "canonical_key": "expedition", "name": "Expedition", "pokemon_api_set_id": None},
        [{"id": "card-1", "name": "Pikachu", "card_number": "1"}],
    )
    client = _FakeClient({"ecard1": [_api_card("1", "Pikachu", "ecard1")]})
    service = sync_module.PokemonTCGImageSyncService(client=client)

    result = service.sync_set("Expedition", dry_run=True)

    assert client.requested_set_ids == ["ecard1"]
    assert client.resolved_names == [], "a reviewed source must not trigger a name search"
    summary = result["api_fetch_summary"]
    assert summary["image_source_api_set_ids"] == ["ecard1"]
    assert summary["image_source_kind"] == "one_to_one_api_match"
    assert summary["api_cards_fetched"] == 1


def test_borrowed_image_source_is_never_reported_as_the_catalog_identity(wired):
    wired(
        {"id": "set-1", "canonical_key": "expedition", "name": "Expedition", "pokemon_api_set_id": None},
        [{"id": "card-1", "name": "Pikachu", "card_number": "1"}],
    )
    service = sync_module.PokemonTCGImageSyncService(
        client=_FakeClient({"ecard1": [_api_card("1", "Pikachu", "ecard1")]})
    )

    summary = service.sync_set("Expedition", dry_run=True)["api_fetch_summary"]

    # ecard1 belongs to eCardEra/expeditionBaseSet; this catalog must not claim it.
    assert summary["pokemon_api_set_id"] is None
    assert summary["image_source_is_borrowed"] is True


def test_multiple_reviewed_image_sources_are_all_fetched_and_merged(wired, monkeypatch):
    monkeypatch.setitem(
        sync_module.catalog_sources.REVIEWED_IMAGE_SOURCES,
        "twoSourceCatalog",
        sync_module.catalog_sources.CatalogImageSource(
            canonical_key="twoSourceCatalog", tcgplayer_set_id="9999",
            tcgplayer_set_name="Two Source Catalog", api_set_ids=("tk1a", "tk1b"),
            match_kind=sync_module.catalog_sources.PARENT_OR_MULTI,
            strategy="test", evidence="test", reviewed_internal_card_count=2,
            reviewed_api_card_count=20,
        ),
    )
    wired(
        {"id": "set-2", "canonical_key": "twoSourceCatalog", "name": "Two Source Catalog",
         "pokemon_api_set_id": None},
        [{"id": "card-1", "name": "Latias", "card_number": "1"}],
    )
    client = _FakeClient({
        "tk1a": [_api_card("1", "Latias", "tk1a")],
        "tk1b": [_api_card("1", "Latios", "tk1b")],
    })
    service = sync_module.PokemonTCGImageSyncService(client=client)

    summary = service.sync_set("Two Source Catalog", dry_run=True)["api_fetch_summary"]

    assert client.requested_set_ids == ["tk1a", "tk1b"]
    assert summary["api_cards_fetched"] == 2
    assert summary["image_source_api_set_ids"] == ["tk1a", "tk1b"]


def test_an_unmapped_catalog_falls_back_to_todays_behavior(wired):
    wired(
        {"id": "set-3", "canonical_key": "battleAcademy", "name": "Battle Academy",
         "pokemon_api_set_id": None},
        [{"id": "card-1", "name": "Pikachu", "card_number": "1"}],
    )
    client = _FakeClient()
    service = sync_module.PokemonTCGImageSyncService(client=client)

    summary = service.sync_set("Battle Academy", dry_run=True)["api_fetch_summary"]

    assert client.resolved_names == ["Battle Academy"]
    assert summary["image_source_api_set_ids"] == []
    assert summary["image_source_is_borrowed"] is False


def test_a_normal_api_backed_set_is_completely_unaffected(wired):
    wired(
        {"id": "set-4", "canonical_key": "surgingSparks", "name": "Surging Sparks",
         "pokemon_api_set_id": "sv8"},
        [{"id": "card-1", "name": "Pikachu ex", "card_number": "1"}],
    )
    client = _FakeClient({"sv8": [_api_card("1", "Pikachu ex", "sv8")]})
    service = sync_module.PokemonTCGImageSyncService(client=client)

    summary = service.sync_set("Surging Sparks", dry_run=True)["api_fetch_summary"]

    assert client.requested_set_ids == ["sv8"]
    assert client.resolved_names == []
    assert summary["pokemon_api_set_id"] == "sv8"
    assert summary["image_source_is_borrowed"] is False
    assert summary["api_set_id_used"] == "sv8"
