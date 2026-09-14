from __future__ import annotations

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
ORCHESTRATOR = ROOT / "backend/scripts/run_price_storage_v2_serving_cutover.py"
WRAPPER = ROOT / "backend/scripts/rebuild_snapshots_after_scrape.sh"
PROPOSAL = ROOT / "backend/db/proposals/price_storage_v2_serving_cutover.sql"


class PriceStorageV2ServingCutoverContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.orchestrator = ORCHESTRATOR.read_text(encoding="utf-8")
        cls.wrapper = WRAPPER.read_text(encoding="utf-8")
        cls.wrapper_code = "\n".join(
            line for line in cls.wrapper.splitlines()
            if not line.lstrip().startswith("#")
        )
        cls.sql = PROPOSAL.read_text(encoding="utf-8")

    def test_stage_batches_are_bounded_to_proven_envelope(self):
        self.assertIn("STAGE_BATCH_SIZE = 5", self.orchestrator)
        self.assertIn("stage_price_storage_v2_scoped_values_v2", self.orchestrator)

    def test_every_root_must_stage_before_release_or_publish(self):
        run = self.orchestrator.split("def run(", 1)[1]
        stage = run.index("for batch_number, batch in enumerate")
        whole_cohort_check = run.index("if blocked or set(staged) != set(root_ids)")
        release = run.index("release_enabled = _read_release_gate")
        publish = run.index("ATOMIC_PUBLISH_RPC")
        self.assertLess(stage, whole_cohort_check)
        self.assertLess(whole_cohort_check, release)
        self.assertLess(release, publish)

    def test_public_compatibility_flips_only_after_isolated_cohort_verification(self):
        run = self.orchestrator.split("def run(", 1)[1]
        publish = run.index("ATOMIC_PUBLISH_RPC")
        verify = run.index("isolated = _verify_isolated_cohort")
        finalize = run.index("FINALIZE_RPC")
        receipt = run.index("receipt = _read_receipt")
        self.assertLess(publish, verify)
        self.assertLess(verify, finalize)
        self.assertLess(finalize, receipt)

    def test_scheduler_never_enables_release_gate(self):
        self.assertIn('"releaseGateMutated": False', self.orchestrator)
        self.assertNotIn('"enabled": True', self.orchestrator)
        self.assertNotIn("price_storage_v2_scoped_release_gate SET enabled", self.sql)

    def test_wrapper_runs_v2_before_any_public_snapshot_refresh(self):
        # Compare executable shell commands only. The header intentionally documents
        # refresh_stale_public_snapshots.py before the command body, and comments must
        # never be mistaken for execution order.
        v2 = self.wrapper_code.index("run_price_storage_v2_serving_cutover.py")
        refresh = self.wrapper_code.index("backend/scripts/refresh_stale_public_snapshots.py")
        audit = self.wrapper_code.index("backend/scripts/audit_pokemon_market_publication.py")
        self.assertLess(v2, refresh)
        self.assertLess(refresh, audit)
        between = self.wrapper_code[v2:refresh]
        self.assertIn('if [[ "${V2_STATUS}" -eq 3 ]]; then', between)
        self.assertIn('if [[ "${V2_STATUS}" -ne 0 ]]; then', between)

    def test_atomic_root_writer_never_updates_public_compatibility(self):
        atomic = self.sql.split(
            "CREATE FUNCTION public.publish_price_storage_v2_scoped_run_atomic_v2", 1
        )[1].split(
            "CREATE FUNCTION public.finalize_price_storage_v2_serving_compatibility_v1", 1
        )[0]
        self.assertNotIn("public.pokemon_set_value_daily_history(", atomic)
        self.assertIn("pokemon_member_set_value_daily_history_v2", atomic)
        self.assertIn("pokemon_root_set_value_daily_history_v2", atomic)
        self.assertIn("preview_price_storage_v2_scoped_values_v2", atomic)

    def test_finalizer_is_all_roots_and_receipted(self):
        finalizer = self.sql.split(
            "CREATE FUNCTION public.finalize_price_storage_v2_serving_compatibility_v1", 1
        )[1]
        self.assertIn("p_root_set_ids uuid[]", finalizer)
        self.assertIn("Full root V2 cohort is not complete", finalizer)
        self.assertIn("price_storage_v2_serving_publication_receipts", finalizer)
        self.assertIn("price_storage_v2_serving_compatibility_v1", finalizer)
        self.assertIn("pokemon_set_value_daily_history(", finalizer)

    def test_transition_anchor_prevents_definition_jump_and_preserves_backup(self):
        self.assertIn("DATE '2026-09-08'", self.sql)
        self.assertIn("price_storage_v2_transition_anchor_v1", self.sql)
        self.assertIn("price_storage_v2_legacy_set_value_backup", self.sql)
        self.assertIn("anchor_applied_at", self.sql)

    def test_existing_subset_root_guard_only_whitelists_explicit_v2_provenance(self):
        self.assertIn("guard_canonical_rollout_root_set_value_history_v1", self.sql)
        self.assertIn("price_storage_v2_transition_anchor_v1", self.sql)
        self.assertIn("price_storage_v2_serving_compatibility_v1", self.sql)
        self.assertIn("counts_toward_parent_set_value = true", self.sql)

    def test_no_new_database_cron_is_attached(self):
        self.assertNotIn("cron.schedule", self.sql)
        self.assertNotIn("cron.unschedule", self.sql)
        self.assertIn("schedulerAttached", self.orchestrator)


if __name__ == "__main__":
    unittest.main()
