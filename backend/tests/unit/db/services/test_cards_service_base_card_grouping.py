"""
Unit tests for CardsService base card grouping fix.

Root cause: grouping by (name, card_number, rarity) produced duplicate base card rows
for pattern-overlay variants (Pokeball / Master Ball) that share (name, card_number)
but carry a different rarity value.

Fix: group by (name, card_number) only; select rarity from the non-pattern upstream row.
"""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch, call

FAKE_SET_ID = "41a0ac1c-27ca-444b-8665-8ba35e583a3b"
FAKE_CARD_ID_1 = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
FAKE_CARD_ID_2 = "ffffffff-eeee-dddd-cccc-bbbbbbbbbbbb"


def _escavalier_rows():
    """Two upstream rows for the same physical card with different rarities."""
    base = {
        "name": "Escavalier",
        "card_number": "060/086",
        "rarity": "uncommon",   # true base-card rarity
        "variant": "",          # empty → base row
        "condition": "Near Mint",
        "printing": "Normal",
        "edition": "",
        "printing_type": "non-holo",
        "pull_rate": None,
        "copies_in_pack": None,
        "source": "TCGPlayer",
        "currency": "USD",
        "prices": {"market": 0.10},
    }
    pokeball = {
        "name": "Escavalier",
        "card_number": "060/086",
        "rarity": "common",     # pattern-overlay rarity (must NOT be used for base card row)
        "variant": "pokeball",  # non-empty → overlay row
        "condition": "Near Mint",
        "printing": "Normal",
        "edition": "",
        "printing_type": "non-holo",
        "pull_rate": None,
        "copies_in_pack": None,
        "source": "TCGPlayer",
        "currency": "USD",
        "prices": {"market": 0.25},
    }
    return [base, pokeball]


def _make_patch_target(name):
    return f"backend.db.services.cards_service.{name}"


class TestBaseCardGrouping(unittest.TestCase):
    """Verify that pattern-variant rows do not create duplicate base card rows."""

    def _make_service(self):
        from backend.db.services.cards_service import CardsService
        service = CardsService()
        # Phase 2 / 3 use multiprocessing internals; stub them out for isolation
        service.divide_work_into_batches = MagicMock(return_value=[])
        service.process_batches_in_parallel = MagicMock(return_value=([], []))
        service.ship_results_sequentially = MagicMock(return_value=(0, 0, []))
        return service

    def test_promo_qualifier_names_normalize_deterministically(self):
        normalize = self._make_service()._normalize_base_card_name

        self.assertEqual(
            normalize("Treecko - 016 (EX Deck Tin)"),
            normalize("Treecko(EX Deck Tin)"),
        )
        self.assertEqual(
            normalize("Treecko - 016 (Target Promo)"),
            normalize("Treecko(Target Promo)"),
        )
        self.assertNotEqual(
            normalize("Treecko - 016 (EX Deck Tin)"),
            normalize("Treecko - 016 (Target Promo)"),
        )

    def test_promo_qualifier_normalization_preserves_trailing_marker(self):
        normalize = self._make_service()._normalize_base_card_name

        self.assertEqual(
            normalize("Grovyle - 004 (e-League) [Winner]"),
            normalize("Grovyle(e-League) [Winner]"),
        )
        self.assertEqual(
            normalize("Grovyle - 004 (e-League) [Winner]"),
            "Grovyle(e-League) [Winner]",
        )

    def test_normal_name_and_trailing_number_behavior_is_unchanged(self):
        normalize = self._make_service()._normalize_base_card_name

        self.assertEqual(normalize("Escavalier"), "Escavalier")
        self.assertEqual(
            normalize("Black Belt's Training - 096/131"),
            "Black Belt's Training",
        )

    @patch(_make_patch_target("insert_cards_batch"))
    @patch(_make_patch_target("get_all_cards_for_set"), return_value=[])
    @patch(_make_patch_target("get_card_set_ids_bulk"), return_value={"base-card": "base-set"})
    @patch(_make_patch_target("get_card_variants_bulk"), return_value=(
        {"base-variant": {"id": "base-variant", "card_id": "base-card",
                          "printing_type": "holo", "special_type": None, "edition": None}},
        {}, 1,
    ))
    @patch(_make_patch_target("get_card_variant_external_identities_bulk"))
    def test_cross_set_identity_fails_before_any_base_card_insert(
        self, mock_identities, _mock_variants, _mock_card_sets, _mock_existing,
        mock_insert_cards,
    ):
        identity_key = (
            "tcgplayer", "42346", "edition=|printing_type=holo|special_type="
        )
        mock_identities.return_value = ({identity_key: {
            "provider": "tcgplayer",
            "external_product_id": "42346",
            "external_variant_key": identity_key[2],
            "card_variant_id": "base-variant",
        }}, 1)
        expedition_card = {
            **_escavalier_rows()[0],
            "name": "Alakazam",
            "card_number": "001/102",
            "tcgplayer_product_id": "42346",
            "external_variant_key": identity_key[2],
        }

        result = self._make_service().insert_cards_with_variants_and_prices(
            "expedition-set", [expedition_card]
        )

        mock_insert_cards.assert_not_called()
        _mock_existing.assert_not_called()
        self.assertEqual(result["inserted_cards"], 0)
        self.assertEqual(result["inserted_variants"], 0)
        self.assertEqual(result["inserted_prices"], 0)
        self.assertEqual(result["external_identities_linked"], 0)
        self.assertEqual(
            result["error_codes"], ["external_variant_identity_conflict"]
        )

    @patch(_make_patch_target("get_card_set_ids_bulk"), return_value={"card-a": "set-a"})
    @patch(_make_patch_target("get_card_variants_bulk"), return_value=(
        {"variant-a": {"id": "variant-a", "card_id": "card-a"}}, {}, 1,
    ))
    @patch(_make_patch_target("get_card_variant_external_identities_bulk"))
    def test_preinsert_validation_allows_existing_same_set_identity(
        self, mock_identities, _mock_variants, _mock_card_sets,
    ):
        key = ("tcgplayer", "1", "edition=|printing_type=holo|special_type=")
        mock_identities.return_value = ({key: {
            "card_variant_id": "variant-a",
        }}, 1)
        self._make_service()._validate_external_identities_before_card_insert(
            "set-a",
            [{"tcgplayer_product_id": "1", "external_variant_key": key[2]}],
        )

    def test_price_write_uses_explicit_scraper_market_date(self):
        service = self._make_service()
        service._conditions_cache = {"Near Mint": "nm-id"}
        row = _escavalier_rows()[0]
        row["_market_date"] = "2026-08-18"
        work, errors = service._prepare_card_data(
            (row["name"], row["card_number"]), FAKE_CARD_ID_1, [row])
        self.assertEqual(errors, [])
        self.assertEqual(work[0][1][0]["captured_at"], "2026-08-18")

    @patch(_make_patch_target("insert_cards_batch"), return_value=[FAKE_CARD_ID_1])
    @patch(_make_patch_target("get_all_cards_for_set"), return_value=[])
    @patch(
        "backend.db.services.orchestrators.data_preparation_orchestrator"
        ".DataPreparationOrchestrator.prepare_data_in_parallel",
        return_value=([], []),
    )
    def test_one_base_card_row_inserted_for_pattern_variants(
        self, _mock_prep, _mock_get_all, mock_insert_batch
    ):
        """Two upstream rows for the same (name, card_number) must produce exactly one
        row in the insert payload, preventing the DB unique-constraint violation."""
        service = self._make_service()
        service.insert_cards_with_variants_and_prices(FAKE_SET_ID, _escavalier_rows())

        mock_insert_batch.assert_called_once()
        payload = mock_insert_batch.call_args[0][0]
        self.assertEqual(
            len(payload), 1,
            f"Expected 1 base card row but got {len(payload)}: {payload}",
        )

    @patch(_make_patch_target("insert_cards_batch"), return_value=[FAKE_CARD_ID_1])
    @patch(_make_patch_target("get_all_cards_for_set"), return_value=[])
    @patch(
        "backend.db.services.orchestrators.data_preparation_orchestrator"
        ".DataPreparationOrchestrator.prepare_data_in_parallel",
        return_value=([], []),
    )
    def test_base_row_rarity_used_not_overlay_rarity(
        self, _mock_prep, _mock_get_all, mock_insert_batch
    ):
        """Rarity in the insert payload must come from the non-variant (base) row,
        not from the Pokeball pattern row whose rarity differs."""
        service = self._make_service()
        service.insert_cards_with_variants_and_prices(FAKE_SET_ID, _escavalier_rows())

        row = mock_insert_batch.call_args[0][0][0]
        self.assertEqual(row["name"], "Escavalier")
        self.assertEqual(row["card_number"], "060/086")
        self.assertEqual(
            row["rarity"], "uncommon",
            f"Expected 'uncommon' (base row rarity) but got '{row['rarity']}'",
        )

    @patch(_make_patch_target("insert_cards_batch"))
    @patch(_make_patch_target("get_all_cards_for_set"), return_value=[])
    @patch(
        "backend.db.services.orchestrators.data_preparation_orchestrator"
        ".DataPreparationOrchestrator.prepare_data_in_parallel",
        return_value=([], []),
    )
    def test_distinct_cards_not_collapsed(
        self, _mock_prep, _mock_get_all, mock_insert_batch
    ):
        """Two genuinely different cards (different card_number) must both appear in the
        insert payload — the fix must not over-collapse distinct physical cards."""
        mock_insert_batch.return_value = [FAKE_CARD_ID_1, FAKE_CARD_ID_2]

        service = self._make_service()
        cards = [
            {
                "name": "Escavalier", "card_number": "060/086", "rarity": "uncommon",
                "variant": "", "condition": "Near Mint", "printing": "Normal",
                "edition": "", "printing_type": "non-holo", "pull_rate": None,
                "copies_in_pack": None, "source": "TCGPlayer", "currency": "USD",
                "prices": {"market": 0.10},
            },
            {
                "name": "Karrablast", "card_number": "061/086", "rarity": "common",
                "variant": "", "condition": "Near Mint", "printing": "Normal",
                "edition": "", "printing_type": "non-holo", "pull_rate": None,
                "copies_in_pack": None, "source": "TCGPlayer", "currency": "USD",
                "prices": {"market": 0.05},
            },
        ]
        service.insert_cards_with_variants_and_prices(FAKE_SET_ID, cards)

        mock_insert_batch.assert_called_once()
        payload = mock_insert_batch.call_args[0][0]
        self.assertEqual(
            len(payload), 2,
            f"Expected 2 distinct base card rows but got {len(payload)}",
        )
        names = {row["name"] for row in payload}
        self.assertEqual(names, {"Escavalier", "Karrablast"})

    @patch(_make_patch_target("insert_cards_batch"), return_value=[FAKE_CARD_ID_1])
    @patch(_make_patch_target("get_all_cards_for_set"), return_value=[])
    @patch(
        "backend.db.services.orchestrators.data_preparation_orchestrator"
        ".DataPreparationOrchestrator.prepare_data_in_parallel",
        return_value=([], []),
    )
    def test_existing_card_not_re_inserted(
        self, _mock_prep, mock_get_all, mock_insert_batch
    ):
        """If a card already exists in the DB it must be reused, not re-inserted."""
        mock_get_all.return_value = [
            {"name": "Escavalier", "card_number": "060/086", "id": FAKE_CARD_ID_1}
        ]

        service = self._make_service()
        service.insert_cards_with_variants_and_prices(FAKE_SET_ID, _escavalier_rows())

        mock_insert_batch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
