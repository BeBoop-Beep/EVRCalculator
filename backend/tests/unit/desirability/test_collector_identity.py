from __future__ import annotations

from backend.desirability.collector_identity import (
    FUNCTIONAL_EXACT_FALLBACK,
    FUNCTIONAL_SIGNATURE,
    TRAINER_COMPOUND,
    TRAINER_EXACT,
    TRAINER_OVERRIDE,
    TRAINER_POSSESSIVE,
    build_functional_identity,
    gameplay_signature,
    match_trainer_subjects,
    normalize_identity_text,
)


def _trainer_entity(entity_id: str, name: str):
    return {
        "id": entity_id,
        "entity_type": "trainer",
        "display_name": name,
        "normalized_name": normalize_identity_text(name),
    }


def _supporter(name: str, card_id: str = "card-1", api_id: str = "sv-test-1"):
    return {
        "id": card_id,
        "pokemon_tcg_api_card_id": api_id,
        "name": name,
        "supertype": "Trainer",
        "subtypes": ["Supporter"],
    }


def test_trainer_exact_name_match():
    matches = match_trainer_subjects(_supporter("Iono"), [_trainer_entity("t-iono", "Iono")])
    assert len(matches) == 1
    assert matches[0].entity_id == "t-iono"
    assert matches[0].method == TRAINER_EXACT
    assert matches[0].confidence == 1.0


def test_trainer_possessive_match_is_boundary_based():
    matches = match_trainer_subjects(
        _supporter("Cynthia's Ambition"),
        [_trainer_entity("t-cynthia", "Cynthia")],
    )
    assert len(matches) == 1
    assert matches[0].entity_id == "t-cynthia"
    assert matches[0].method == TRAINER_POSSESSIVE


def test_generic_supporter_is_not_guessed_from_unrelated_entities():
    matches = match_trainer_subjects(
        _supporter("Professor's Research"),
        [_trainer_entity("t-oak", "Professor Oak"), _trainer_entity("t-sada", "Professor Sada")],
    )
    assert matches == []


def test_boss_orders_is_not_mistaken_for_a_specific_boss():
    matches = match_trainer_subjects(
        _supporter("Boss's Orders"),
        [_trainer_entity("t-giovanni", "Giovanni"), _trainer_entity("t-lysandre", "Lysandre")],
    )
    assert matches == []


def test_compound_supporter_requires_every_part_to_resolve():
    entities = [_trainer_entity("t-cynthia", "Cynthia"), _trainer_entity("t-caitlin", "Caitlin")]
    matches = match_trainer_subjects(_supporter("Cynthia & Caitlin"), entities)
    assert [match.entity_id for match in matches] == ["t-cynthia", "t-caitlin"]
    assert all(match.method == TRAINER_COMPOUND for match in matches)
    assert all(match.contribution_weight == 0.5 for match in matches)

    assert match_trainer_subjects(
        _supporter("Cynthia & Unknown Trainer"),
        entities,
    ) == []


def test_card_specific_override_resolves_ambiguous_supporter_only_when_all_names_exist():
    card = _supporter("Professor's Research", api_id="swsh45-60")
    entities = [_trainer_entity("t-oak", "Professor Oak")]
    matches = match_trainer_subjects(
        card,
        entities,
        card_overrides={"swsh45-60": ["Professor Oak"]},
    )
    assert len(matches) == 1
    assert matches[0].method == TRAINER_OVERRIDE
    assert matches[0].entity_id == "t-oak"

    assert match_trainer_subjects(
        card,
        entities,
        card_overrides={"swsh45-60": ["Professor Sada"]},
    ) == []


def test_non_supporter_never_gets_trainer_subject_link():
    card = {
        "name": "Rare Candy",
        "supertype": "Trainer",
        "subtypes": ["Item"],
    }
    assert match_trainer_subjects(card, [_trainer_entity("t-candy", "Rare Candy")]) == []


def test_trainer_functional_signature_groups_same_gameplay_across_printings():
    base_payload = {
        "name": "Rare Candy",
        "supertype": "Trainer",
        "subtypes": ["Item"],
        "rules": ["Choose 1 of your Basic Pokemon in play. Evolve it."],
        "artist": "Artist A",
        "rarity": "Common",
        "set": {"id": "set-a"},
        "tcgplayer": {"prices": {"normal": {"market": 2.5}}},
    }
    left = {
        "id": "card-a",
        "pokemon_tcg_api_card_id": "seta-1",
        "name": "Rare Candy",
        "supertype": "Trainer",
        "subtypes": ["Item"],
        "rarity": "Common",
        "artist": "Artist A",
        "source_payload": base_payload,
    }
    right = {
        **left,
        "id": "card-b",
        "pokemon_tcg_api_card_id": "setb-99",
        "rarity": "Hyper Rare",
        "artist": "Artist B",
        "source_payload": {
            **base_payload,
            "artist": "Artist B",
            "rarity": "Hyper Rare",
            "set": {"id": "set-b"},
            "tcgplayer": {"prices": {"holofoil": {"market": 95}}},
        },
    }
    left_identity = build_functional_identity(left)
    right_identity = build_functional_identity(right)
    assert left_identity is not None and right_identity is not None
    assert left_identity.method == FUNCTIONAL_SIGNATURE
    assert right_identity.method == FUNCTIONAL_SIGNATURE
    assert left_identity.functional_key == right_identity.functional_key


def test_different_gameplay_text_does_not_merge_same_trainer_name():
    common = {
        "name": "Potion",
        "supertype": "Trainer",
        "subtypes": ["Item"],
    }
    left = {**common, "id": "a", "pokemon_tcg_api_card_id": "old-1", "source_payload": {**common, "rules": ["Heal 20 damage."]}}
    right = {**common, "id": "b", "pokemon_tcg_api_card_id": "new-1", "source_payload": {**common, "rules": ["Heal 30 damage."]}}
    assert build_functional_identity(left).functional_key != build_functional_identity(right).functional_key


def test_missing_gameplay_payload_falls_back_to_exact_card_identity():
    card = {
        "id": "card-a",
        "pokemon_tcg_api_card_id": "xy-123",
        "name": "Rare Candy",
        "supertype": "Trainer",
        "subtypes": ["Item"],
        "source_payload": {},
    }
    identity = build_functional_identity(card)
    assert identity is not None
    assert identity.method == FUNCTIONAL_EXACT_FALLBACK
    assert identity.functional_key.endswith(":xy-123")
    assert identity.confidence < 1.0


def test_energy_is_deliberately_outside_v1_functional_playability_identity():
    card = {
        "id": "energy-1",
        "pokemon_tcg_api_card_id": "energy-1",
        "name": "Fairy Energy",
        "supertype": "Energy",
        "subtypes": ["Basic Energy"],
        "source_payload": {"rules": ["Provides Fairy Energy."]},
    }
    assert build_functional_identity(card) is None


def test_pokemon_signature_uses_gameplay_fields_not_collectible_or_market_fields():
    payload = {
        "name": "Charizard ex",
        "supertype": "Pokemon",
        "subtypes": ["Stage 2", "ex"],
        "hp": "330",
        "types": ["Fire"],
        "abilities": [{"name": "Burning Rule", "type": "Ability", "text": "Once during your turn..."}],
        "attacks": [{"name": "Blaze", "cost": ["Fire", "Fire"], "convertedEnergyCost": 2, "damage": "180", "text": ""}],
        "weaknesses": [{"type": "Water", "value": "x2"}],
        "retreatCost": ["Colorless", "Colorless"],
        "convertedRetreatCost": 2,
        "artist": "Artist A",
        "rarity": "Special Illustration Rare",
        "tcgplayer": {"prices": {"holofoil": {"market": 250}}},
    }
    card = {"name": "Charizard ex", "supertype": "Pokemon", "subtypes": ["Stage 2", "ex"]}
    signature = gameplay_signature(card, payload)
    serialized = str(signature).casefold()
    assert "market" not in serialized
    assert "rarity" not in serialized
    assert "artist a" not in serialized
    assert signature["hp"] == "330"
    assert signature["attacks"][0]["name"] == "blaze"
