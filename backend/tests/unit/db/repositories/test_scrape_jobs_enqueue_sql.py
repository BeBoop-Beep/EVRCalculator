from pathlib import Path


MIGRATION_PATH = (
    Path(__file__).resolve().parents[4]
    / "db"
    / "migrations"
    / "036_guard_enqueue_missing_scrape_jobs_for_ready_sets_by_day.sql"
)


def _migration_sql() -> str:
    return MIGRATION_PATH.read_text(encoding="utf-8")


def _compact(sql: str) -> str:
    return " ".join(sql.lower().split())


def test_enqueue_missing_scrape_jobs_sql_inserts_pending_jobs_for_ready_sets():
    sql = _compact(_migration_sql())

    assert "insert into public.scrape_jobs (set_id, status, attempts, created_at)" in sql
    assert "coalesce(s.ready_for_daily_scrape, false) = true" in sql
    assert "coalesce(s.has_card_details_url, false) = true" in sql
    assert "s.card_details_url is not null" in sql
    assert "'pending'" in sql
    assert "0" in sql
    assert "timezone('utc', now())" in sql


def test_enqueue_missing_scrape_jobs_sql_skips_current_day_jobs_in_all_cycle_statuses():
    sql = _compact(_migration_sql())

    assert "not exists" in sql
    assert "jobs.set_id = s.id" in sql
    assert "jobs.status in ('pending', 'running', 'completed', 'failed')" in sql


def test_enqueue_missing_scrape_jobs_sql_guards_only_current_utc_day():
    sql = _compact(_migration_sql())

    assert "v_cycle_start timestamptz" in sql
    assert "v_cycle_end timestamptz" in sql
    assert "date_trunc('day', now() at time zone 'utc') at time zone 'utc'" in sql
    assert "jobs.created_at >= v_cycle_start" in sql
    assert "jobs.created_at < v_cycle_end" in sql


def test_enqueue_missing_scrape_jobs_sql_preserves_active_job_race_protection_only():
    sql = _compact(_migration_sql())

    assert "on conflict (set_id) where status in ('pending', 'running') do nothing" in sql


def test_enqueue_missing_scrape_jobs_sql_is_idempotent_under_active_job_races():
    sql = _compact(_migration_sql())

    assert "on conflict (set_id) where status in ('pending', 'running') do nothing" in sql
    assert "returning 1" in sql
    assert "returns integer" in sql
