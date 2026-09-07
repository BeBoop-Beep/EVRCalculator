"""Hermetic scope contracts and the extracted production index math.

The SQL proposal is not executed here. These are not production E2E assertions.
AST-loading isolates the pure production builder from network-client imports.
"""
from __future__ import annotations
import ast
from copy import deepcopy
from datetime import date
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from typing import Any, Mapping, Sequence
import unittest

from backend.db.services.price_storage_v2_integration import (
    MEMBER_RPC, ROOT_RPC, ScopeContractError, ScopedRun, amount, compare_index_outputs,
    market_day, public_root_materialization, publish_isolated_run, root_source_rows,
)
from backend.scripts.reconcile_price_storage_v2_migrations import (
    plan_files, validate_export, write_plan,
)

ROOT = Path(__file__).resolve().parents[1]
DAY = "2026-09-06"


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()


def load_functions(path, names, extras=None):
    source = ast.parse(path.read_text(encoding="utf-8"))
    chosen = [node for node in source.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names]
    if len(chosen) != len(names):
        raise AssertionError("production helper not found")
    tree = ast.Module(body=chosen, type_ignores=[])
    env = dict(Any=Any, Mapping=Mapping, Sequence=Sequence, INDEX_KEYS=("raw", "top10"),
               RAW_INDEX_KEY="raw", MARKET_INDEX_CONTRACT_VERSION="pokemon-market-index-v1",
               MARKET_INDEX_METHODOLOGY_VERSION="chain_linked_common_cohort_v1",
               deterministic_fingerprint=fingerprint)
    env.update(extras or {})
    exec(compile(tree, str(path), "exec"), env)
    return env


math_env = load_functions(ROOT / "db/services/pokemon_market_rollout_index.py",
                         {"_previous_constituents", "build_rollout_index_from_inputs"})
build_index = math_env["build_rollout_index_from_inputs"]


def accepted_preview(root="cz", members=("cz", "gg")):
    evidence = [{"set_id": member, "source_ready": True, "job_status": "completed", "shadow_status": "complete",
                 "source_completed_at": "2026-09-06T18:00:00Z", "shadow_source_completed_at": "2026-09-06T18:00:00Z"}
                for member in members]
    vals = [{"universe_scope": "root", "set_id": root, "market_scope": "standard", "value_scope": scope,
             "set_value": value, "priced_card_count": count, "expected_card_count": count}
            for scope, value, count in (("standard", "2634.47", 230), ("hits", "2466.72", 107), ("top10", "1432.66", 10))]
    vals.append(dict(vals[0], universe_scope="member", set_value="254.87", priced_card_count=160, expected_card_count=160))
    return {"status": "parity_passed", "publication_authorized": False,
            "context": {"root_set_id": root, "market_date": DAY, "member_set_ids": list(members), "source_evidence": evidence},
            "comparison": {name: 0 for name in ("raw_only_rows", "v2_only_rows", "duplicate_raw_keys", "duplicate_v2_keys",
                           "live_root_only_rows", "proposed_root_only_rows", "missing_prices", "needs_review_cards")},
            "candidate_values": vals}


def root_rows(root="cz"):
    return [{"set_id": root, "snapshot_date": DAY, "value_scope": scope,
             "source": f"canonical_root_{kind}_public_rollout_v1"}
            for scope, kind in (("standard", "set"), ("top10", "top10"))]


class MaterializationTests(unittest.TestCase):
    def test_valid_public_root_pairs(self):
        self.assertTrue(public_root_materialization(["cz"], root_rows(), DAY)["ready"])

    def test_member_rows_do_not_certify_combined_root(self):
        rows = [dict(r, source="card_variant_price_observations_near_mint_latest_as_of_day:standard:canonical_checklist") for r in root_rows()]
        self.assertFalse(public_root_materialization(["cz"], rows, DAY)["ready"])

    def test_generic_rollout_does_not_expand_public_cohort(self):
        rows = [dict(r, source=r["source"].replace("_public", "")) for r in root_rows()]
        self.assertFalse(public_root_materialization(["cz"], rows, DAY)["ready"])

    def test_wrong_date_and_missing_scope(self):
        self.assertFalse(public_root_materialization(["cz"], root_rows()[:1], DAY)["ready"])
        self.assertFalse(public_root_materialization(["cz"], [dict(r, snapshot_date="2026-09-05") for r in root_rows()], DAY)["ready"])

    def test_duplicate_rejected_and_unrelated_root_ignored(self):
        self.assertFalse(public_root_materialization(["cz"], root_rows() + root_rows()[:1], DAY)["ready"])
        self.assertFalse(public_root_materialization(["other"], root_rows(), DAY)["ready"])

    def test_empty_public_rollout_is_noop(self):
        self.assertTrue(public_root_materialization([], [], DAY)["ready"])


class PreviewTests(unittest.TestCase):
    def test_combined_root_is_not_member_price(self):
        rows = root_source_rows(accepted_preview(), "cz", DAY)
        self.assertEqual(next(r for r in rows if r["value_scope"] == "standard")["set_value"], "2634.47")

    def test_blocked_source_rejected(self):
        p = accepted_preview(); p["status"] = "blocked"
        with self.assertRaises(ScopeContractError): root_source_rows(p, "cz", DAY)

    def test_superseded_source_receipt_rejected(self):
        p = accepted_preview(); p["context"]["source_evidence"][0]["shadow_source_completed_at"] = "2026-09-05T18:00:00Z"
        with self.assertRaises(ScopeContractError): root_source_rows(p, "cz", DAY)

    def test_missing_subset_receipt_rejected(self):
        p = accepted_preview(); p["context"]["source_evidence"].pop()
        with self.assertRaises(ScopeContractError): root_source_rows(p, "cz", DAY)

    def test_duplicate_subset_receipt_rejected(self):
        p = accepted_preview(); p["context"]["source_evidence"].append(p["context"]["source_evidence"][0])
        with self.assertRaises(ScopeContractError): root_source_rows(p, "cz", DAY)

    def test_wrong_root_or_date_rejected(self):
        for root, day in (("other", DAY), ("cz", "2026-09-05")):
            with self.subTest(root=root, day=day), self.assertRaises(ScopeContractError): root_source_rows(accepted_preview(), root, day)

    def test_missing_comparison_field_rejected(self):
        p = accepted_preview(); p["comparison"].pop("missing_prices")
        with self.assertRaises(ScopeContractError): root_source_rows(p, "cz", DAY)

    def test_mismatch_or_boolean_zero_rejected(self):
        for value in (1, False):
            p = accepted_preview(); p["comparison"]["raw_only_rows"] = value
            with self.subTest(value=value), self.assertRaises(ScopeContractError): root_source_rows(p, "cz", DAY)

    def test_duplicate_root_scope_rejected(self):
        p = accepted_preview(); p["candidate_values"].append(p["candidate_values"][0])
        with self.assertRaises(ScopeContractError): root_source_rows(p, "cz", DAY)

    def test_missing_price_is_not_zero(self):
        p = accepted_preview(); p["candidate_values"][0]["set_value"] = None
        with self.assertRaises(ScopeContractError): root_source_rows(p, "cz", DAY)

    def test_empty_hits_remains_null_not_zero(self):
        p = accepted_preview(); p["candidate_values"][1].update(set_value=None, expected_card_count=0, priced_card_count=0)
        rows = root_source_rows(p, "cz", DAY)
        self.assertIsNone(next(r for r in rows if r["value_scope"] == "hits")["set_value"])

    def test_invalid_numeric_and_dates(self):
        for value in (None, True, "NaN", "Infinity", -1, "garbage"):
            with self.subTest(value=value), self.assertRaises(ScopeContractError): amount(value)
        for day in ("2026-09-06T00:00:00Z", "2026-02-30", None):
            with self.subTest(day=day), self.assertRaises(ScopeContractError): market_day(day)


class WriterTests(unittest.TestCase):
    def client(self):
        class Client:
            def __init__(self): self.calls = []
            def rpc(self, rpc, args):
                self.calls.append((rpc, args))
                return SimpleNamespace(execute=lambda: SimpleNamespace(data={"status": "complete"}))
        return Client()

    def test_default_dry_run_never_calls_rpc(self):
        c = self.client(); result = publish_isolated_run(c, ScopedRun(1, "cz", DAY))
        self.assertEqual(c.calls, []); self.assertEqual(result["writes"], 0)

    def test_member_then_root_separate_destinations(self):
        c = self.client(); publish_isolated_run(c, ScopedRun(1, "cz", DAY), commit=True)
        self.assertEqual([r for r, _ in c.calls], [MEMBER_RPC, ROOT_RPC])
        self.assertTrue(all(args["p_root_set_id"] == "cz" for _, args in c.calls))

    def test_reverse_order_same_scopes(self):
        c = self.client(); publish_isolated_run(c, ScopedRun(1, "cz", DAY), commit=True, order=("root", "member"))
        self.assertEqual([r for r, _ in c.calls], [ROOT_RPC, MEMBER_RPC])

    def test_duplicate_scope_order_rejected_before_writes(self):
        c = self.client()
        with self.assertRaises(ScopeContractError): publish_isolated_run(c, ScopedRun(1, "cz", DAY), commit=True, order=("root", "root"))
        self.assertEqual(c.calls, [])

    def test_failed_rpc_is_not_success(self):
        c = SimpleNamespace(rpc=lambda *_: SimpleNamespace(execute=lambda: SimpleNamespace(data={"status": "blocked"})))
        with self.assertRaises(ScopeContractError): publish_isolated_run(c, ScopedRun(1, "cz", DAY), commit=True)


class ProductionMathTests(unittest.TestCase):
    def fixture(self):
        sets = [{"id": key, "canonical_key": key} for key in ("es", "cz", "celebrations")]
        rows = [{"set_id": key, "snapshot_date": DAY, "value_scope": scope,
                 "set_value": val, "priced_card_count": 10 if scope == "top10" else count,
                 "source": "baseline", "updated_at": "2026-09-06T20:00:00Z"}
                for key, val, count in (("es", 1000, 237), ("cz", 2634.47, 230), ("celebrations", 624.16, 50))
                for scope in ("standard", "top10")]
        previous = {scope: {"market_date": "2026-09-05", "normalized_index_value": 110,
                           "constituents_json": [{"setId": key, "setValue": 900} for key in ("es", "cz", "celebrations")]}
                    for scope in ("raw", "top10")}
        return dict(market_date=DAY, sets=sets, source_rows=rows, previous=previous, transition_ids=[])

    def test_same_inputs_identical_index_payloads(self):
        args = self.fixture(); self.assertEqual(build_index(**args), build_index(**deepcopy(args)))

    def test_provenance_only_change_is_reported_but_economically_equal(self):
        args = self.fixture(); baseline = build_index(**args)
        for row in args["source_rows"]: row.update(source="v2", updated_at=None)
        proposed = build_index(**args)
        self.assertNotEqual(baseline[0]["source_generation_fingerprint"], proposed[0]["source_generation_fingerprint"])
        self.assertEqual(compare_index_outputs(baseline, proposed)["status"], "pass")

    def test_member_only_crown_zenith_fails_index_comparison(self):
        args = self.fixture(); baseline = build_index(**args)
        next(r for r in args["source_rows"] if r["set_id"] == "cz" and r["value_scope"] == "standard").update(set_value=254.87, priced_card_count=160)
        self.assertEqual(compare_index_outputs(baseline, build_index(**args))["status"], "blocked")

    def test_coverage_change_is_not_ignored(self):
        args = self.fixture(); baseline = build_index(**args)
        args["source_rows"][0]["priced_card_count"] -= 1
        self.assertEqual(compare_index_outputs(baseline, build_index(**args))["status"], "blocked")

    def test_rollout_neutralization_is_preserved(self):
        args = self.fixture(); args["transition_ids"] = ["cz"]
        rows = build_index(**args)
        self.assertEqual(rows[0]["diagnostics_json"]["commonSetIds"], ["celebrations", "es"])
        self.assertAlmostEqual(rows[0]["daily_return"], (1000 + 624.16) / 1800 - 1)

    def test_duplicate_or_wrong_date_source_rejected(self):
        args = self.fixture(); args["source_rows"].append(dict(args["source_rows"][0]))
        with self.assertRaises(RuntimeError): build_index(**args)
        args = self.fixture(); args["source_rows"][0]["snapshot_date"] = "2026-09-05"
        with self.assertRaises(RuntimeError): build_index(**args)

    def test_missing_root_scope_cannot_pass(self):
        args = self.fixture(); args["source_rows"].pop()
        with self.assertRaises(RuntimeError): build_index(**args)

    def test_empty_comparison_never_passes(self):
        self.assertEqual(compare_index_outputs([], [])["status"], "blocked")


class MigrationReconciliationTests(unittest.TestCase):
    def records(self):
        content = "SELECT 1;\n"
        return [{"version": "20260906123456", "name": "test_original", "statements": [content],
                 "md5": hashlib.md5(content.encode()).hexdigest()}]

    def test_exact_bytes_and_original_ids_retained(self):
        records = validate_export(self.records(), verify_checkpoint=False)
        with TemporaryDirectory() as tmp:
            pending, conflicts = plan_files(records, Path(tmp))
            self.assertEqual(write_plan(pending, conflicts, write=True), 2)
            for p, content in pending:
                self.assertEqual(p.read_bytes(), content.encode())
                self.assertTrue(p.name.startswith("20260906123456_"))
            again, conflicts = plan_files(records, Path(tmp)); self.assertEqual(again, [])

    def test_bad_hash_refuses_import(self):
        records = self.records(); records[0]["md5"] = "bad"
        with self.assertRaises(ValueError): validate_export(records, verify_checkpoint=False)

    def test_missing_statement_placeholder_forbidden(self):
        records = self.records(); records[0]["statements"] = []
        with self.assertRaises(ValueError): validate_export(records, verify_checkpoint=False)

    def test_renumbered_alias_or_changed_content_refuses_all_writes(self):
        records = validate_export(self.records(), verify_checkpoint=False)
        with TemporaryDirectory() as tmp:
            folder = Path(tmp) / "supabase/migrations"; folder.mkdir(parents=True)
            (folder / "20260906999999_test_original.sql").write_text("-- other session")
            pending, conflicts = plan_files(records, Path(tmp))
            self.assertTrue(conflicts)
            with self.assertRaises(ValueError): write_plan(pending, conflicts, write=True)
            self.assertFalse((Path(tmp) / "backend/db/migrations").exists())

    def test_checkpoint_mismatch_requires_reaudit(self):
        with self.assertRaises(ValueError): validate_export(self.records())

    def test_dry_run_creates_nothing(self):
        records = validate_export(self.records(), verify_checkpoint=False)
        with TemporaryDirectory() as tmp:
            pending, conflicts = plan_files(records, Path(tmp))
            self.assertEqual(write_plan(pending, conflicts, write=False), 0)
            self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_path_traversal_rejected(self):
        records = self.records(); records[0]["name"] = "../secrets"
        with self.assertRaises(ValueError): validate_export(records, verify_checkpoint=False)


class SqlProposalContractTests(unittest.TestCase):
    def test_release_gate_disabled_and_existing_functions_not_replaced(self):
        sql = (ROOT / "db/proposals/price_storage_v2_scoped_publication.sql").read_text()
        self.assertIn("VALUES(true,false)", sql)
        self.assertNotIn("CREATE OR REPLACE", sql)
        self.assertNotIn("DELETE FROM", sql)
        self.assertNotIn("ON CONFLICT DO UPDATE", sql)
        self.assertNotIn("UPDATE public.pokemon_set_value_daily_history", sql)
        self.assertIn("v_candidates IS DISTINCT FROM v_preview->'candidate_values'", sql)
        self.assertIn("md5(v_preview::text) IS DISTINCT FROM v_run.evidence_signature", sql)

    def test_writer_destinations_cannot_cross(self):
        sql = (ROOT / "db/proposals/price_storage_v2_scoped_publication.sql").read_text()
        self.assertIn("WHEN 'member' THEN 'pokemon_member_set_value_daily_history_v2'", sql)
        self.assertIn("ELSE 'pokemon_root_set_value_daily_history_v2'", sql)
        self.assertIn("SECURITY INVOKER", sql)
        self.assertIn("FROM PUBLIC,anon,authenticated,service_role", sql)


if __name__ == "__main__":
    unittest.main()
