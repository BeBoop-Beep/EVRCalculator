"""Run exact-source SQL contracts plus the date-safe v2 staging successor.

The historical fixture class intentionally exposes a class-level SQL helper named
`run`, so this runner calls its test methods directly. The already-applied v1
stage remains unmodified; this runner installs the review-only v2 successor and
proves publication uses v2 evidence.
"""
from __future__ import annotations

import inspect
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


def _run_v2_stage_and_writer_contract(cls) -> None:
    staged = cls.value(
        "SELECT public.stage_price_storage_v2_scoped_values_v2(ARRAY['%s','%s','%s']::uuid[],'2026-09-06');"
        % ROOTS
    )
    if not all(r["status"] == "parity_passed" for r in staged["results"]):
        raise AssertionError(staged)
    cls.run("UPDATE public.price_storage_v2_scoped_release_gate SET enabled=true;")
    for item in staged["results"]:
        cls.run(
            f"SELECT public.publish_price_storage_v2_member_run({item['run_id']},"
            f"'{item['root_set_id']}','{DAY}');"
        )
        cls.run(
            f"SELECT public.publish_price_storage_v2_root_run({item['run_id']},"
            f"'{item['root_set_id']}','{DAY}');"
        )
    got = cls.value(f"""
SELECT jsonb_build_object(
 'member_rows',(SELECT count(*) FROM public.pokemon_member_set_value_daily_history_v2),
 'root_rows',(SELECT count(*) FROM public.pokemon_root_set_value_daily_history_v2),
 'crown_member',(SELECT set_value FROM public.pokemon_member_set_value_daily_history_v2 WHERE set_id='{SETS['Crown Zenith']}' AND value_scope='standard'),
 'crown_root',(SELECT set_value FROM public.pokemon_root_set_value_daily_history_v2 WHERE set_id='{SETS['Crown Zenith']}' AND value_scope='standard'),
 'gallery_member',(SELECT set_value FROM public.pokemon_member_set_value_daily_history_v2 WHERE set_id='{SETS['Galarian Gallery']}' AND value_scope='standard'));
""")
    expected = {"member_rows":15,"root_rows":9,"crown_member":3,"crown_root":73,"gallery_member":70}
    if got != expected:
        raise AssertionError(got)


def _run_latest_drift_contract(cls) -> None:
    root = SETS["Evolving Skies"]
    # Advance only the moving latest V2 state. Historical events/ranges remain
    # unchanged, so the approved 2026-09-06 as-of oracle still reconstructs the
    # exact original state. This reproduces the production canary failure mode.
    cls.run(f"""
UPDATE public.card_variant_price_current_v2 cur
SET last_observed_date='2026-09-07',
    last_observation_created_at='2026-09-07 12:00:00+00',
    market_price=cur.market_price+100
WHERE cur.card_variant_id IN (
  SELECT v.id
  FROM public.card_variants v
  JOIN public.cards c ON c.id=v.card_id
  WHERE c.set_id='{root}'
);
""")
    old = cls.value(
        f"SELECT public.preview_price_storage_v2_scoped_values('{root}','{DAY}');"
    )
    if old.get("status") != "blocked" or old.get("reason") != "live_root_contract_mismatch":
        raise AssertionError(old)

    new = cls.value(
        f"SELECT public.preview_price_storage_v2_scoped_values_v2('{root}','{DAY}');"
    )
    comparison = new.get("comparison") or {}
    if new.get("status") != "parity_passed" or new.get("reason") != "exact_source_gated_scope_parity_v2":
        raise AssertionError(new)
    if comparison.get("raw_only_rows") != 0 or comparison.get("v2_only_rows") != 0:
        raise AssertionError(comparison)
    if comparison.get("root_identity_live_only_rows") != 0 or comparison.get("root_identity_proposed_only_rows") != 0:
        raise AssertionError(comparison)
    if comparison.get("live_root_economic_comparison_applicable") is not False:
        raise AssertionError(comparison)
    if not isinstance(comparison.get("live_root_future_rows"), int) or comparison["live_root_future_rows"] <= 0:
        raise AssertionError(comparison)
    if comparison.get("root_economic_live_only_rows", 0) <= 0 or comparison.get("root_economic_proposed_only_rows", 0) <= 0:
        raise AssertionError(comparison)


def main() -> int:
    if not os.environ.get("PRICE_STORAGE_V2_TEST_CONTAINER"):
        raise SystemExit("isolated Docker PostgreSQL service required")
    cls = RealSourceContractTests
    cls.setUpClass()

    # Forward-only v2 proposal is applied after the exact historical v1 sources.
    cls.run((REPO_ROOT / "backend/db/proposals/price_storage_v2_scope_stage_v2.sql").read_text(encoding="utf-8"))

    names = sorted(
        name for name, value in inspect.getmembers(cls, predicate=inspect.isfunction)
        if name.startswith("test_")
    )
    if not names:
        raise AssertionError("no real-source SQL contract checks discovered")

    for name in names:
        if name == "test_05_stage_and_separated_writers_use_real_preview":
            _run_v2_stage_and_writer_contract(cls)
        else:
            case = cls(methodName=name)
            getattr(case, name)()
        print(f"{name}: ok", flush=True)

    _run_latest_drift_contract(cls)
    print("test_08_date_safe_v2_tolerates_newer_latest_only_after_identity_and_asof_parity: ok", flush=True)
    print(f"REAL_SOURCE_SQL_CONTRACTS={len(names)+1} passed", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
