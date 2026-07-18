"""Structural guarantees for the batch/lease scrape-queue orchestration migrations.

These assert the durable invariants live in the DDL (mirrors the existing
test_scrape_jobs_enqueue_sql.py convention) so a regression to the July-17
failure mode is caught without a live database.
"""

from pathlib import Path

import pytest

_MIGRATIONS = Path(__file__).resolve().parents[4] / "db" / "migrations"


def _sql(name: str) -> str:
    return (_MIGRATIONS / name).read_text(encoding="utf-8")


def _compact(sql: str) -> str:
    return " ".join(sql.lower().split())


@pytest.fixture(scope="module")
def schema_sql():
    return _compact(_sql("047_add_pokemon_scrape_batches_and_lease_columns.sql"))


@pytest.fixture(scope="module")
def rpc_sql():
    return _compact(_sql("048_scrape_queue_batch_lease_orchestration.sql"))


@pytest.fixture(scope="module")
def repair_sql():
    return _compact(_sql("049_requeue_missing_scrape_jobs_for_batch.sql"))


# --- Phase 3: batch/manifest authority -------------------------------------

def test_batch_table_has_manifest_and_lifecycle_columns(schema_sql):
    assert "create table if not exists public.pokemon_scrape_batches" in schema_sql
    for col in (
        "market_date", "timezone", "status", "expected_set_count", "queued_set_count",
        "succeeded_set_count", "failed_set_count", "missing_set_count",
        "started_at", "completed_at", "promoted_at", "error_summary",
    ):
        assert col in schema_sql, f"missing batch column {col}"
    assert "check (status in ('pending', 'running', 'incomplete', 'complete', 'failed'))" in schema_sql


def test_one_batch_per_market_date_is_idempotent(schema_sql):
    assert "unique index if not exists uq_pokemon_scrape_batches_market_date" in schema_sql
    assert "on public.pokemon_scrape_batches(market_date)" in schema_sql


def test_jobs_gain_batch_lease_and_retry_columns(schema_sql):
    for col in (
        "batch_id", "market_date", "priority", "worker_id", "heartbeat_at",
        "lease_expires_at", "next_attempt_at", "max_attempts", "diag_run_id",
    ):
        assert col in schema_sql, f"missing scrape_jobs column {col}"
    # one job per set per batch (idempotent re-enqueue)
    assert "unique index if not exists uq_scrape_jobs_batch_set" in schema_sql
    # durable diagnostics linkage
    assert "queue_job_id" in schema_sql


# --- Phase 2/11: AZ market date + dynamic cohort ---------------------------

def test_batch_creation_uses_america_phoenix_not_utc_midnight(rpc_sql):
    assert "create or replace function public.create_daily_scrape_batch" in rpc_sql
    assert "timezone('america/phoenix', now())::date" in rpc_sql
    # must not derive the business day from UTC midnight
    assert "date_trunc('day', now() at time zone 'utc')" not in rpc_sql


def test_expected_cohort_is_dynamically_derived_not_hardcoded(rpc_sql):
    assert "create or replace function public.pokemon_scrape_ready_cohort" in rpc_sql
    assert "select count(*) into v_expected from public.pokemon_scrape_ready_cohort()" in rpc_sql
    assert "166" not in rpc_sql  # never hardcode the cohort size


# --- Phase 1/4/7: reconcile-first, prior-day fail, priority, attempt bound --

def test_batch_creation_reconciles_stale_jobs_before_enqueue(rpc_sql):
    create_idx = rpc_sql.index("create or replace function public.create_daily_scrape_batch")
    body = rpc_sql[create_idx:]
    reconcile_pos = body.index("perform public.reconcile_stale_scrape_jobs")
    insert_pos = body.index("insert into public.scrape_jobs")
    # reconcile must happen before the enqueue insert so a stale active slot is freed
    assert reconcile_pos < insert_pos


def test_stale_prior_day_job_is_terminally_failed(rpc_sql):
    assert "is_prior_day" in rpc_sql
    assert "stale_prior_day_lease_expired" in rpc_sql
    # requeue only when attempts remain, otherwise fail (no infinite loop)
    assert "attempts_remain" in rpc_sql
    assert "max attempts exhausted" in rpc_sql


def test_claim_is_lease_aware_and_priority_ordered(rpc_sql):
    assert "create or replace function public.claim_next_scrape_job" in rpc_sql
    assert "perform public.reconcile_stale_scrape_jobs(now())" in rpc_sql
    assert "order by priority asc, created_at asc, id asc" in rpc_sql
    assert "lease_expires_at = now() + make_interval" in rpc_sql
    assert "next_attempt_at is null or next_attempt_at <= now()" in rpc_sql


def test_priority_gives_current_and_newest_sets_precedence(rpc_sql):
    # public/simulated tier 0, newest-active tier 1000, remainder tier 2000
    assert "when r.is_public then 0" in rpc_sql
    assert "1000" in rpc_sql
    assert "else 2000" in rpc_sql


def test_idempotent_enqueue_and_complete_batch_returns_unchanged(rpc_sql):
    assert "on conflict (batch_id, set_id) where batch_id is not null do nothing" in rpc_sql
    assert "if found and v_batch.status = 'complete' then" in rpc_sql


# --- Phase 5: durable transactional finalization ---------------------------

def test_finalize_updates_queue_diag_and_batch_in_one_function(rpc_sql):
    assert "create or replace function public.finalize_scrape_job" in rpc_sql
    fin = rpc_sql[rpc_sql.index("function public.finalize_scrape_job"):]
    assert "update public.scrape_jobs" in fin
    assert "update public.scrape_job_runs" in fin
    assert "update public.pokemon_scrape_batches" in fin
    # idempotent: re-finalizing a terminal job is a no-op
    assert "if v_job.status in ('completed', 'failed') then" in fin
    assert "'idempotent', true" in fin


# --- Phase 6: promotion gate + completeness --------------------------------

def test_partial_cohort_cannot_be_promoted(rpc_sql):
    comp = rpc_sql[rpc_sql.index("function public.complete_scrape_batch_if_ready"):]
    assert "if v_missing = 0 then" in comp
    assert "v_new_status := 'complete'" in comp
    assert "v_new_status := 'incomplete'" in comp
    # promoted_at is stamped only for a complete cohort
    assert "promoted_at = case when v_new_status = 'complete'" in comp


def test_completeness_is_measured_against_near_mint_observations(rpc_sql):
    miss = rpc_sql[rpc_sql.index("function public.pokemon_scrape_missing_sets"):]
    assert "near mint" in miss
    assert "market_price > 0" in miss
    assert "timezone('america/phoenix', o.captured_at)::date = p_market_date" in miss
    # a set is "missing" when it has NO valid observation for the market date
    assert "not exists" in miss


def test_cohort_repair_respects_attempt_limits(repair_sql):
    assert "create or replace function public.requeue_missing_scrape_jobs_for_batch" in repair_sql
    assert "j.attempts < j.max_attempts" in repair_sql
    assert "public.pokemon_scrape_missing_sets" in repair_sql
    # never reopen a set that already has an active job
    assert "a.status in ('pending', 'running')" in repair_sql


# --- Phase 9/test 15: orchestration never deletes price observations -------

def test_orchestration_migrations_never_delete_observations(rpc_sql, repair_sql, schema_sql):
    for sql in (rpc_sql, repair_sql, schema_sql):
        assert "delete from public.card_variant_price_observations" not in sql
    # reconciliation only mutates queue + diagnostic rows
    reconcile = rpc_sql[rpc_sql.index("function public.reconcile_stale_scrape_jobs"):]
    reconcile = reconcile[: reconcile.index("function public.create_daily_scrape_batch")]
    assert "card_variant_price_observations" not in reconcile
