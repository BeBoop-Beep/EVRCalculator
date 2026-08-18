import copy

import pytest

from backend.scripts.audit_pokemon_level_schema_parity import (EXPECTED_COLUMNS,
    EXPECTED_CONSTRAINT_TOKENS, EXPECTED_INDEX_TOKENS, FUNCTION_TOKENS, PRIVATE_TABLES,
    SERVICE_PRIVILEGES, reconcile)


# Actual privileges service_role holds in production on the four Pokemon-level analytics
# tables, as reported by backend/scripts/assets/pokemon_level_schema_inventory.sql.
PRODUCTION_SERVICE_ROLE_PRIVILEGES = {"DELETE", "INSERT", "REFERENCES", "SELECT", "TRIGGER", "TRUNCATE", "UPDATE"}


def production_inventory():
    tables = {name: {"columns": [{"name": column, **definition} for column, definition in columns.items()],
        "rlsEnabled": True, "constraints": [" ".join(EXPECTED_CONSTRAINT_TOKENS[name])],
        "indexes": [" ".join(EXPECTED_INDEX_TOKENS[name])]}
        for name, columns in EXPECTED_COLUMNS.items()}
    grants = [{"table": table, "grantee": "service_role", "privileges": sorted(PRODUCTION_SERVICE_ROLE_PRIVILEGES)} for table in EXPECTED_COLUMNS]
    grants += [{"table": "pokemon_rip_stats_snapshot_latest", "grantee": role, "privileges": ["SELECT"]} for role in ("anon", "authenticated")]
    return {"tables": tables, "policies": [{"table": "pokemon_rip_stats_snapshot_latest",
        "name": "pokemon_rip_stats_snapshot_latest_read_policy", "roles": ["anon", "authenticated"],
        "command": "SELECT", "using": "true"}], "grants": grants,
        "trigger": {"table": "pokemon_market_index_daily_history", "timing": "BEFORE", "events": ["UPDATE"],
                    "function": "sync_pokemon_public_snapshot_updated_at"},
        "function": {"definition": " ".join(FUNCTION_TOKENS), "securityType": "INVOKER", "prosecdef": False,
                     "executeRoles": ["postgres", "service_role"]}, "migrationVersions": []}


def test_verified_production_semantics_are_parity_with_missing_history_and_repair_output():
    result = reconcile(production_inventory())
    assert result["status"] == "parity"
    assert result["missingMigrationHistory"] == ["20260818032645", "20260818032648"]
    assert "migration repair 20260818032645 20260818032648 --status applied --linked" in result["repairCommands"][1]


def mutate_column_type(value): value["tables"]["pokemon_rip_stats_snapshot_sets"]["columns"][0]["udt"] = "text"
def mutate_nullability_default(value):
    column = next(row for row in value["tables"]["pokemon_market_index_daily_history"]["columns"] if row["name"] == "tcg")
    column["nullable"] = True; column["default"] = None
def mutate_constraint(value): value["tables"]["pokemon_rip_stats_snapshots"]["constraints"] = []
def mutate_index(value): value["tables"]["pokemon_market_index_daily_history"]["indexes"] = ["(wrong)"]
def mutate_rls(value): value["tables"]["pokemon_rip_stats_snapshots"]["rlsEnabled"] = False
def mutate_policy(value): value["policies"][0]["using"] = "false"
def mutate_anon_write(value): value["grants"].append({"table": "pokemon_rip_stats_snapshot_latest", "grantee": "anon", "privileges": ["SELECT", "INSERT"]})
def mutate_trigger(value): value["trigger"] = {}
def mutate_security(value): value["function"].update({"securityType": "DEFINER", "prosecdef": True})
def mutate_rpc_grant(value): value["function"]["executeRoles"].append("anon")
def mutate_body(value): value["function"]["definition"] = "select 1"


@pytest.mark.parametrize("mutation", [mutate_column_type, mutate_nullability_default, mutate_constraint,
    mutate_index, mutate_rls, mutate_policy, mutate_anon_write, mutate_trigger, mutate_security,
    mutate_rpc_grant, mutate_body])
def test_every_semantic_drift_category_fails_closed_without_repair_commands(mutation):
    changed = copy.deepcopy(production_inventory()); mutation(changed); result = reconcile(changed)
    assert result["status"] == "mismatch"
    assert result["repairCommands"] == []


def _service_grant(inventory, table):
    return next(row for row in inventory["grants"] if row["table"] == table and row["grantee"] == "service_role")


def test_production_fixture_matches_verified_catalog_privilege_shape():
    inventory = production_inventory()
    assert SERVICE_PRIVILEGES < PRODUCTION_SERVICE_ROLE_PRIVILEGES
    for table in EXPECTED_COLUMNS:
        assert _service_grant(inventory, table)["privileges"] == [
            "DELETE", "INSERT", "REFERENCES", "SELECT", "TRIGGER", "TRUNCATE", "UPDATE"]


def test_case_a_full_production_service_role_privileges_are_parity():
    assert reconcile(production_inventory())["status"] == "parity"


@pytest.mark.parametrize("privilege", ["SELECT", "INSERT", "UPDATE", "DELETE"])
def test_cases_b_to_e_missing_required_service_role_privilege_fails_closed(privilege):
    inventory = production_inventory()
    for table in EXPECTED_COLUMNS:
        grant = _service_grant(inventory, table)
        grant["privileges"] = [item for item in grant["privileges"] if item != privilege]
    result = reconcile(inventory)
    assert result["status"] == "mismatch"
    assert result["repairCommands"] == []


@pytest.mark.parametrize("role,privileges", [("anon", ["INSERT"]), ("authenticated", ["UPDATE"]), ("PUBLIC", ["SELECT"])])
def test_cases_f_to_h_public_roles_on_private_tables_fail_closed(role, privileges):
    inventory = production_inventory()
    inventory["grants"].append({"table": sorted(PRIVATE_TABLES)[0], "grantee": role, "privileges": privileges})
    result = reconcile(inventory)
    assert result["status"] == "mismatch"
    assert result["repairCommands"] == []


def test_case_i_anon_write_on_public_latest_fails_closed():
    inventory = production_inventory()
    inventory["grants"].append({"table": "pokemon_rip_stats_snapshot_latest", "grantee": "anon",
                                "privileges": ["SELECT", "INSERT"]})
    result = reconcile(inventory)
    assert result["status"] == "mismatch"
    assert result["repairCommands"] == []


def test_case_j_additional_non_required_service_role_privilege_is_parity():
    inventory = production_inventory()
    for table in EXPECTED_COLUMNS:
        _service_grant(inventory, table)["privileges"].append("MAINTAIN")
    assert reconcile(inventory)["status"] == "parity"
