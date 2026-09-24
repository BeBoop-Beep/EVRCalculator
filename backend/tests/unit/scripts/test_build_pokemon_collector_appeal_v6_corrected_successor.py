from backend.scripts import build_pokemon_collector_appeal_v6_corrected_successor as subject
from backend.scripts.build_pokemon_collector_appeal_v6_corrected_successor import pokemon_d, trainer_d

def test_frozen_pokemon_d_neutral_and_duplicate_contract():
    base=pokemon_d([90,80,70])[0]
    assert pokemon_d([90,80,70,50])[0] == base
    assert pokemon_d([90,80,70])[0] == base

def test_trainer_headroom_is_positive_and_bounded():
    dp=80;dt=trainer_d([90,75]);lift=(100-dp)*.15*(dt/100)
    assert 0 <= lift <= (100-dp)*.15


def test_live_membership_extension_adds_only_new_approved_root_sets(monkeypatch):
    pages = iter([
        [
            {
                "id": "new-card", "set_id": "new-root", "pokemon_tcg_api_card_id": "api-1",
                "name": "Pikachu", "supertype": "Pokémon", "rarity": "Rare",
                "catalog_role": "main", "opening_eligible": True,
                "canonical_review_status": "approved",
            },
            {
                "id": "subset-card", "set_id": "new-subset", "pokemon_tcg_api_card_id": "api-2",
                "name": "Charizard", "supertype": "Pokémon", "rarity": "Rare",
                "catalog_role": "subset", "opening_eligible": True,
                "canonical_review_status": "approved",
            },
            {
                "id": "frozen-card", "set_id": "frozen-set", "pokemon_tcg_api_card_id": "api-3",
                "name": "Mew", "supertype": "Pokémon", "rarity": "Rare",
                "catalog_role": "main", "opening_eligible": True,
                "canonical_review_status": "approved",
            },
            {
                "id": "old-missing-card", "set_id": "old-missing-root", "pokemon_tcg_api_card_id": "api-4",
                "name": "Lugia", "supertype": "Pokémon", "rarity": "Rare",
                "catalog_role": "main", "opening_eligible": True,
                "canonical_review_status": "approved",
            },
        ],
        [
            {"id": "new-root", "name": "New Root", "release_date": "2026-09-16", "catalog_only": False, "is_subset": False},
            {"id": "new-subset", "name": "New Subset", "release_date": "2026-09-16", "catalog_only": False, "is_subset": True},
            {"id": "frozen-set", "name": "Frozen Set", "release_date": "2026-07-17", "catalog_only": False, "is_subset": False},
            {"id": "old-missing-root", "name": "Old Missing Root", "release_date": "2009-01-01", "catalog_only": False, "is_subset": False},
        ],
        [{"id": 25, "display_name": "Pikachu"}],
        [{
            "pokemon_canonical_card_id": "new-card", "pokemon_reference_id": 25,
            "contribution_weight": 1, "is_hit_eligible": True,
        }],
        [],
        [],
        [],
        [],
    ])
    monkeypatch.setattr(subject, "paged", lambda _factory, size=1000: next(pages))
    monkeypatch.setattr(subject, "trainer_scores", lambda *_a, **_k: {})
    monkeypatch.setattr(subject, "build_playability", lambda *_a, **_k: {})

    rows, names = subject._live_membership_extension_rows(
        object(),
        frozen_set_ids={"frozen-set"},
        trainer_12m_source_run_id="t12",
        trainer_5y_source_run_id="t5",
        playability_source_run_id="play",
    )

    assert [row["canonical_card_id"] for row in rows] == ["new-card"]
    assert rows[0]["subject_type"] == "pokemon"
    assert rows[0]["subject_identity"] == "Pikachu"
    assert rows[0]["hit_eligibility"] is True
    assert rows[0]["membership_extension"] is True
    assert names == {"new-root": "New Root"}
