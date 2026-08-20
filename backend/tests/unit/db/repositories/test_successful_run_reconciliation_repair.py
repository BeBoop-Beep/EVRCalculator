from pathlib import Path
import re

import pytest

from backend.db.repositories import scrape_jobs_repository as repo
from backend.db.services.scrape_failure_classification import (
    ERROR_EXTERNAL_VARIANT_IDENTITY_CONFLICT,
    NON_RETRYABLE_ERROR_CODES,
    classify_report_failure,
    is_retryable,
)


ROOT = Path(__file__).resolve().parents[4]
BACKEND_MIGRATION = ROOT / "db" / "migrations" / "20260819210000_add_successful_run_reconciliation_repair.sql"
SUPABASE_MIGRATION = ROOT.parent / "supabase" / "migrations" / BACKEND_MIGRATION.name


@pytest.fixture(scope="module")
def sql():
    return " ".join(BACKEND_MIGRATION.read_text(encoding="utf-8").lower().split())


@pytest.fixture(scope="module")
def run_repair_sql(sql):
    start = sql.index(
        "create or replace function public.requeue_unreconciled_retryable_scrape_jobs_for_batch"
    )
    return sql[start:sql.index(
        "revoke all on function public.scrape_error_code_is_retryable", start
    )]


@pytest.fixture(scope="module")
def observation_repair_sql(sql):
    start = sql.index(
        "create or replace function public.requeue_missing_scrape_jobs_for_batch"
    )
    end = sql.index(
        "create or replace function public.requeue_unreconciled_retryable_scrape_jobs_for_batch",
        start,
    )
    return sql[start:end]


def test_migration_mirrors_are_byte_identical():
    assert BACKEND_MIGRATION.read_bytes() == SUPABASE_MIGRATION.read_bytes()


def test_zero_or_existing_observations_do_not_gate_run_repair(run_repair_sql):
    assert "from public.pokemon_scrape_missing_sets" not in run_repair_sql
    assert "card_variant_price_observations" not in run_repair_sql
    assert "j.status = 'failed'" in run_repair_sql


def test_observation_repair_blocks_deterministic_but_reopens_transient(
    observation_repair_sql,
):
    reopened = observation_repair_sql[
        observation_repair_sql.index("with reopened as"):observation_repair_sql.index(
            "with inserted as"
        )
    ]
    assert "j.status = 'failed'" in reopened
    assert "j.attempts < j.max_attempts" in reopened
    assert "public.scrape_error_code_is_retryable(j.error_code)" in reopened
    assert is_retryable(ERROR_EXTERNAL_VARIANT_IDENTITY_CONFLICT) is False
    assert is_retryable("ingestion_failure") is True


def test_observation_repair_fresh_job_insertion_semantics_are_preserved(
    observation_repair_sql,
):
    inserted = observation_repair_sql[observation_repair_sql.index("with inserted as"):]
    assert "from public.pokemon_scrape_ready_cohort() c" in inserted
    assert "join _missing_sets ms on ms.set_id = c.set_id" in inserted
    assert "on conflict (batch_id, set_id) where batch_id is not null do nothing" in inserted


def test_retry_budget_and_active_job_guards_are_durable(sql):
    assert "j.attempts < j.max_attempts" in sql
    assert "a.status in ('pending', 'running')" in sql
    assert "set status = 'pending'" in sql
    assert "attempts = 0" not in sql
    assert "attempts = attempts + 1" not in sql


def test_repair_preserves_attempt_and_next_claim_owns_increment(sql):
    claim_sql = " ".join((ROOT / "db" / "migrations" /
        "20260819160000_add_date_qualified_scrape_job_claim.sql").read_text(
            encoding="utf-8").lower().split())
    assert "next_attempt_at = now() + make_interval" in sql
    assert "attempts = jobs.attempts + 1" in claim_sql


def test_qualifying_success_contract_is_exact_and_complete(sql):
    for required in (
        "r.queue_job_id = j.id",
        "r.market_date = j.market_date",
        "r.job_name = 'pokemon_set_scrape'",
        "r.source_system = 'tcgplayer'",
        "r.job_type = 'price_scrape'",
        "r.entity_type = 'set'",
        "r.status = 'success'",
        "coalesce(r.items_succeeded, 0) >= 1",
        "coalesce(r.items_failed, 0) = 0",
        "'sourcecoverageratio'",
        "'acceptedvariantgroups'",
        "'positivenmobservationcount'",
    ):
        assert required in sql


def test_wrong_date_or_unrelated_success_cannot_reconcile(sql):
    assert "r.market_date = j.market_date" in sql
    assert "r.job_name = 'pokemon_set_scrape'" in sql
    assert "r.source_system = 'tcgplayer'" in sql
    assert "r.job_type = 'price_scrape'" in sql


def test_successful_exact_date_run_suppresses_repair(sql):
    assert "and not exists ( select 1 from public.scrape_job_runs r" in sql
    assert "public.safe_scrape_metric_numeric( r.metadata ->> 'sourcecoverageratio') = 1.0" in sql


def test_malformed_metrics_are_guarded_before_any_cast(sql, run_repair_sql):
    assert "create or replace function public.safe_scrape_metric_numeric" in sql
    assert "return btrim(p_value)::numeric" in sql
    assert "when invalid_text_representation or numeric_value_out_of_range then return null" in sql
    assert "(r.metadata ->> 'sourcecoverageratio')::numeric" not in run_repair_sql
    assert "(r.metadata ->> 'acceptedvariantgroups')::integer" not in run_repair_sql
    assert "(r.metadata ->> 'positivenmobservationcount')::integer" not in run_repair_sql


def test_run_repair_uses_frozen_batch_jobs_not_current_cohort(run_repair_sql):
    assert "pokemon_scrape_ready_cohort" not in run_repair_sql
    assert "j.batch_id = p_batch_id" in run_repair_sql
    assert "j.market_date = v_batch.market_date" in run_repair_sql


def test_exhausted_and_deterministic_jobs_are_not_reopened(sql):
    assert "j.attempts < j.max_attempts" in sql
    assert "public.scrape_error_code_is_retryable(j.error_code)" in sql
    assert "'external_variant_identity_conflict'" in sql
    assert is_retryable(ERROR_EXTERNAL_VARIANT_IDENTITY_CONFLICT) is False


def test_sql_and_python_nonretryable_codes_stay_aligned():
    source = BACKEND_MIGRATION.read_text(encoding="utf-8")
    helper = source[source.index("CREATE OR REPLACE FUNCTION public.scrape_error_code_is_retryable"):
                    source.index("CREATE OR REPLACE FUNCTION public.safe_scrape_metric_numeric")]
    sql_codes = set(re.findall(r"'([a-z][a-z0-9_]*)'", helper))
    assert sql_codes == set(NON_RETRYABLE_ERROR_CODES)


def test_structured_identity_code_wins_without_substring_parsing():
    report = {"results": [{
        "error": "human-readable wording may change",
        "error_code": ERROR_EXTERNAL_VARIANT_IDENTITY_CONFLICT,
    }]}
    assert classify_report_failure(report) == ERROR_EXTERNAL_VARIANT_IDENTITY_CONFLICT


def test_nine_market_set_incident_shape_is_retryable():
    sets = {
        "ascendedHeroes", "blackBolt", "destinedRivals", "obsidianFlames",
        "paldeaEvolved", "paradoxRift", "prismaticEvolutions",
        "surgingSparks", "whiteFlare",
    }
    jobs = [{"set": key, "status": "failed", "attempts": 2,
             "max_attempts": 3, "error_code": "ingestion_failure",
             "has_observations": True, "has_qualifying_success": False}
            for key in sets]
    repairable = [job for job in jobs if job["status"] == "failed"
                  and job["attempts"] < job["max_attempts"]
                  and is_retryable(job["error_code"])
                  and not job["has_qualifying_success"]]
    assert {job["set"] for job in repairable} == sets


def test_repository_normalizes_repair_diagnostics(monkeypatch):
    class Result:
        data = {"unreconciledRunRequeued": 9, "deterministicBlocked": 3}

    class RPC:
        def execute(self): return Result()

    monkeypatch.setattr(repo.supabase, "rpc", lambda name, params: RPC())
    assert repo.requeue_unreconciled_retryable_scrape_jobs_for_batch(25) == {
        "unreconciledRunRequeued": 9,
        "deterministicBlocked": 3,
    }
