"""Validate scoped publication and V2 serving cutover on exact restored source SQL.

Uses the same bounded Evolving Skies / Crown Zenith+Gallery / Celebrations+Classic
fixture as the exact-source contract suite. No Supabase DSN or production credential
is accepted. Neither proposal may attach a cron or enable the operator release gate.
"""
from __future__ import annotations

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


def service_cycle_sql(values=ROOTS) -> str:
    return (
        "SET ROLE service_role; "
        f"SELECT public.run_price_storage_v2_scoped_publication_cycle('{DAY}',{root_array(values)}); "
        "RESET ROLE;"
    )


def atomic_sql(run_id: int, root_id: str) -> str:
    return (
        "SET ROLE service_role; "
        "SELECT public.publish_price_storage_v2_scoped_run_atomic_v2("
        f"{run_id},'{root_id}'::uuid,'{DAY}'::date); "
        "RESET ROLE;"
    )


def main() -> int:
    if not os.environ.get("PRICE_STORAGE_V2_TEST_CONTAINER"):
        raise SystemExit("isolated Docker PostgreSQL service required")

    cls = RealSourceContractTests
    cls.setUpClass()

    # Install the forward-only date-safe stage successor after the exact historical v1 source.
    stage_v2 = REPO_ROOT / "backend/db/proposals/price_storage_v2_scope_stage_v2.sql"
    stage_v2_sql = stage_v2.read_text(encoding="utf-8")
    if "cron.schedule" in stage_v2_sql or "cron.unschedule" in stage_v2_sql:
        raise AssertionError("date-safe stage proposal must not attach or mutate a scheduler")
    cls.run(stage_v2_sql)

    # The minimal exact-source fixture creates its source tables as postgres and does not
    # replay every older Supabase ACL migration. Mirror the backend read posture explicitly.
    # This grants SELECT only: service_role still cannot UPDATE the release gate or rewrite
    # immutable destination rows. Production's Market Date Quality migration explicitly grants
    # service_role SELECT/INSERT/UPDATE on that source authority.
    quality_migration = (
        REPO_ROOT / "supabase/migrations/20260820120000_create_pokemon_market_date_quality.sql"
    ).read_text(encoding="utf-8")
    if "GRANT SELECT, INSERT, UPDATE" not in quality_migration or "TO service_role" not in quality_migration:
        raise AssertionError("production Market Date Quality service-role read grant not found")
    cls.run("""
GRANT SELECT ON TABLE
 public.conditions,
 public.sets,
 public.cards,
 public.card_variants,
 public.pokemon_canonical_cards,
 public.pokemon_canonical_card_legacy_identity_links,
 public.card_variant_price_observations,
 public.card_variant_price_events_v2,
 public.card_variant_price_observation_ranges_v2,
 public.card_variant_price_current_v2,
 public.pokemon_canonical_card_market_prices_latest,
 public.pokemon_market_explorer_card_current_metadata,
 public.pokemon_market_date_quality,
 public.scrape_jobs,
 public.price_storage_v2_shadow_queue,
 public.pokemon_edition_split_root_sets_v2,
 public.pokemon_card_desirability_links,
 public.pokemon_canonical_card_variant_preferences_v2,
 public.simulation_input_cards
TO service_role;
""")

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
 'root_rows',(SELECT count(*) FROM public.pokemon_root_set_value_daily_history_v2),
 'legacy_rows',(SELECT count(*) FROM public.pokemon_set_value_daily_history));
""")

    before = counts()
    if before != {"stage_runs":0,"candidate_rows":0,"member_rows":0,"root_rows":0,"legacy_rows":0}:
        raise AssertionError(f"unexpected clean-fixture state: {before}")

    # Gate is disabled by default and rejection occurs before staging writes.
    rejected = cls.run(service_cycle_sql(), check=False)
    if rejected.returncode == 0 or counts() != before:
        raise AssertionError("disabled coordinator must fail before any stage/publish write")
    print("coordinator_disabled_before_stage: ok", flush=True)

    # The owner/admin-controlled gate is enabled only inside this disposable fixture.
    cls.run("UPDATE public.price_storage_v2_scoped_release_gate SET enabled=true;")
    first = cls.value(service_cycle_sql())
    if first.get("status") != "complete" or first.get("root_count") != 3:
        raise AssertionError(first)
    if first.get("definition_version") != "canonical_asof_scope_split_v2":
        raise AssertionError(first)
    if any(row.get("member_status") != "complete" or row.get("root_status") != "complete"
           for row in first.get("results") or []):
        raise AssertionError(first)
    published = counts()
    if published != {"stage_runs":3,"candidate_rows":24,"member_rows":15,"root_rows":9,"legacy_rows":0}:
        raise AssertionError(published)
    print("coordinator_first_atomic_publication: ok", flush=True)

    # Exact repeat reuses staged evidence and becomes destination no-op.
    second = cls.value(service_cycle_sql())
    if any(row.get("member_status") != "noop" or row.get("root_status") != "noop"
           for row in second.get("results") or []):
        raise AssertionError(second)
    if counts() != published:
        raise AssertionError("repeat cycle changed immutable publication state")
    print("coordinator_repeat_noop: ok", flush=True)

    # Duplicate root requests are rejected without mutation.
    duplicate = cls.run(service_cycle_sql((ROOTS[0],ROOTS[0])), check=False)
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
    blocked = cls.run(service_cycle_sql((ROOTS[0],ROOTS[2])), check=False)
    if blocked.returncode == 0 or counts() != blocked_before:
        raise AssertionError("mixed pass/block cycle must roll back staging and publication atomically")
    cls.run(
        f"UPDATE public.scrape_jobs SET status='completed' "
        f"WHERE set_id='{SETS['Classic Collection']}' AND market_date='{DAY}';"
    )
    print("coordinator_mixed_block_rolls_back: ok", flush=True)

    # Install the serving cutover on this same exact-source fixture. The new one-root
    # writer must revalidate the staged preview ONCE and must not touch legacy/public
    # compatibility until the all-roots finalizer (which is post-cutover only).
    serving_proposal = REPO_ROOT / "backend/db/proposals/price_storage_v2_serving_cutover.sql"
    serving_sql = serving_proposal.read_text(encoding="utf-8")
    if "cron.schedule" in serving_sql or "cron.unschedule" in serving_sql:
        raise AssertionError("serving cutover proposal must not attach or mutate a scheduler")
    if "UPDATE public.price_storage_v2_scoped_release_gate SET enabled" in serving_sql:
        raise AssertionError("serving cutover must never enable its own operator gate")
    cls.run(serving_sql)
    print("serving_cutover_proposal_installs: ok", flush=True)

    run_id = int(cls.run(
        f"SELECT id FROM public.price_storage_v2_scope_stage_runs "
        f"WHERE root_set_id='{ROOTS[0]}' AND market_date='{DAY}' ORDER BY id DESC LIMIT 1;"
    ).stdout.strip())

    # Disabled kill switch rejects the atomic writer without changing any destination.
    cls.run("UPDATE public.price_storage_v2_scoped_release_gate SET enabled=false;")
    atomic_before = counts()
    atomic_denied = cls.run(atomic_sql(run_id, ROOTS[0]), check=False)
    if atomic_denied.returncode == 0 or counts() != atomic_before:
        raise AssertionError("atomic serving writer ignored disabled release gate")
    print("serving_atomic_gate_disabled: ok", flush=True)

    # Re-enable only in disposable CI. Existing exact V2 rows make the new atomic writer
    # a no-op, proving it accepts the old staged run without mutating legacy history.
    cls.run("UPDATE public.price_storage_v2_scoped_release_gate SET enabled=true;")
    atomic = cls.value(atomic_sql(run_id, ROOTS[0]))
    if atomic.get("status") != "noop" or atomic.get("root_rows_verified") != 3:
        raise AssertionError(atomic)
    if counts() != atomic_before:
        raise AssertionError("pre-cutover atomic V2 verification mutated history")
    print("serving_atomic_exact_repeat_noop: ok", flush=True)

    # The public compatibility finalizer has a hard post-cutover boundary. The Sep 6
    # exact-source fixture must be rejected and legacy history must remain untouched.
    pre_finalize = counts()
    finalizer = cls.run(
        "SET ROLE service_role; "
        f"SELECT public.finalize_price_storage_v2_serving_compatibility_v1('{DAY}',{root_array()});",
        check=False,
    )
    if finalizer.returncode == 0 or counts() != pre_finalize:
        raise AssertionError("pre-cutover compatibility finalization must fail closed")
    print("serving_pre_cutover_finalize_blocked: ok", flush=True)

    # Public roles cannot execute either old coordinator or new atomic serving writer.
    denied = cls.run(
        f"SET ROLE anon; SELECT public.run_price_storage_v2_scoped_publication_cycle('{DAY}',{root_array()});",
        check=False,
    )
    if denied.returncode == 0:
        raise AssertionError("anon unexpectedly executed scoped coordinator")
    denied_atomic = cls.run(
        f"SET ROLE anon; SELECT public.publish_price_storage_v2_scoped_run_atomic_v2({run_id},'{ROOTS[0]}','{DAY}');",
        check=False,
    )
    if denied_atomic.returncode == 0:
        raise AssertionError("anon unexpectedly executed atomic V2 serving writer")
    print("serving_public_roles_denied: ok", flush=True)

    print("SCOPED_COORDINATOR_AND_SERVING_CONTRACTS=10 passed", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
