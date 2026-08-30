"""Migration 058's lifecycle lists must stay generated, not hand-maintained.

The 2026-08-03 incident was a metadata/runtime divergence. A migration carrying a
hand-typed canonical-key list is exactly the same class of hazard one layer down,
so these tests fail if the committed SQL drifts from the real SET_CONFIG_MAP.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from backend.db.services.pokemon_set_lifecycle_flags import (
    is_daily_scrape_ready,
    normalize_details_url,
    resolve_config_lifecycle_flags,
)
from backend.scripts.generate_set_lifecycle_flag_backfill import build_lifecycle_backfill

_MIGRATIONS_DIR = Path(__file__).resolve().parents[3] / "db" / "migrations"
MIGRATION_PATH = _MIGRATIONS_DIR / "058_set_lifecycle_flags_and_scrape_runtime_provenance.sql"
MIGRATION_059_PATH = _MIGRATIONS_DIR / "059_correct_opening_simulation_capability.sql"


def _sql_array_values(sql: str, variable: str) -> list[str]:
    match = re.search(rf"{variable} TEXT\[\] := ARRAY\[(.*?)\]::text\[\]", sql, re.DOTALL)
    assert match, f"could not locate {variable} array in the migration"
    return re.findall(r"'([^']+)'", match.group(1))


@pytest.fixture(scope="module")
def migration_sql() -> str:
    return MIGRATION_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def migration_059_sql() -> str:
    return MIGRATION_059_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def backfill() -> dict:
    return build_lifecycle_backfill()


@pytest.fixture(scope="module")
def config_map() -> dict:
    from backend.scripts.run_pokemon_set_scrape import build_valid_set_key_registry

    return build_valid_set_key_registry()["config_map"]


# --- config flag discovery ---------------------------------------------------
class _CatalogOnlyConfig:
    CATALOG_ONLY = True
    CARD_DETAILS_URL = "https://www.tcgplayer.com/x"


class _PlainConfig:
    CARD_DETAILS_URL = "https://www.tcgplayer.com/y"


class _SealedOnlyConfig:
    SEALED_DETAILS_URL = "https://www.tcgplayer.com/sealed"


class _ExplicitNoSimConfig:
    SUPPORTS_OPENING_SIMULATION = False
    USE_MONTE_CARLO_V2 = True
    CARD_DETAILS_URL = "https://www.tcgplayer.com/z"


class _MonteCarloV2Config:
    USE_MONTE_CARLO_V2 = True
    CARD_DETAILS_URL = "https://www.tcgplayer.com/mc"


class _ExplicitSimCatalogOnlyConfig:
    CATALOG_ONLY = True
    SUPPORTS_OPENING_SIMULATION = True
    USE_MONTE_CARLO_V2 = True
    CARD_DETAILS_URL = "https://www.tcgplayer.com/c"


def test_catalog_only_config_is_discovered_and_defaults_to_no_simulation():
    flags = resolve_config_lifecycle_flags(_CatalogOnlyConfig)
    assert flags["catalog_only"] is True
    assert flags["supports_opening_simulation"] is False


def test_plain_config_is_not_simulation_supported():
    """Corrected semantics (migration 059).

    A set that merely is not catalog-only is NOT simulation-supported. The old
    `not catalog_only` default marked 172 production rows supported against a
    real V2 runner list of 22.
    """
    flags = resolve_config_lifecycle_flags(_PlainConfig)
    assert flags["catalog_only"] is False
    assert flags["supports_opening_simulation"] is False


def test_capability_is_derived_from_the_runner_criterion():
    """Rule 2: USE_MONTE_CARLO_V2 is what run_all_v2_sets.py actually filters on."""
    flags = resolve_config_lifecycle_flags(_MonteCarloV2Config)
    assert flags["supports_opening_simulation"] is True


def test_explicit_simulation_flag_overrides_the_runner_criterion():
    """Rule 1 beats rule 2: an explicit declaration wins even over V2=True."""
    flags = resolve_config_lifecycle_flags(_ExplicitNoSimConfig)
    assert flags["catalog_only"] is False
    assert flags["supports_opening_simulation"] is False


def test_catalog_only_overrides_even_an_explicit_simulation_declaration():
    """Rule 4 is absolute: catalog_only always implies false."""
    flags = resolve_config_lifecycle_flags(_ExplicitSimCatalogOnlyConfig)
    assert flags["catalog_only"] is True
    assert flags["supports_opening_simulation"] is False


def test_flag_matches_the_actual_v2_runner_set_list(backfill):
    """The strongest anti-drift guard: the flag must equal what the runner runs.

    If these ever diverge, `supports_opening_simulation` is once again claiming a
    capability the simulation runner does not have.
    """
    from backend.scripts.run_all_v2_sets import discover_sets, filter_v2_enabled_sets

    runner_keys = sorted(filter_v2_enabled_sets(discover_sets()).keys())
    assert sorted(backfill["simulation_supported_keys"]) == runner_keys


def test_catalog_only_config_can_never_become_daily_scrape_ready():
    # Even though it HAS a card URL, it must stay out of the daily cohort.
    assert resolve_config_lifecycle_flags(_CatalogOnlyConfig)["ready_for_daily_scrape"] is False
    assert is_daily_scrape_ready(card_details_url="https://x", catalog_only=True) is False


def test_card_url_is_required_for_daily_scrape():
    # A sealed URL alone must not qualify: the cohort completeness check is
    # defined over CARD observations, so such a set would wedge the batch.
    assert resolve_config_lifecycle_flags(_SealedOnlyConfig)["ready_for_daily_scrape"] is False
    assert is_daily_scrape_ready(card_details_url=None, catalog_only=False) is False
    assert is_daily_scrape_ready(card_details_url="   ", catalog_only=False) is False
    assert is_daily_scrape_ready(card_details_url="https://x", catalog_only=False) is True


def test_url_normalization_is_conservative():
    assert normalize_details_url("https://Www.TCGplayer.com/Path/") == "https://www.tcgplayer.com/Path"
    # Path case is preserved because TCGplayer paths are case-sensitive.
    assert normalize_details_url("https://a.com/AbC") != normalize_details_url("https://a.com/abc")
    assert normalize_details_url(None) is None


# --- migration list generation ----------------------------------------------
def test_migration_058_catalog_only_list_is_a_frozen_subset_of_current_configs(
    migration_sql, backfill
):
    """Migration 058's list is history, not a mirror of today's configuration.

    The previous version of this test asserted byte-equality between 058's
    hand-embedded array and the CURRENT ``SET_CONFIG_MAP``. That premise is
    unsound: 058 is applied in production and immutable, while lifecycle state
    keeps evolving forward. Every later set that legitimately becomes catalog-only
    — the four EX Trainer Kit children detached from their combined TCGplayer
    groups on 2026-08-22, for example — made the old assertion fail and applied
    pressure to rewrite applied history to silence it. That is exactly backwards.

    What must still hold is the containment direction: a set 058 recorded as
    catalog-only must NOT have silently become daily-scrape-ready since. Sets may
    join the catalog-only population over time; they may not quietly leave it.
    """
    frozen = _sql_array_values(migration_sql, "v_catalog_only_keys")
    current = set(backfill["catalog_only_keys"])

    # A later lifecycle migration may intentionally promote a catalog identity
    # into a separately scraped child subset.  Such a transition is valid only
    # when it carries the machine-checkable runtime contract enforced by
    # test_set_lifecycle_migration_contract.py.
    forward_contract_keys = set()
    supabase_migrations = _MIGRATIONS_DIR.parents[2] / "supabase" / "migrations"
    contract_prefix = "-- pokemon-runtime-lifecycle-contract: "
    for path in supabase_migrations.glob("*.sql"):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith(contract_prefix):
                contract = json.loads(line[len(contract_prefix):])
                if contract.get("catalog_only") is False:
                    forward_contract_keys.add(contract["canonical_key"])

    regressed = sorted(
        key for key in frozen if key not in current and key not in forward_contract_keys
    )
    assert not regressed, (
        "sets recorded catalog-only by migration 058 are no longer catalog-only: "
        f"{regressed}"
    )


def test_migration_058_simulation_list_is_a_frozen_historical_artifact(migration_sql):
    """Migration 058 is APPLIED IN PRODUCTION and must never be rewritten.

    Under 058's (now superseded) `not catalog_only` default, its no-simulation
    list was by construction identical to its catalog-only list. That internal
    identity is the frozen contract worth asserting. The corrected capability
    lives in migration 059, and neither list is compared against current configs —
    doing so would pressure someone into editing an already-applied migration.
    """
    assert _sql_array_values(migration_sql, "v_no_simulation_keys") == _sql_array_values(
        migration_sql, "v_catalog_only_keys"
    )


def test_a_config_that_drops_its_card_url_is_carried_by_a_forward_migration(config_map):
    """The latest EFFECTIVE state — 058 plus every forward migration — must
    account for current configuration, for the one change sync cannot make.

    This is the assertion the old test was reaching for, done correctly. Most
    lifecycle changes need no migration at all: ``sync_pokemon_era_and_set_metadata``
    propagates flags like ``catalog_only`` straight from the configs, which is how
    e.g. ``megaEvolutionPromos`` became catalog-only without one.

    CLEARING a details URL is the exception. ``_coalesce_value`` treats a None
    source as "no opinion" and keeps the EXISTING database value — a deliberate
    guard so a config parse failure can never wipe every set's URL. The
    consequence is that setting ``CARD_DETAILS_URL = None`` in a config is by
    itself inert: without an explicit migration the database keeps serving the old
    URL, and the set silently stays in the daily cohort. That is precisely how a
    detached set would keep scraping a source it no longer claims.

    Scope note: a set that never had a URL (the promo/miscellany sets such as
    ``bestOfGame`` and the Black Star Promos) has nothing stale to clear and needs
    no migration. Static configuration cannot distinguish "never had one" from
    "gave one up", so this test asserts the concrete, known set of detachments.
    The general config-vs-database divergence check is the runtime preflight's
    job (``pokemon_scrape_runtime_preflight``, ``MISMATCH_URL``), which compares
    live rows rather than guessing from source.
    """
    detached_by_this_repair = [
        "exTrainerKit2Minun",
        "exTrainerKit2Plusle",
        "exTrainerKitLatias",
        "exTrainerKitLatios",
    ]
    for key in detached_by_this_repair:
        assert resolve_config_lifecycle_flags(config_map[key])["card_details_url"] is None

    all_sql = "\n".join(
        path.read_text(encoding="utf-8") for path in sorted(_MIGRATIONS_DIR.glob("*.sql"))
    )
    uncovered = sorted(
        key
        for key in detached_by_this_repair
        if not re.search(
            rf"'{re.escape(key)}'[^;]*?card_details_url\s*=\s*NULL"
            rf"|card_details_url\s*=\s*NULL[^;]*?'{re.escape(key)}'",
            all_sql,
            re.DOTALL,
        )
    )
    assert not uncovered, (
        "config declares no card_details_url but no migration NULLs it, so the "
        f"database keeps the stale URL: {uncovered}"
    )


# --- migration 059: corrected opening-simulation capability -------------------
def test_migration_059_allow_list_matches_configs(migration_059_sql, backfill):
    """The allow-list must stay generated, never hand-maintained."""
    assert (
        _sql_array_values(migration_059_sql, "v_simulation_supported_keys")
        == backfill["simulation_supported_keys"]
    )


def test_migration_059_expected_count_matches_the_generated_list(migration_059_sql, backfill):
    keys = _sql_array_values(migration_059_sql, "v_simulation_supported_keys")
    match = re.search(r"v_expected_supported INTEGER := (\d+)", migration_059_sql)
    assert match, "migration 059 must declare its expected supported count"
    assert int(match.group(1)) == len(keys) == backfill["simulation_supported_count"]


def test_migration_059_fails_closed_on_catalog_only(migration_059_sql):
    assert "NOT COALESCE(catalog_only, FALSE)" in migration_059_sql
    assert "Migration 059 invariant violated" in migration_059_sql
    assert "catalog-only set(s) marked supports_opening_simulation" in migration_059_sql


def test_migration_059_reports_the_resulting_supported_count(migration_059_sql):
    assert "RAISE NOTICE" in migration_059_sql
    assert "supports_opening_simulation=%" in migration_059_sql


def test_migration_059_leaves_catalog_only_and_daily_cohort_untouched(migration_059_sql):
    """Scope guard: 059 must not reopen the working migration-058 semantics."""
    assert "SET catalog_only" not in migration_059_sql
    assert "SET ready_for_daily_scrape" not in migration_059_sql
    assert "pokemon_scrape_ready_cohort" not in migration_059_sql
    # Exactly one column is recomputed.
    assert migration_059_sql.count("SET supports_opening_simulation = (") == 1


def test_migration_059_adds_no_grants_and_no_policies(migration_059_sql):
    """Migration 051's privilege rules must survive untouched."""
    for forbidden in ("GRANT ", "CREATE POLICY", "TO PUBLIC", "GRANT ALL", "CREATE OR REPLACE FUNCTION"):
        assert forbidden not in migration_059_sql, forbidden


def test_migration_059_is_idempotent(migration_059_sql):
    """An unconditional recompute over all rows re-runs to the same state."""
    assert "BEGIN;" in migration_059_sql and "COMMIT;" in migration_059_sql
    # No append-only/DDL-conflicting statement that would break a second run.
    assert "ADD CONSTRAINT" not in migration_059_sql
    assert "INSERT INTO" not in migration_059_sql


def test_no_config_is_both_catalog_only_and_daily_ready(backfill):
    leaked = [
        row["canonical_key"]
        for row in backfill["rows"]
        if row["catalog_only"] and row["ready_for_daily_scrape"]
    ]
    assert leaked == []


# --- migration security + cohort contract ------------------------------------
def test_cohort_functions_exclude_catalog_only(migration_sql):
    for function_name in ("pokemon_scrape_ready_cohort", "enqueue_missing_scrape_jobs_for_ready_sets"):
        assert f"CREATE OR REPLACE FUNCTION public.{function_name}" in migration_sql
    # Both rewritten cohort predicates must carry the guard.
    assert migration_sql.count("COALESCE(s.catalog_only, FALSE) = FALSE") == 2


def test_migration_preserves_service_role_only_privileges(migration_sql):
    # Migration 051's rules must survive: definer + fixed search_path, no
    # PUBLIC/anon/authenticated execute, service_role only.
    assert "SET search_path = public" in migration_sql
    assert "SECURITY DEFINER" in migration_sql
    assert "TO PUBLIC" not in migration_sql
    assert "GRANT EXECUTE ON FUNCTION public.pokemon_scrape_ready_cohort()\n    TO service_role;" in migration_sql

    for grantee in ("anon", "authenticated"):
        assert f"GRANT EXECUTE ON FUNCTION public.pokemon_scrape_ready_cohort()\n    TO {grantee}" not in migration_sql

    # Every function this migration (re)creates is revoked from the public roles.
    revoked = re.findall(r"REVOKE ALL ON FUNCTION public\.(\w+)", migration_sql)
    for expected in (
        "pokemon_scrape_ready_cohort",
        "enqueue_missing_scrape_jobs_for_ready_sets",
        "requeue_missing_scrape_jobs_for_batch",
        "record_scrape_batch_runtime_provenance",
        "scrape_error_code_is_retryable",
        "finalize_scrape_job",
    ):
        assert expected in revoked

    # No RLS policy and no broad table grant is introduced here.
    assert "CREATE POLICY" not in migration_sql
    assert "GRANT ALL" not in migration_sql


def test_requeue_refuses_non_retryable_error_codes(migration_sql):
    assert "public.scrape_error_code_is_retryable(j.error_code)" in migration_sql
    for code in (
        "invalid_set_key_filter",
        "set_not_found",
        "missing_canonical_key",
        "invalid_scrape_config",
        "catalog_only_not_daily_eligible",
    ):
        assert f"'{code}'" in migration_sql


def test_migration_adds_runtime_provenance_columns(migration_sql):
    for column in ("runtime_git_sha", "runtime_registry_hash", "runtime_preflight_json"):
        assert f"ADD COLUMN IF NOT EXISTS {column}" in migration_sql


def test_catalog_only_daily_ready_invariant_is_structural(migration_sql):
    assert "CHECK (NOT (catalog_only AND ready_for_daily_scrape))" in migration_sql


# --- one definition of "simulation-supported" --------------------------------
def test_every_consumer_resolves_the_same_simulation_supported_set(backfill):
    """One definition, four consumers.

    The gate previously hardcoded two era maps and re-tested USE_MONTE_CARLO_V2
    itself. That is a drift hazard in both directions: a simulatable set in a
    third era would be invisible to the gate while the sync and the migration
    counted it, and the duplicated criterion could diverge from the shared
    resolution order. These key sets must be byte-identical.
    """
    from backend.db.services.opening_simulation_gate import supported_opening_set_keys
    from backend.scripts.run_all_v2_sets import discover_sets, filter_v2_enabled_sets

    # 1. the migration/backfill generator (feeds migration 059)
    generator_keys = sorted(backfill["simulation_supported_keys"])
    # 2. the opening simulation gate
    gate_keys = sorted(supported_opening_set_keys())
    # 3. the simulation runner itself
    runner_keys = sorted(filter_v2_enabled_sets(discover_sets()).keys())

    assert gate_keys == generator_keys == runner_keys
    assert len(gate_keys) == backfill["simulation_supported_count"]


def test_the_gate_resolves_over_the_full_registry_not_two_era_maps():
    """A regression guard for the hardcoded-era-map shortcut."""
    import inspect

    from backend.db.services import opening_simulation_gate

    source = inspect.getsource(opening_simulation_gate.supported_opening_set_keys)
    assert "build_valid_set_key_registry" in source
    assert "supports_opening_simulation" in source
    # The two-era-map shortcut and the open-coded criterion are both gone.
    assert "SCARLET_VIOLET_SET_CONFIG_MAP" not in source
    assert "MEGA_EVOLUTION_SET_CONFIG_MAP" not in source
    assert 'getattr(config, "USE_MONTE_CARLO_V2"' not in source


def test_metadata_sync_resolves_the_same_capability_as_the_gate(backfill):
    """The sync writes what resolve_config_lifecycle_flags decides."""
    from backend.db.services.opening_simulation_gate import supported_opening_set_keys
    from backend.scripts.run_pokemon_set_scrape import build_valid_set_key_registry

    config_map = build_valid_set_key_registry()["config_map"]
    sync_keys = sorted(
        key
        for key, config_cls in config_map.items()
        if resolve_config_lifecycle_flags(config_cls)["supports_opening_simulation"]
    )
    assert sync_keys == sorted(supported_opening_set_keys())
