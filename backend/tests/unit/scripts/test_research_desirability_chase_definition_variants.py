from __future__ import annotations

from typing import Any, Dict, Sequence

import backend.scripts.research_desirability_chase_definition_variants as research


class FakeRepository:
    def list_v2_rows(self, *, scoring_version: str, hit_policy_version: str, composite_scoring_version: str):
        _ = (scoring_version, hit_policy_version, composite_scoring_version)
        return [
            {
                "set_id": "set-1",
                "set_name": "Canonical Set",
                "set_canonical_key": "canonicalSet",
                "set_desirability_score": 70.0,
                "built_at": "2026-06-01T00:00:00+00:00",
            }
        ]

    def list_latest_rip_rows(self):
        return [
            {
                "set_id": "set-1",
                "set_name": "Canonical Set",
                "canonical_key": "canonicalSet",
                "calculation_run_id": "run-1",
                "run_at": "2026-06-01T00:00:00+00:00",
                "current_market_pack_cost": 5.0,
                "prob_big_hit": 0.25,
                "p95_value_to_cost_ratio": 2.0,
                "hit_ev_per_pack": 1.0,
                "effective_chase_count": 6.0,
                "top1_ev_share": 0.2,
                "top3_ev_share": 0.5,
            }
        ]

    def list_simulation_cards_for_runs(self, run_ids: Sequence[str]):
        assert list(run_ids) == ["run-1"]
        return [
            {
                "calculation_run_id": "run-1",
                "card_id": f"card-{index}",
                "card_variant_id": f"variant-{index}",
                "card_name": f"Pokemon {index}",
                "rarity_bucket": "Rare Holo",
                "price_used": 100 - index,
                "effective_pull_rate": 0.01,
                "ev_contribution": 100 - index,
            }
            for index in range(1, 7)
        ]

    def list_canonical_cards(self, set_ids: Sequence[str]):
        assert list(set_ids) == ["set-1"]
        return [_canonical_card(index) for index in range(1, 7)]

    def list_card_links(self, card_ids: Sequence[str]):
        return [
            {
                "pokemon_canonical_card_id": card_id,
                "pokemon_reference_id": int(str(card_id).split("-")[1]),
                "pokedex_number": int(str(card_id).split("-")[1]),
                "contribution_weight": 1.0,
            }
            for card_id in card_ids
        ]

    def list_composite_scores(self, *, scoring_version: str):
        _ = scoring_version
        return [
            {
                "pokemon_reference_id": index,
                "pokedex_number": index,
                "pokemon_name": f"Pokemon {index}",
                "desirability_score": 50 + index,
            }
            for index in range(1, 7)
        ]

    def list_legacy_cards(self, set_ids: Sequence[str]):
        assert list(set_ids) == ["set-1"]
        return [
            {
                "id": f"legacy-{index}",
                "set_id": "set-1",
                "name": f"Pokemon {index}",
                "card_number": f"{index:03d}/100",
                "pokemon_tcg_api_id": f"api-{index}",
            }
            for index in range(1, 7)
        ]

    def list_card_variants(self, legacy_card_ids: Sequence[str]):
        return [
            {
                "id": f"variant-{index}",
                "card_id": f"legacy-{index}",
                "pokemon_tcg_api_id": f"api-{index}",
            }
            for index in range(1, 7)
            if f"legacy-{index}" in legacy_card_ids
        ]

    def get_near_mint_condition_id(self):
        return "near-mint"

    def list_latest_price_rows(self, variant_ids: Sequence[str], condition_id: str):
        assert condition_id == "near-mint"
        return [
            {
                "variant_id": f"variant-{index}",
                "condition_id": condition_id,
                "market_price": 10.0 + index,
                "source": "test",
                "captured_at": "2026-06-01T00:00:00+00:00",
            }
            for index in range(1, 7)
            if f"variant-{index}" in variant_ids
        ]


def test_card_appeal_correlation_uses_uncapped_canonical_sample():
    report = research.build_audit_report(
        repository=FakeRepository(),
        focus_set_keys=["canonicalSet"],
        scoring_version="v2",
        hit_policy_version="hit",
        composite_scoring_version="comp",
        market_card_limit=2,
        meaningful_share_threshold=0.01,
        max_meaningful_cumulative_share=0.8,
    )

    set_report = report["sets"][0]
    card_appeal = set_report["card_appeal_market_price_correlation"]
    assert len(set_report["market_salient_cards"]) == 2
    assert card_appeal["canonical_count"] == 6
    assert card_appeal["included_count"] == 6
    assert card_appeal["n"] == 6
    assert report["focused"][0]["card_appeal_included_count"] == 6


def _canonical_card(index: int) -> Dict[str, Any]:
    return {
        "id": f"card-{index}",
        "set_id": "set-1",
        "pokemon_tcg_api_card_id": f"api-{index}",
        "name": f"Pokemon {index}",
        "supertype": "Pokemon",
        "subtypes": ["Basic"],
        "rarity": "Common",
        "number": f"{index:03d}",
        "printed_number": f"{index:03d}/100",
        "national_pokedex_numbers": [index],
    }
