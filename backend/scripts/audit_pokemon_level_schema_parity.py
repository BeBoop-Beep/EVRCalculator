"""Offline/read-only reconciliation for dashboard-applied Pokemon analytics DDL.

This command consumes a catalog inventory JSON produced by the read-only query
documented in docs/backend/pokemon_level_schema_reconciliation.md. It never
connects to a database and never executes migration repair.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

VERSIONS = ("20260818032645", "20260818032648")
EXPECTED_COLUMNS = {
    "pokemon_market_index_daily_history": {"id", "tcg", "index_key", "market_date", "contract_version", "methodology_version", "basket_value", "normalized_index_value", "daily_return", "previous_market_date", "set_count", "card_count", "cohort_fingerprint", "source_generation_fingerprint", "constituents_json", "diagnostics_json", "created_at", "updated_at"},
    "pokemon_rip_stats_snapshots": {"id", "market_date", "built_at", "published_at", "publication_status", "contract_version", "methodology_version", "weighting_version", "eligible_cohort_count", "exact_outcome_set_count", "total_source_outcome_count", "cohort_fingerprint", "source_run_fingerprint", "payload_json", "diagnostics_json", "created_at"},
    "pokemon_rip_stats_snapshot_sets": {"snapshot_id", "set_id", "calculation_run_id", "set_canonical_key", "pack_cost", "set_weight", "artifact_outcome_count", "artifact_sha256", "source_market_date", "created_at"},
    "pokemon_rip_stats_snapshot_latest": {"tcg", "scope", "market_date", "payload_json", "source_run_fingerprint", "payload_size_bytes", "created_at", "updated_at"},
}
EXPECTED_INDEXES = {"pokemon_market_index_key_date_idx", "pokemon_market_index_methodology_date_idx",
    "pokemon_market_index_daily_history_pkey", "pokemon_market_index_daily_history_tcg_index_key_market_date_me",
    "pokemon_rip_stats_snapshots_pkey", "pokemon_rip_stats_snapshots_market_date_contract_version_method",
    "pokemon_rip_stats_snapshot_sets_pkey", "pokemon_rip_stats_snapshot_sets_snapshot_id_calculation_run_id_",
    "pokemon_rip_stats_snapshot_latest_pkey"}
FUNCTION_TOKENS = ("security invoker", "pokemon_rip_stats_snapshots", "pokemon_rip_stats_snapshot_sets",
                   "pokemon_rip_stats_snapshot_latest", "incomplete or duplicate rip stats cohort")
CONSTRAINT_TOKENS = {
    "pokemon_market_index_daily_history": ("primary key", "unique (tcg, index_key, market_date, methodology_version)", "basket_value >", "normalized_index_value >", "jsonb_typeof(constituents_json)"),
    "pokemon_rip_stats_snapshots": ("primary key", "unique (market_date, contract_version, methodology_version, weighting_version)", "exact_outcome_set_count = eligible_cohort_count"),
    "pokemon_rip_stats_snapshot_sets": ("primary key (snapshot_id, set_id)", "unique (snapshot_id, calculation_run_id)", "foreign key (set_id)", "foreign key (calculation_run_id)"),
    "pokemon_rip_stats_snapshot_latest": ("primary key (tcg, scope)", "payload_size_bytes >"),
}


def reconcile(inventory: dict) -> dict:
    mismatches = []
    tables = inventory.get("tables") or {}
    for table, expected in EXPECTED_COLUMNS.items():
        actual = set((tables.get(table) or {}).get("columns") or [])
        if actual != expected: mismatches.append(f"{table} columns expected={sorted(expected)} actual={sorted(actual)}")
        if (tables.get(table) or {}).get("rlsEnabled") is not True: mismatches.append(f"{table} RLS is not enabled")
        constraints = " ".join((tables.get(table) or {}).get("constraints") or []).lower()
        missing_constraint_tokens = [token for token in CONSTRAINT_TOKENS[table] if token not in constraints]
        if missing_constraint_tokens: mismatches.append(f"{table} constraints differ/missing tokens: {missing_constraint_tokens}")
    actual_indexes = set(inventory.get("indexes") or [])
    missing_indexes = EXPECTED_INDEXES - actual_indexes
    if missing_indexes: mismatches.append(f"missing indexes: {sorted(missing_indexes)}")
    policies = inventory.get("policies") or []
    expected_policy = {"table": "pokemon_rip_stats_snapshot_latest", "name": "pokemon_rip_stats_snapshot_latest_read_policy", "roles": ["anon", "authenticated"], "command": "SELECT"}
    if expected_policy not in policies: mismatches.append("public latest read policy differs")
    grants = inventory.get("grants") or []
    for table in EXPECTED_COLUMNS:
        if not any(row.get("table") == table and row.get("grantee") == "service_role" for row in grants): mismatches.append(f"{table} service_role grants missing")
    private_tables = set(EXPECTED_COLUMNS) - {"pokemon_rip_stats_snapshot_latest"}
    forbidden = [row for row in grants if row.get("table") in private_tables and row.get("grantee") in {"PUBLIC", "anon", "authenticated"}]
    if forbidden: mismatches.append(f"private-table public grants differ: {forbidden}")
    definition = str((inventory.get("function") or {}).get("definition") or "").lower()
    if any(token not in definition for token in FUNCTION_TOKENS): mismatches.append("publication function definition/security differs")
    execute_roles = set((inventory.get("function") or {}).get("executeRoles") or [])
    if execute_roles != {"service_role"}: mismatches.append(f"publication function execute roles differ: {sorted(execute_roles)}")
    applied = set(inventory.get("migrationVersions") or [])
    missing_history = sorted(set(VERSIONS) - applied)
    result = {"status": "parity" if not mismatches else "mismatch", "mismatches": mismatches,
              "missingMigrationHistory": missing_history, "repairCommands": []}
    if not mismatches and missing_history:
        versions = " ".join(missing_history)
        result["repairCommands"] = ["supabase migration list --linked",
            f"supabase migration repair {versions} --status applied --linked", "supabase migration list --linked"]
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare read-only remote catalog inventory with checked-in Pokemon analytics DDL")
    parser.add_argument("inventory_json", type=Path); args = parser.parse_args()
    result = reconcile(json.loads(args.inventory_json.read_text(encoding="utf-8")))
    print(json.dumps(result, indent=2, sort_keys=True))
    raise SystemExit(0 if result["status"] == "parity" else 1)


if __name__ == "__main__": main()
