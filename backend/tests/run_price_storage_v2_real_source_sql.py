"""Run exact-source SQL contracts plus the date-safe v2 staging successor.

The historical fixture class intentionally exposes a class-level SQL helper named
`run`, so this runner calls its test methods directly. The already-applied v1
stage remains unmodified; this runner installs the v2 successor and proves both
current-date publication and historical retry safety.
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
    before = cls.value(f"""
SELECT jsonb_agg(jsonb_build_object(
 'canonical_card_id',canonical_card_id,
 'card_variant_id',card_variant_id,
 'market_price',market_price,
 'captured_at',captured_at
) ORDER BY canonical_card_id)
FROM public.get_pokemon_market_root_set_card_prices_latest_v1('{root}')
WHERE market_scope='standard';
""")
    cls.run(f"""
UPDATE public.pokemon_canonical_card_market_prices_latest p
SET captured_at='2026-09-07',
    market_price=p.market_price+100,
    source='fixture-newer-latest'
WHERE p.set_id='{root}';
INSERT INTO public.pokemon_market_date_quality(market_date,tcg,status)
VALUES('2026-09-07','pokemon','READY');
""")
    after = cls.value(f"""
SELECT jsonb_agg(jsonb_build_object(
 'canonical_card_id',canonical_card_id,
 'card_variant_id',card_variant_id,
 'market_price',market_price,
 'captured_at',captured_at
) ORDER BY canonical_card_id)
FROM public.get_pokemon_market_root_set_card_prices_latest_v1('{root}')
WHERE market_scope='standard';
""")
    if before == after or not after or any(row.get("captured_at") != "2026-09-07" for row in after):
        raise AssertionError({"before": before, "after": after})

    old = cls.run(
        f"SELECT public.preview_price_storage_v2_scoped_values('{root}','{DAY}');",
        check=False,
    )
    if old.returncode == 0 or "latest approved market date" not in old.stderr:
        raise AssertionError({"stdout": old.stdout, "stderr": old.stderr})

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

    mismatch = cls.value(f"""
BEGIN;
UPDATE public.card_variant_price_observations
SET market_price=market_price+1
WHERE card_variant_id=(
  SELECT card_variant_id
  FROM public.pokemon_canonical_card_market_prices_latest
  WHERE set_id='{root}'
  ORDER BY canonical_card_id
  LIMIT 1
);
SELECT public.preview_price_storage_v2_scoped_values_v2('{root}','{DAY}');
ROLLBACK;
""")
    if mismatch.get("status") != "blocked" or mismatch.get("reason") != "raw_v2_price_contract_mismatch":
        raise AssertionError(mismatch)

    # The promoted root entrypoint is a thin wrapper around the exact V2 shadow
    # implementation. Mutate that underlying implementation transactionally to
    # simulate a true root-contract identity drift, then roll the DDL back.
    identity = cls.value(f"""
BEGIN;
DO $do$
DECLARE
  v_def text;
BEGIN
  SELECT pg_get_functiondef('public.get_pokemon_market_root_set_card_prices_latest_v1_v2_shadow(uuid)'::regprocedure)
    INTO v_def;
  v_def := replace(
    v_def,
    'AND pcc.set_value_eligible = true',
    'AND pcc.set_value_eligible = true AND pcc.id <> ''30000000-0000-4000-8000-000000000001''::uuid'
  );
  IF v_def NOT LIKE '%30000000-0000-4000-8000-000000000001%' THEN
    RAISE EXCEPTION 'fixture failed to alter root identity contract';
  END IF;
  EXECUTE v_def;
END
$do$;
SELECT public.preview_price_storage_v2_scoped_values_v2('{root}','{DAY}');
ROLLBACK;
""")
    if identity.get("status") != "blocked" or identity.get("reason") != "live_root_identity_mismatch":
        raise AssertionError(identity)
    identity_comparison = identity.get("comparison") or {}
    if identity_comparison.get("root_identity_proposed_only_rows") != 1:
        raise AssertionError(identity_comparison)


def main() -> int:
    if not os.environ.get("PRICE_STORAGE_V2_TEST_CONTAINER"):
        raise SystemExit("isolated Docker PostgreSQL service required")
    cls = RealSourceContractTests
    cls.setUpClass()

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
    print("test_08_date_safe_v2_survives_market_date_advance_and_stays_fail_closed: ok", flush=True)
    print(f"REAL_SOURCE_SQL_CONTRACTS={len(names)+1} passed", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
