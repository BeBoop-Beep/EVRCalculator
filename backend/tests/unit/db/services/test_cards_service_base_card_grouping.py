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
