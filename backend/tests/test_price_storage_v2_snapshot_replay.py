from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "price_storage_v2_snapshot_replay_under_test",
    ROOT / "backend/db/services/price_storage_v2_snapshot_replay.py",
)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("snapshot replay helper is unavailable")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

apply_overrides = MODULE.apply_current_standard_root_overrides
ReplayError = MODULE.ScopedSnapshotReplayError
DAY = "2026-09-06"


class SnapshotReplayTests(unittest.TestCase):
    def histories(self):
        return {
            "ordinary": [
                {"set_id":"ordinary","snapshot_date":"2026-09-05","set_value":10},
                {"set_id":"ordinary","snapshot_date":DAY,"set_value":11},
            ],
            "subset-root": [
                {"set_id":"subset-root","snapshot_date":"2026-09-05","set_value":20},
                {"set_id":"subset-root","snapshot_date":DAY,"set_value":21},
            ],
            "unrelated": [
                {"set_id":"unrelated","snapshot_date":DAY,"set_value":99},
            ],
        }

    def test_replaces_only_explicit_current_root_and_preserves_history(self):
        original = self.histories()
        result = apply_overrides(original,[{
            "set_id":"subset-root","snapshot_date":DAY,"value_scope":"standard",
            "set_value":"73.00","source":"price_storage_v2_combined_root_candidate",
        }],market_date=DAY,allowed_set_ids=original)
        self.assertEqual([row["snapshot_date"] for row in result["subset-root"]],["2026-09-05",DAY])
        self.assertEqual(result["subset-root"][-1]["set_value"],"73.00")
        self.assertEqual(result["unrelated"],original["unrelated"])
        self.assertEqual(original["subset-root"][-1]["set_value"],21)

    def test_partial_override_does_not_require_or_modify_other_roots(self):
        original=self.histories()
        result=apply_overrides(original,[{
            "set_id":"ordinary","snapshot_date":DAY,"value_scope":"standard","set_value":11,
        }],market_date=DAY,allowed_set_ids=original)
        self.assertEqual(result["subset-root"],original["subset-root"])
        self.assertEqual(result["unrelated"],original["unrelated"])

    def test_duplicate_root_fails_closed(self):
        row={"set_id":"ordinary","snapshot_date":DAY,"value_scope":"standard","set_value":11}
        with self.assertRaises(ReplayError):
            apply_overrides(self.histories(),[row,row],market_date=DAY,allowed_set_ids=self.histories())

    def test_unknown_subset_or_member_id_fails_closed(self):
        with self.assertRaises(ReplayError):
            apply_overrides(self.histories(),[{
                "set_id":"child-not-a-root","snapshot_date":DAY,"value_scope":"standard","set_value":70,
            }],market_date=DAY,allowed_set_ids=self.histories())

    def test_wrong_date_scope_and_nonpositive_value_fail_closed(self):
        invalid = (
            {"set_id":"ordinary","snapshot_date":"2026-09-05","value_scope":"standard","set_value":11},
            {"set_id":"ordinary","snapshot_date":DAY,"value_scope":"top10","set_value":11},
            {"set_id":"ordinary","snapshot_date":DAY,"value_scope":"standard","set_value":0},
            {"set_id":"ordinary","snapshot_date":DAY,"value_scope":"standard","set_value":None},
        )
        for row in invalid:
            with self.subTest(row=row), self.assertRaises(ReplayError):
                apply_overrides(self.histories(),[row],market_date=DAY,allowed_set_ids=self.histories())

    def test_production_builder_defaults_to_no_override(self):
        source=(ROOT/"backend/scripts/build_pokemon_explore_set_value_snapshot.py").read_text(encoding="utf-8")
        self.assertIn("current_standard_overrides=None",source)
        self.assertIn("if current_standard_overrides is not None:",source)
        self.assertNotIn("PRICE_STORAGE_V2_SCOPED",source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
