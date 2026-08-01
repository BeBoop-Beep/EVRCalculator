"""Safety coverage for the Pokemon TCG image sync service.

The service materialises the whole card iterator before preparing writes. These
tests pin that all-or-nothing contract: a pagination failure must abort before
any repository write, and a complete fetch must still match and update the way
it always has.

Database and HTTP boundaries are mocked; nothing here touches Supabase or the
live Pokemon TCG API.
"""

import pytest

from backend.db.clients.pokemon_tcg_api_client import PokemonTCGAPIError
from backend.db.services import pokemon_tcg_image_sync_service as sync_module
from backend.db.services.pokemon_tcg_image_sync_service import PokemonTCGImageSyncService


INTERNAL_SET_ID = 42


class _FakeClient:
    """Stands in for PokemonTCGAPIClient with a scripted card stream."""

    def __init__(self, cards=None, error=None):
        self._cards = cards or []
        self._error = error
        self.iter_calls = 0

    def resolve_set(self, set_name):  # pragma: no cover - not used, api id is preloaded
        return {"id": "me5", "name": set_name}

    def iter_cards_for_set(self, set_id, **_kwargs):
        self.iter_calls += 1
        for card in self._cards:
            yield card
        if self._error is not None:
            raise self._error


def _api_card(number, name, card_id=None):
    return {
        "pokemon_tcg_api_id": card_id or f"me5-{number}",
        "set_id": "me5",
        "set_name": "Pitch Black",
        "number": str(number),
        "name": name,
        "image_small_url": f"https://images.example/me5-{number}/small",
        "image_large_url": f"https://images.example/me5-{number}/large",
    }


def _internal_card(card_id, number, name):
    return {
        "id": card_id,
        "set_id": INTERNAL_SET_ID,
        "name": name,
        "rarity": "Common",
        "card_number": str(number),
        "image_small_url": None,
        "image_large_url": None,
        "pokemon_tcg_api_id": None,
        "image_last_synced_at": None,
    }


def _variant(variant_id, card_id, printing_type="Normal", special_type=None):
    return {
        "id": variant_id,
        "card_id": card_id,
        "pokemon_tcg_api_id": None,
        "printing_type": printing_type,
        "special_type": special_type,
        "edition": None,
        "image_small_url": None,
        "image_large_url": None,
    }


class _Recorder:
    """Records repository write calls so tests can assert they never happened."""

    def __init__(self):
        self.card_update_batches = []
        self.variant_update_batches = []

    def update_cards(self, updates):
        self.card_update_batches.append(updates)
        return len(updates)

    def update_variants(self, updates):
        self.variant_update_batches.append(updates)
        return len(updates)


@pytest.fixture
def wiring(monkeypatch):
    """Patch every DB boundary the service touches; return the write recorder."""
    recorder = _Recorder()

    internal_cards = [
        _internal_card(1, 1, "Tropius"),
        _internal_card(2, 2, "Pikachu"),
        _internal_card(3, 2, "Pikachu - Master Ball Pattern"),
    ]
    variants = [
        _variant(101, 1),
        _variant(102, 2),
        _variant(103, 3, special_type="master ball"),
    ]

    monkeypatch.setattr(sync_module, "get_set_id_by_name", lambda _name: INTERNAL_SET_ID)
    monkeypatch.setattr(
        sync_module,
        "get_set_by_name",
        lambda _name: type("Res", (), {"data": {"pokemon_api_set_id": "me5"}})(),
    )
    monkeypatch.setattr(sync_module, "get_all_cards_for_set", lambda _sid: internal_cards)
    monkeypatch.setattr(sync_module, "get_card_variants_by_card_ids", lambda _ids: variants)
    monkeypatch.setattr(sync_module, "update_card_image_sync_fields_batch", recorder.update_cards)
    monkeypatch.setattr(sync_module, "update_card_variant_image_sync_fields_batch", recorder.update_variants)

    return recorder


def test_pagination_failure_writes_nothing(wiring):
    """An incomplete fetch must abort before any card or variant row is touched."""
    incomplete = PokemonTCGAPIError(
        "Could not fetch all cards for set 'me5': 100/120 unique cards",
        path="/cards",
        retryable=True,
    )
    client = _FakeClient(cards=[_api_card(1, "Tropius")], error=incomplete)
    service = PokemonTCGImageSyncService(client=client)

    with pytest.raises(PokemonTCGAPIError):
        service.sync_set(set_name="Pitch Black", dry_run=False)

    assert wiring.card_update_batches == [], "no card writes may occur on an incomplete fetch"
    assert wiring.variant_update_batches == [], "no variant writes may occur on an incomplete fetch"


def test_dry_run_prepares_updates_but_writes_nothing(wiring):
    client = _FakeClient(cards=[_api_card(1, "Tropius"), _api_card(2, "Pikachu")])
    service = PokemonTCGImageSyncService(client=client)

    result = service.sync_set(set_name="Pitch Black", dry_run=True)

    assert result["fetched_api_cards"] == 2
    assert result["prepared_card_updates"] > 0
    assert result["updated_card_rows"] == 0
    assert result["updated_variant_rows"] == 0
    assert wiring.card_update_batches == []
    assert wiring.variant_update_batches == []


def test_complete_fetch_preserves_existing_matching_behavior(wiring):
    """Exact number+name matching plus the parallel-row supplement are unchanged."""
    client = _FakeClient(cards=[_api_card(1, "Tropius"), _api_card(2, "Pikachu")])
    service = PokemonTCGImageSyncService(client=client)

    result = service.sync_set(set_name="Pitch Black", dry_run=False)

    assert result["fetched_api_cards"] == 2
    summary = result["card_matching_summary"]
    # Counts internal rows matched, not API cards: Tropius + Pikachu base +
    # the Pikachu parallel row that the supplement pulls in.
    assert summary["cards_matched_by_number_name"] == 3
    # "Pikachu - Master Ball Pattern" is picked up as a duplicate/parallel row.
    assert summary["cards_matched_duplicate_parallel_rows"] == 1
    assert summary["cards_unmatched"] == 0
    assert summary["cards_ambiguous"] == 0

    # All three internal cards receive card-level image URLs.
    assert len(wiring.card_update_batches) == 1
    card_updates = {u["card_id"]: u for u in wiring.card_update_batches[0]}
    assert set(card_updates) == {1, 2, 3}
    assert card_updates[1]["image_small_url"] == "https://images.example/me5-1/small"
    assert card_updates[3]["image_large_url"] == "https://images.example/me5-2/large"

    # All three variants receive image URLs.
    assert len(wiring.variant_update_batches) == 1
    variant_updates = {u["card_id"]: u for u in wiring.variant_update_batches[0]}
    assert set(variant_updates) == {101, 102, 103}
    assert variant_updates[101]["image_small_url"] == "https://images.example/me5-1/small"

    # The image-only master ball variant must not inherit the API id.
    assert "pokemon_tcg_api_id" not in variant_updates[103]
    assert variant_updates[102]["pokemon_tcg_api_id"] == "me5-2"
