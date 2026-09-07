"""Validate the review-only scoped publication coordinator on exact restored source SQL.

Uses the same bounded Evolving Skies / Crown Zenith+Gallery / Celebrations+Classic
fixture as the exact-source contract suite. No Supabase DSN or production credential
is accepted. The coordinator proposal itself contains no cron attachment.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.tests.test_price_storage_v2_real_source_sql import (
    DAY,
    ROOTS,
    SETS,
    RealSourceContractTests,
)


def root_array(values=ROOTS) -> str:
    return "ARRAY[" + ",".join(f"'{value}'" for value in values) + "]::uuid[]"


def main() -> int:
    if not os.environ.get("PRICE_STORAGE_V2_TEST_CONTAINER"):
        raise SystemExit("isolated Docker PostgreSQL service required")

    cls = RealSourceContractTests
    cls.setUpClass()
    proposal = REPO_ROOT / "backend/db/proposals/price_storage_v2_scoped_publication_cycle.sql"
    sql = proposal.read_text(encoding="utf-8")
    if "cron.schedule" in sql or "cron.unschedule" in sql:
        raise AssertionError("coordinator proposal must not attach or mutate a scheduler")
    cls.run(sql)

    def counts():
        return cls.value("""
SELECT jsonb_build_object(
 'stage_runs',(SELECT count(*) FROM public.price_storage_v2_scope_stage_runs),
 'candidate_rows',(SELECT count(*) FROM public.price_storage_v2_scoped_value_candidates),
 'member_rows',(SELECT count(*) FROM public.pokemon_member_set_value_daily_history_v2),
 'root_rows',(SELECT count(*) FROM public.pokemon_root_set_value_daily_history_v2));
""")

    before = counts()
    if before != {"stage_runs":0,"candidate_rows":0,"member_rows":0,"root_rows":0}:
        raise AssertionError(f"unexpected clean-fixture state: {before}")

    # Gate is disabled by default and rejection occurs before staging writes.
    rejected = cls.run(
        f"SELECT public.run_price_storage_v2_scoped_publication_cycle('{DAY}',{root_array()});",
        check=False,
    )
    if rejected.returncode == 0 or counts() != before:
        raise AssertionError("disabled coordinator must fail before any stage/publish write")
    print("coordinator_disabled_before_stage: ok", flush=True)

    # The owner/admin-controlled gate is enabled only inside this disposable fixture.
    cls.run("UPDATE public.price_storage_v2_scoped_release_gate SET enabled=true;")
    first = cls.value(
        f"SELECT public.run_price_storage_v2_scoped_publication_cycle('{DAY}',{root_array()});"
    )
    if first.get("status") != "complete" or first.get("root_count") != 3:
        raise AssertionError(first)
    if any(row.get("member_status") != "complete" or row.get("root_status") != "complete"
           for row in first.get("results") or []):
        raise AssertionError(first)
    published = counts()
    if published != {"stage_runs":3,"candidate_rows":24,"member_rows":15,"root_rows":9}:
        raise AssertionError(published)
    print("coordinator_first_atomic_publication: ok", flush=True)

    # Exact repeat reuses staged evidence and becomes destination no-op.
    second = cls.value(
        f"SELECT public.run_price_storage_v2_scoped_publication_cycle('{DAY}',{root_array()});"
    )
    if any(row.get("member_status") != "noop" or row.get("root_status") != "noop"
           for row in second.get("results") or []):
        raise AssertionError(second)
    if counts() != published:
        raise AssertionError("repeat cycle changed immutable publication state")
    print("coordinator_repeat_noop: ok", flush=True)

    # Duplicate root requests are rejected without mutation.
    duplicate = cls.run(
        f"SELECT public.run_price_storage_v2_scoped_publication_cycle('{DAY}',"
        f"{root_array((ROOTS[0],ROOTS[0]))});",
        check=False,
    )
    if duplicate.returncode == 0 or counts() != published:
        raise AssertionError("duplicate roots must fail closed")
    print("coordinator_duplicate_roots_blocked: ok", flush=True)

    # Make one member source receipt invalid. The coordinator may discover the first
    # requested root is valid, but the later blocked root must roll back all new stage work.
    cls.run(
        f"UPDATE public.scrape_jobs SET status='failed' "
        f"WHERE set_id='{SETS['Classic Collection']}' AND market_date='{DAY}';"
    )
    blocked_before = counts()
    blocked = cls.run(
        f"SELECT public.run_price_storage_v2_scoped_publication_cycle('{DAY}',"
        f"{root_array((ROOTS[0],ROOTS[2]))});",
        check=False,
    )
    if blocked.returncode == 0 or counts() != blocked_before:
        raise AssertionError("mixed pass/block cycle must roll back staging and publication atomically")
    cls.run(
        f"UPDATE public.scrape_jobs SET status='completed' "
        f"WHERE set_id='{SETS['Classic Collection']}' AND market_date='{DAY}';"
    )
    print("coordinator_mixed_block_rolls_back: ok", flush=True)

    # Public roles cannot execute the coordinator even when the admin gate is enabled.
    denied = cls.run(
        f"SET ROLE anon; SELECT public.run_price_storage_v2_scoped_publication_cycle('{DAY}',{root_array()});",
        check=False,
    )
    if denied.returncode == 0:
        raise AssertionError("anon unexpectedly executed scoped coordinator")
    print("coordinator_public_role_denied: ok", flush=True)

    print("SCOPED_COORDINATOR_CONTRACTS=6 passed", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
