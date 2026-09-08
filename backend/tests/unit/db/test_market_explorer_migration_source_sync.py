"""Contract tests for the repo mirror of production Market Explorer migrations.

These are historical mirrors of exactly what ran in production
(`supabase_migrations.schema_migrations`), byte-verified against the ledger at
mirror time (session-level MD5 comparison against the live ledger, not
re-checked here since these tests must not require a live DB connection).
This suite only asserts on the static SQL text: that every previously-missing
version now has a file, that the historical (pre-hardening) and current
(post-hardening) `reproject_pokemon_market_explorer_card_daily_states`
definitions differ exactly as expected, that the Chansey correction is scoped
to only the canonical UPDATE, and that the batched-publication RPCs and
service-role boundaries are present. It never rewrites or "fixes" the
historical SQL -- these files are frozen historical record.
"""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
MIGRATIONS_DIR = ROOT / "backend/db/migrations"

MIRRORED_VERSIONS = [
    "20260902221622_add_market_explorer_vintage_identity_repair_primitives",
    "20260902221819_add_scoped_variant_monthly_rollup_rebuild",
    "20260903034704_harden_market_explorer_vintage_top_hits_rebuild",
    "20260903192911_add_market_explorer_current_metadata_projection",
    "20260904173530_canonical_market_root_set_universe_v1",
    "20260904173806_exclude_invalid_gym_challenge_duplicate",
    "20260904174406_canonical_market_publication_certification_v1",
    "20260904174801_canonical_market_root_set_daily_history_v1",
    "20260905040740_add_batched_market_explorer_cache_publication",
    "20260906003840_harden_market_explorer_reproject_authority_boundary",
    "20260907055306_market_explorer_v2_daily_advance_and_cache_lease_heartbeat",
    "20260907075615_stage_market_explorer_cache_from_detail",
    "20260907174821_add_market_explorer_materialized_series_rpc",
]


def test_recent_production_mirrors_are_text_identical_to_supabase_lineage():
    for stem in MIRRORED_VERSIONS[-3:]:
        backend_text = (MIGRATIONS_DIR / f"{stem}.sql").read_text(encoding="utf-8")
        lineage_text = (ROOT / "supabase/migrations" / f"{stem}.sql").read_text(encoding="utf-8")
        assert backend_text == lineage_text


def _sql(stem: str) -> str:
    path = MIGRATIONS_DIR / f"{stem}.sql"
    return " ".join(path.read_text(encoding="utf-8").lower().split())


def test_every_previously_missing_market_explorer_migration_now_has_a_repo_file():
    for stem in MIRRORED_VERSIONS:
        assert (MIGRATIONS_DIR / f"{stem}.sql").is_file(), f"missing mirrored file for {stem}"


def test_original_reproject_migration_predates_the_authority_join():
    """20260902221622 is the ORIGINAL implementation, before the later
    hardening -- it must NOT contain the canonical-authority join. This is
    historical record and must never be "fixed" retroactively.
    """
    sql = _sql("20260902221622_add_market_explorer_vintage_identity_repair_primitives")
    original_start = sql.index(
        "create or replace function public.reproject_pokemon_market_explorer_card_daily_states"
    )
    original_end = sql.index("$function$;", original_start)
    original_body = sql[original_start:original_end]
    assert "get_pokemon_canonical_card_variant_authority" not in original_body
    assert "join public.pokemon_card_variant_market_price_intervals i" in original_body
    assert "join authority a" not in original_body


def test_authority_filtered_reproject_migration_supersedes_it_later():
    """20260906003840 is the LATER hardening replacing the same function --
    it must contain the authority join this test suite already covers in
    detail (see test_market_explorer_reproject_authority_boundary_migration.py).
    Here we only assert ordering/supersession: its version sorts after the
    original, and it targets the identical function signature.
    """
    original_version = "20260902221622"
    hardened_version = "20260906003840"
    assert hardened_version > original_version  # lexicographic == chronological here
    hardened_sql = _sql("20260906003840_harden_market_explorer_reproject_authority_boundary")
    assert "get_pokemon_canonical_card_variant_authority(p_set_ids)" in hardened_sql
    assert "create or replace function public.reproject_pokemon_market_explorer_card_daily_states" in hardened_sql


def test_chansey_migration_only_performs_the_canonical_correction():
    sql = _sql("20260904173806_exclude_invalid_gym_challenge_duplicate")
    assert sql.startswith("update public.pokemon_canonical_cards")
    assert "'duplicate_alias'" in sql
    assert "set_value_eligible = false" in sql
    assert "opening_eligible = false" in sql
    assert "5b336ad8-1397-42ea-a88b-53c0d67f6d82" in sql
    # Must not touch materialized daily-states history -- Prompt 5's own
    # generic purge (commit 6b8f5417) and the reproject-authority migration
    # (20260906003840) own removing/preventing stray state rows, not this one.
    assert "pokemon_market_explorer_card_daily_states" not in sql
    assert "delete" not in sql


def test_batched_publication_migration_contains_all_four_staged_rpcs():
    sql = _sql("20260905040740_add_batched_market_explorer_cache_publication")
    for fn in (
        "stage_pokemon_market_explorer_query_cache_build",
        "upsert_pokemon_market_explorer_query_cache_constituent_batch",
        "trim_pokemon_market_explorer_query_cache_constituent_batch",
        "finalize_pokemon_market_explorer_query_cache_build",
    ):
        assert f"create or replace function public.{fn}" in sql
    assert "market_explorer.skip_constituent_sync" in sql


def test_service_role_only_boundaries_preserved_across_mirrored_migrations():
    checks = [
        ("20260902221622_add_market_explorer_vintage_identity_repair_primitives",
         "public.reproject_pokemon_market_explorer_card_daily_states(uuid[],date,date)"),
        ("20260903192911_add_market_explorer_current_metadata_projection",
         "public.refresh_pokemon_market_explorer_card_current_metadata"),
        ("20260905040740_add_batched_market_explorer_cache_publication",
         "public.finalize_pokemon_market_explorer_query_cache_build(text,uuid)"),
        ("20260906003840_harden_market_explorer_reproject_authority_boundary",
         "public.reproject_pokemon_market_explorer_card_daily_states(uuid[],date,date)"),
    ]
    for stem, signature in checks:
        sql = _sql(stem)
        base = signature.split("(")[0]
        assert f"revoke all on function {base}" in sql or f"revoke all on function {signature}" in sql
        assert f"to service_role" in sql


def test_migration_ordering_reflects_production_version_sequence():
    versions = [stem.split("_", 1)[0] for stem in MIRRORED_VERSIONS]
    assert versions == sorted(versions)
