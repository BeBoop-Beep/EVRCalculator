from backend.scripts.audit_pokemon_level_schema_parity import (CONSTRAINT_TOKENS, EXPECTED_COLUMNS,
    EXPECTED_INDEXES, FUNCTION_TOKENS, reconcile)


def inventory():
    tables = {name: {"columns": sorted(columns), "rlsEnabled": True,
                     "constraints": [" ".join(CONSTRAINT_TOKENS[name])]}
              for name, columns in EXPECTED_COLUMNS.items()}
    grants = [{"table": name, "grantee": "service_role"} for name in EXPECTED_COLUMNS]
    return {"tables": tables, "indexes": sorted(EXPECTED_INDEXES),
        "policies": [{"table": "pokemon_rip_stats_snapshot_latest", "name": "pokemon_rip_stats_snapshot_latest_read_policy", "roles": ["anon", "authenticated"], "command": "SELECT"}],
        "grants": grants, "function": {"definition": " ".join(FUNCTION_TOKENS), "executeRoles": ["service_role"]},
        "migrationVersions": []}


def test_exact_parity_prints_but_does_not_execute_repair_commands():
    result = reconcile(inventory())
    assert result["status"] == "parity"
    assert result["missingMigrationHistory"] == ["20260818032645", "20260818032648"]
    assert "migration repair 20260818032645 20260818032648 --status applied --linked" in result["repairCommands"][1]


def test_any_schema_difference_blocks_repair_recommendation():
    changed = inventory(); changed["tables"]["pokemon_rip_stats_snapshot_sets"]["columns"].remove("set_weight")
    result = reconcile(changed)
    assert result["status"] == "mismatch"
    assert result["repairCommands"] == []
