"""Migration 058's lifecycle lists must stay generated, not hand-maintained.

The 2026-08-03 incident was a metadata/runtime divergence. A migration carrying a
hand-typed canonical-key list is exactly the same class of hazard one layer down,
so these tests fail if the committed SQL drifts from the real SET_CONFIG_MAP.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from backend.db.services.pokemon_set_lifecycle_flags import (
    is_daily_scrape_ready,
    normalize_details_url,
    resolve_config_lifecycle_flags,
)
from backend.scripts.generate_set_lifecycle_flag_backfill import build_lifecycle_backfill

MIGRATION_PATH = (
    Path(__file__).resolve().parents[3]
    / "db"
    / "migrations"
    / "058_set_lifecycle_flags_and_scrape_runtime_provenance.sql"
)


def _sql_array_values(sql: str, variable: str) -> list[str]:
    match = re.search(rf"{variable} TEXT\[\] := ARRAY\[(.*?)\]::text\[\]", sql, re.DOTALL)
    assert match, f"could not locate {variable} array in migration 058"
    return re.findall(r"'([^']+)'", match.group(1))


@pytest.fixture(scope="module")
def migration_sql() -> str:
    return MIGRATION_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def backfill() -> dict:
    return build_lifecycle_backfill()


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
    CARD_DETAILS_URL = "https://www.tcgplayer.com/z"


def test_catalog_only_config_is_discovered_and_defaults_to_no_simulation():
    flags = resolve_config_lifecycle_flags(_CatalogOnlyConfig)
    assert flags["catalog_only"] is True
    assert flags["supports_opening_simulation"] is False


def test_plain_config_defaults_to_simulation_supported():
    flags = resolve_config_lifecycle_flags(_PlainConfig)
    assert flags["catalog_only"] is False
    assert flags["supports_opening_simulation"] is True


def test_explicit_simulation_flag_overrides_the_default():
    flags = resolve_config_lifecycle_flags(_ExplicitNoSimConfig)
    assert flags["catalog_only"] is False
    assert flags["supports_opening_simulation"] is False


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
def test_migration_catalog_only_list_matches_configs(migration_sql, backfill):
    assert _sql_array_values(migration_sql, "v_catalog_only_keys") == backfill["catalog_only_keys"]


def test_migration_no_simulation_list_matches_configs(migration_sql, backfill):
    assert _sql_array_values(migration_sql, "v_no_simulation_keys") == backfill["no_simulation_keys"]


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
