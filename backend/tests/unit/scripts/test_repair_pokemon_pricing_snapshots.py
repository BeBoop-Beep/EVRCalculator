from backend.scripts.repair_pokemon_pricing_snapshots import _cards_need_rebuild


def _cards(**overrides):
    stats = {
        "cards": 100,
        "priced": 100,
        "movement7dContracts": 100,
        "movement30dContracts": 100,
    }
    stats.update(overrides)
    return stats


def test_cards_rebuild_when_30d_contracts_are_missing():
    assert _cards_need_rebuild(
        _cards(movement30dContracts=0),
        {"canonical": 100, "selected": 100, "resolvable": 100},
    )


def test_cards_rebuild_when_selected_price_coverage_changed():
    assert _cards_need_rebuild(
        _cards(priced=5, movement7dContracts=5, movement30dContracts=5),
        {"canonical": 100, "selected": 95, "resolvable": 95},
    )


def test_cards_are_healthy_when_card_price_and_movement_contract_counts_match():
    assert not _cards_need_rebuild(
        _cards(),
        {"canonical": 100, "selected": 100, "resolvable": 100},
    )
