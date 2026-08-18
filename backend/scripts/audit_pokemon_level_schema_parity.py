"""Fail-closed, offline comparison of a read-only PostgreSQL catalog inventory."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

VERSIONS = ("20260818032645", "20260818032648")


def _column(udt: str, nullable: bool, default: str | None = None) -> dict:
    return {"udt": udt, "nullable": nullable, "default": default}


EXPECTED_COLUMNS = {
    "pokemon_market_index_daily_history": {
        "id": _column("uuid", False, "gen_random_uuid()"), "tcg": _column("text", False, "'pokemon'::text"),
        "index_key": _column("text", False), "market_date": _column("date", False), "contract_version": _column("text", False),
        "methodology_version": _column("text", False), "basket_value": _column("numeric", False), "normalized_index_value": _column("numeric", False),
        "daily_return": _column("numeric", True), "previous_market_date": _column("date", True), "set_count": _column("int4", False),
        "card_count": _column("int4", False), "cohort_fingerprint": _column("text", False), "source_generation_fingerprint": _column("text", False),
        "constituents_json": _column("jsonb", False), "diagnostics_json": _column("jsonb", False, "'{}'::jsonb"),
        "created_at": _column("timestamptz", False, "timezone('utc'::text, now())"), "updated_at": _column("timestamptz", False, "timezone('utc'::text, now())")},
    "pokemon_rip_stats_snapshots": {
        "id": _column("uuid", False, "gen_random_uuid()"), "market_date": _column("date", False), "built_at": _column("timestamptz", False),
        "published_at": _column("timestamptz", True), "publication_status": _column("text", False), "contract_version": _column("text", False),
        "methodology_version": _column("text", False), "weighting_version": _column("text", False), "eligible_cohort_count": _column("int4", False),
        "exact_outcome_set_count": _column("int4", False), "total_source_outcome_count": _column("int8", False), "cohort_fingerprint": _column("text", False),
        "source_run_fingerprint": _column("text", False), "payload_json": _column("jsonb", False), "diagnostics_json": _column("jsonb", False, "'{}'::jsonb"),
        "created_at": _column("timestamptz", False, "timezone('utc'::text, now())")},
    "pokemon_rip_stats_snapshot_sets": {
        "snapshot_id": _column("uuid", False), "set_id": _column("uuid", False), "calculation_run_id": _column("uuid", False),
        "set_canonical_key": _column("text", True), "pack_cost": _column("numeric", False), "set_weight": _column("numeric", False),
        "artifact_outcome_count": _column("int4", False), "artifact_sha256": _column("text", False), "source_market_date": _column("date", False),
        "created_at": _column("timestamptz", False, "timezone('utc'::text, now())")},
    "pokemon_rip_stats_snapshot_latest": {
        "tcg": _column("text", False, "'pokemon'::text"), "scope": _column("text", False, "'rip-stats'::text"),
        "market_date": _column("date", False), "payload_json": _column("jsonb", False), "source_run_fingerprint": _column("text", False),
        "payload_size_bytes": _column("int4", False), "created_at": _column("timestamptz", False), "updated_at": _column("timestamptz", False)},
}

EXPECTED_CONSTRAINT_TOKENS = {
    "pokemon_market_index_daily_history": ("primary key (id)", "unique (tcg, index_key, market_date, methodology_version)", "check", "basket_value", "normalized_index_value", "constituents_json", "diagnostics_json"),
    "pokemon_rip_stats_snapshots": ("primary key (id)", "unique (market_date, contract_version, methodology_version, weighting_version)", "exact_outcome_set_count = eligible_cohort_count", "payload_json", "diagnostics_json"),
    "pokemon_rip_stats_snapshot_sets": ("primary key (snapshot_id, set_id)", "unique (snapshot_id, calculation_run_id)", "foreign key (snapshot_id)", "foreign key (set_id)", "foreign key (calculation_run_id)"),
    "pokemon_rip_stats_snapshot_latest": ("primary key (tcg, scope)", "payload_size_bytes", "tcg", "scope"),
}
EXPECTED_INDEX_TOKENS = {
    "pokemon_market_index_daily_history": ("(index_key, market_date desc)", "(methodology_version, market_date desc)", "unique", "(tcg, index_key, market_date, methodology_version)", "(id)"),
    "pokemon_rip_stats_snapshots": ("unique", "(market_date, contract_version, methodology_version, weighting_version)", "(id)"),
    "pokemon_rip_stats_snapshot_sets": ("unique", "(snapshot_id, calculation_run_id)", "(snapshot_id, set_id)"),
    "pokemon_rip_stats_snapshot_latest": ("unique", "(tcg, scope)"),
}
PRIVATE_TABLES = set(EXPECTED_COLUMNS) - {"pokemon_rip_stats_snapshot_latest"}
# Minimum privileges service_role must hold. service_role is intentionally privileged;
# extra grants (REFERENCES/TRIGGER/TRUNCATE) are acceptable, so this is a required subset,
# not an exact set. Public-facing roles remain strict least-privilege.
SERVICE_PRIVILEGES = {"SELECT", "INSERT", "UPDATE", "DELETE"}
FUNCTION_TOKENS = ("insert into pokemon_rip_stats_snapshots", "delete from pokemon_rip_stats_snapshot_sets",
    "insert into pokemon_rip_stats_snapshot_sets", "insert into pokemon_rip_stats_snapshot_latest",
    "incomplete or duplicate rip stats cohort", "return v_id")


def _sql(value) -> str:
    value = str(value or "").lower().replace('"', "").replace("public.", "")
    return re.sub(r"\s+", " ", value).strip()


def reconcile(inventory: dict) -> dict:
    mismatches: list[str] = []; tables = inventory.get("tables") or {}
    for table, expected_columns in EXPECTED_COLUMNS.items():
        actual_table = tables.get(table) or {}; actual_columns = {row["name"]: {"udt": row.get("udt"), "nullable": bool(row.get("nullable")), "default": row.get("default")} for row in actual_table.get("columns") or []}
        if actual_columns != expected_columns: mismatches.append(f"{table} column semantics differ")
        if actual_table.get("rlsEnabled") is not True: mismatches.append(f"{table} RLS is not enabled")
        constraints = " ".join(_sql(value) for value in actual_table.get("constraints") or [])
        if any(_sql(token) not in constraints for token in EXPECTED_CONSTRAINT_TOKENS[table]): mismatches.append(f"{table} constraint definitions differ")
        indexes = " ".join(_sql(value) for value in actual_table.get("indexes") or [])
        if any(_sql(token) not in indexes for token in EXPECTED_INDEX_TOKENS[table]): mismatches.append(f"{table} index definitions differ")
    policies = inventory.get("policies") or []
    expected_policy = {"table": "pokemon_rip_stats_snapshot_latest", "name": "pokemon_rip_stats_snapshot_latest_read_policy", "roles": ["anon", "authenticated"], "command": "SELECT", "using": "true"}
    normalized_policies = [{**row, "roles": sorted(row.get("roles") or []),
        "using": _sql(row.get("using")).strip("() ")} for row in policies]
    if normalized_policies != [expected_policy]: mismatches.append("public policy semantics differ")
    grant_map = {(row["table"], row["grantee"]): set(row.get("privileges") or []) for row in inventory.get("grants") or []}
    for table in PRIVATE_TABLES:
        if not SERVICE_PRIVILEGES.issubset(grant_map.get((table, "service_role"), set())): mismatches.append(f"{table} service_role required privileges missing")
        for role in ("PUBLIC", "anon", "authenticated"):
            if grant_map.get((table, role), set()): mismatches.append(f"{table} forbidden {role} privileges")
    latest = "pokemon_rip_stats_snapshot_latest"
    if not SERVICE_PRIVILEGES.issubset(grant_map.get((latest, "service_role"), set())): mismatches.append("public latest service_role required privileges missing")
    for role in ("anon", "authenticated"):
        if grant_map.get((latest, role)) != {"SELECT"}: mismatches.append(f"public latest {role} privileges differ")
    if grant_map.get((latest, "PUBLIC"), set()): mismatches.append("public latest PUBLIC privileges differ")
    trigger = inventory.get("trigger") or {}
    if not (trigger.get("table") == "pokemon_market_index_daily_history" and trigger.get("timing") == "BEFORE" and trigger.get("events") == ["UPDATE"] and trigger.get("function") == "sync_pokemon_public_snapshot_updated_at"):
        mismatches.append("Market updated_at trigger differs")
    function = inventory.get("function") or {}; definition = _sql(function.get("definition"))
    if function.get("securityType") != "INVOKER" or function.get("prosecdef") is not False: mismatches.append("publication function is not SECURITY INVOKER")
    if any(_sql(token) not in definition for token in FUNCTION_TOKENS): mismatches.append("publication function semantic body differs")
    execute = set(function.get("executeRoles") or [])
    if "service_role" not in execute or execute & {"PUBLIC", "anon", "authenticated"}: mismatches.append("publication function execution privileges differ")
    missing_history = sorted(set(VERSIONS) - set(inventory.get("migrationVersions") or []))
    result = {"status": "parity" if not mismatches else "mismatch", "mismatches": mismatches, "missingMigrationHistory": missing_history, "repairCommands": []}
    if not mismatches and missing_history:
        versions = " ".join(missing_history)
        result["repairCommands"] = ["supabase migration list --linked", f"supabase migration repair {versions} --status applied --linked", "supabase migration list --linked"]
    return result


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("inventory_json", type=Path); args = parser.parse_args()
    result = reconcile(json.loads(args.inventory_json.read_text(encoding="utf-8"))); print(json.dumps(result, indent=2, sort_keys=True))
    raise SystemExit(0 if result["status"] == "parity" else 1)


if __name__ == "__main__": main()
