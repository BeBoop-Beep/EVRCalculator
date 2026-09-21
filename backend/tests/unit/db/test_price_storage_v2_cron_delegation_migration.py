from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
NAME = "20260921195000_delegate_v2_queue_to_staged_worker.sql"


def _sql(path: str) -> str:
    return (ROOT / path / NAME).read_text(encoding="utf-8")


def test_v2_cron_delegation_migration_mirrors_are_identical():
    assert _sql("backend/db/migrations") == _sql("supabase/migrations")


def test_v2_cron_no_longer_executes_monolithic_queue_worker():
    sql = _sql("backend/db/migrations")
    body = sql.split("CREATE OR REPLACE FUNCTION public.run_price_storage_v2_shadow_cycle()", 1)[1]
    assert "process_price_storage_v2_shadow_queue(" not in body
    assert "delegated_to_application_staged_worker" in body
    assert "enqueue_price_storage_v2_completed_scrape_jobs" in body
    assert "sync_price_storage_v2_root_history_latest" in body
    assert "sync_price_storage_v2_previous_monthly_rollup" in body
