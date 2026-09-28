"""Financial RIP history DB V1 integration and scale proof.

Disposable PostgreSQL only. The suite first executes the certified Benchmark V1
foundation test, preserving its atomicity/idempotency/237,168-row fixture, then
applies only the additive Financial history migration under test.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import runpy
import sys
import uuid


ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "benchmark-test-output"
OUT.mkdir(exist_ok=True)
if os.environ.get("PGHOST") not in ("127.0.0.1", "localhost") or os.environ.get("PGDATABASE") != "benchmark_test":
    raise SystemExit("Refusing non-isolated PostgreSQL target")

migration = Path(os.environ["RIP_FINANCIAL_HISTORY_MIGRATION"]).resolve()
if not migration.is_relative_to(ROOT):
    raise SystemExit("Migration must be inside this checkout")

foundation_path = ROOT / "backend" / "tests" / "integration" / "rip_benchmark_v1_postgres.py"
old_argv = sys.argv[:]
sys.argv = [str(foundation_path)]
base = runpy.run_path(str(foundation_path))
sys.argv = old_argv
sql = base["sql"]
val = base["val"]
uid = base["uid"]
ST = base["ST"]
A = base["A"]
fp = "a" * 64

checks: list[str] = []


def ok(name: str) -> None:
    checks.append(name)
    print("PASS financial-history:", name, flush=True)


def decode(value: str):
    return json.loads(value)


sql("BEGIN;\n" + migration.read_text(encoding="utf-8") + "\nCOMMIT;")
ok("additive migration applies after certified Benchmark V1 foundation")

assert sql(
    "SELECT count(*) FROM pg_class WHERE oid='pokemon_rip_benchmark_publication_attempts_v1'::regclass AND relrowsecurity;"
) == "1"
assert sql(
    "SELECT count(*) FROM pg_proc WHERE proname IN "
    "('get_pokemon_financial_rip_history_v1','validate_rip_benchmark_financial_authority_v1') AND prosecdef;"
) == "0"
for role in ("anon", "authenticated"):
    sql("SELECT * FROM pokemon_rip_benchmark_publication_attempts_v1;", role=role, fail="permission denied")
    sql(
        "SELECT get_pokemon_financial_rip_history_v1("
        "'[{\"entity_type\":\"set\",\"entity_id\":\"00000000-0000-0000-0000-000000000001\"}]'::jsonb,"
        "'2026-09-01','2026-09-27');",
        role=role,
        fail="permission denied",
    )
ok("RLS/security-invoker boundary denies anonymous and authenticated access")

attempt_id = uid()
sql(
    "INSERT INTO pokemon_rip_benchmark_publication_attempts_v1"
    "(id,market_date,benchmark_key,calibration_version,status,reason_code)"
    f" VALUES('{attempt_id}','2026-09-25','fixture','fixture-calibration','evaluating','ASSEMBLING');",
    role="service_role",
)
sql(
    "UPDATE pokemon_rip_benchmark_publication_attempts_v1 "
    "SET status='failed',reason_code='FIXTURE_FAILURE',completed_at=now() "
    f"WHERE id='{attempt_id}';",
    role="service_role",
)
assert sql(
    f"SELECT status||':'||reason_code FROM pokemon_rip_benchmark_publication_attempts_v1 WHERE id='{attempt_id}';",
    role="service_role",
) == "failed:FIXTURE_FAILURE"
ok("durable attempt receipt survives a failed candidate without touching public history")

# Production-shaped authority fixture for the staged->published guard.
sql(
    """CREATE TABLE public.pokemon_explore_rankings_snapshot_latest(
         tcg text not null,
         scope text not null,
         updated_at timestamptz not null,
         ranking_payload_json jsonb not null,
         primary key(tcg,scope)
       );
       GRANT SELECT ON public.pokemon_explore_rankings_snapshot_latest TO service_role;"""
)

DAY = "2026-09-25"
UPDATED = "2026-09-25T12:00:00+00:00"
RANKINGS_ID = uid()
FINANCIAL = "financial_rip_v4_outcome_profile_p95_only_25_20_15_25_10_5"
OVERALL = "overall_rip_v12_86_financial_v4_04_chase_accessibility_v1_10_collector_appeal_v5"
CHASE = "chase_accessibility_v1_hc_value_squared_modeled_probability"
COLLECTOR = "collector_appeal_v5_contextual_roster_h_only_d_baseline_up4_down2"
CALIBRATION = "rip_benchmark_v1_fin5_chase10_collector10_overall5"
set_ids = [str(uuid.UUID(hashlib.md5(f"financial-history-set-{i}".encode()).hexdigest())) for i in range(1, 23)]
era_ids = [str(uuid.UUID(hashlib.md5(f"financial-history-era-{i}".encode()).hexdigest())) for i in range(1, 3)]
rankings = {
    "meta": {
        "snapshot": {
            "publicationId": RANKINGS_ID,
            "marketDate": DAY,
            "simulationSourceMarketDate": DAY,
        },
        "ripWeightsConfig": {
            "financialRip": {"version": FINANCIAL},
            "overallRip": {"version": OVERALL},
        },
        "publicAnalyticsCohort": {
            "overallRanked": {
                "publishable": True,
                "rankedSetCount": 22,
                "rankedSetIds": set_ids,
            }
        },
    }
}
sql(
    "INSERT INTO pokemon_explore_rankings_snapshot_latest VALUES"
    f"('pokemon','rip-statistics','{UPDATED}',{val(rankings)});"
)

pub_cols = decode(
    sql(
        "SELECT json_agg(attname ORDER BY attnum) FROM pg_attribute "
        "WHERE attrelid='pokemon_rip_benchmark_publications_v1'::regclass "
        "AND attnum>0 AND NOT attisdropped AND attgenerated='';"
    )
)
source_pub = sql(
    "SELECT id FROM pokemon_rip_benchmark_publications_v1 "
    "WHERE benchmark_key='test-cohort' AND publication_status='published' "
    "ORDER BY published_at DESC LIMIT 1;"
)


def update_with_financial_guard(publication_id: str, *, fail: str | None = None) -> None:
    # The foundation suite above has already fully certified its original header
    # completeness/immutability trigger. Isolate this migration's additional
    # staged->published guard so a 24-row Financial-only fixture can exercise it
    # without fabricating unrelated Chase/Collector/Overall rows.
    sql(
        "ALTER TABLE pokemon_rip_benchmark_publications_v1 "
        "DISABLE TRIGGER rip_benchmark_header_guard_v1;"
    )
    try:
        sql(
            "UPDATE pokemon_rip_benchmark_publications_v1 "
            "SET publication_status='published',published_at=now() "
            f"WHERE id='{publication_id}';",
            fail=fail,
        )
    finally:
        sql(
            "ALTER TABLE pokemon_rip_benchmark_publications_v1 "
            "ENABLE TRIGGER rip_benchmark_header_guard_v1;"
        )


def insert_staged(publication_id: str, *, key: str, day: str, manifest: dict, canonical: bool = True) -> None:
    expr = {column: "p." + column for column in pub_cols}
    expr.update(
        id=f"'{publication_id}'::uuid",
        market_date=f"'{day}'::date",
        benchmark_key="'" + key + "'",
        calibration_version="'" + CALIBRATION + "'",
        publication_status="'staged'",
        expected_entity_count="24",
        expected_row_count="96",
        cohort_fingerprint="repeat('b',64)",
        source_fingerprint="repeat('c',64)",
        request_fingerprint="repeat('d',64)",
        overall_model_version="'" + (OVERALL if canonical else "overall-wrong") + "'",
        financial_model_version="'" + (FINANCIAL if canonical else "financial-wrong") + "'",
        chase_model_version="'" + (CHASE if canonical else "chase-wrong") + "'",
        collector_model_version="'" + (COLLECTOR if canonical else "collector-wrong") + "'",
        collector_run_id="NULL",
        collector_lineage_status="'embedded_source'",
        active_overall_publication_id=f"'{A}'::uuid",
        opening_economics_snapshot_id=f"'{ST}'::uuid",
        opening_economics_contract_version="'pokemon-rip-stats-v3'",
        opening_economics_basis="'all_modeled_products_per_pack_equivalent'",
        source_manifest=val(manifest),
        published_at="NULL",
        superseded_at="NULL",
        previous_publication_id="NULL",
    )
    sql(
        "INSERT INTO pokemon_rip_benchmark_publications_v1(" + ",".join(pub_cols) + ") "
        "SELECT " + ",".join(expr[column] for column in pub_cols) + " "
        f"FROM pokemon_rip_benchmark_publications_v1 p WHERE p.id='{source_pub}';"
    )


manifest = {
    "model_source_date": DAY,
    "set_count": 22,
    "era_count": 2,
    "product_count": 0,
    "rankings_publication_id": RANKINGS_ID,
    "rankings_updated_at": UPDATED,
    "opening_economics_snapshot_id": ST,
}

# Build 22 Set Financial rows and two deterministic equal-Set Era rows.
success_id = uid()
insert_staged(success_id, key="financial-history-fixture", day=DAY, manifest=manifest)
row_cols = decode(
    sql(
        "SELECT json_agg(attname ORDER BY attnum) FROM pg_attribute "
        "WHERE attrelid='pokemon_rip_benchmark_rows_v1'::regclass "
        "AND attnum>0 AND NOT attisdropped AND attgenerated='';"
    )
)
# The row table may not expose an id column; fall back to a direct source predicate.
source_predicate = (
    f"r.publication_id='{source_pub}' AND r.entity_type='set' AND r.metric_key='financial'"
)

set_values = ",".join(
    f"({rank},'{set_id}'::uuid)" for rank, set_id in enumerate(set_ids, 1)
)
set_expr = {column: "r." + column for column in row_cols}
set_expr.update(
    publication_id=f"'{success_id}'::uuid",
    market_date=f"'{DAY}'::date",
    entity_type="'set'",
    entity_id="x.entity_id",
    metric_key="'financial'",
    parent_set_id="NULL",
    model_status="'available'",
    model_reason="NULL",
    benchmark_status="'available'",
    benchmark_reason="NULL",
    raw_model_value="30",
    benchmark_raw_value="30",
    benchmark_score="5",
    rank="x.rank",
    cohort_size="22",
    source_model_version="'" + FINANCIAL + "'",
    source_market_date=f"'{DAY}'::date",
    source_entity_type="'set'",
    source_entity_id="x.entity_id",
    source_publication_id="NULL",
    calculation_run_id="md5('financial-history-run-'||x.rank)::uuid",
    source_result_id="NULL",
    collector_run_id="NULL",
    reconstruction_status="'persisted_exact'",
    source_lineage="'{\"proof\":\"financial-history-fixture\"}'::jsonb",
    financial_evidence_status="'available'",
    financial_evidence_reason="NULL",
    financial_evidence_market_date=f"'{DAY}'::date",
)
sql(
    "INSERT INTO pokemon_rip_benchmark_rows_v1(" + ",".join(row_cols) + ") "
    "SELECT " + ",".join(set_expr[column] for column in row_cols) + " "
    "FROM pokemon_rip_benchmark_rows_v1 r "
    f"CROSS JOIN (VALUES {set_values}) x(rank,entity_id) "
    f"WHERE {source_predicate} LIMIT 22;"
)

for era_rank, era_id in enumerate(era_ids, 1):
    members = set_ids[:16] if era_rank == 1 else set_ids[16:]
    lineage = {
        "aggregation": "equal_weight_mean_of_canonical_member_set_raw_scores",
        "aggregation_version": "era_rip_aggregation_v1_equal_set_mean",
        "member_set_ids": members,
    }
    era_expr = {column: "r." + column for column in row_cols}
    era_expr.update(
        publication_id=f"'{success_id}'::uuid",
        market_date=f"'{DAY}'::date",
        entity_type="'era'",
        entity_id=f"'{era_id}'::uuid",
        metric_key="'financial'",
        parent_set_id="NULL",
        model_status="'available'",
        model_reason="NULL",
        benchmark_status="'available'",
        benchmark_reason="NULL",
        raw_model_value="30",
        benchmark_raw_value="30",
        benchmark_score="5",
        rank=str(era_rank),
        cohort_size="2",
        source_model_version="'" + FINANCIAL + "'",
        source_market_date=f"'{DAY}'::date",
        source_entity_type="'era'",
        source_entity_id=f"'{era_id}'::uuid",
        source_publication_id="NULL",
        calculation_run_id="NULL",
        source_result_id="NULL",
        collector_run_id="NULL",
        reconstruction_status="'persisted_exact'",
        source_lineage=val(lineage),
        financial_evidence_status="'available'",
        financial_evidence_reason="NULL",
        financial_evidence_market_date=f"'{DAY}'::date",
    )
    sql(
        "INSERT INTO pokemon_rip_benchmark_rows_v1(" + ",".join(row_cols) + ") "
        "SELECT " + ",".join(era_expr[column] for column in row_cols) + " "
        f"FROM pokemon_rip_benchmark_rows_v1 r WHERE {source_predicate} LIMIT 1;"
    )

update_with_financial_guard(success_id)
assert sql(
    f"SELECT publication_status FROM pokemon_rip_benchmark_publications_v1 WHERE id='{success_id}';"
) == "published"
ok("complete coherent 22-Set/2-Era candidate passes the final atomic cutover guard")

set_entities = [{"entity_type": "set", "entity_id": item} for item in set_ids]
era_entities = [{"entity_type": "era", "entity_id": item} for item in era_ids]
set_history = decode(
    sql(
        "SELECT get_pokemon_financial_rip_history_v1("
        f"{val(set_entities)},'{DAY}','{DAY}','financial-history-fixture','{CALIBRATION}',10000,NULL);",
        role="service_role",
    )
)
era_history = decode(
    sql(
        "SELECT get_pokemon_financial_rip_history_v1("
        f"{val(era_entities)},'{DAY}','{DAY}','financial-history-fixture','{CALIBRATION}',10000,NULL);",
        role="service_role",
    )
)
history_rows = set_history["rows"] + era_history["rows"]
assert len(set_history["rows"]) == 22 and set_history["has_more"] is False
assert len(era_history["rows"]) == 2 and era_history["has_more"] is False
assert {row["absolute_financial_rip_score"] for row in history_rows} == {30}
assert {row["overall_financial_rip_reference"] for row in history_rows} == {30}
assert {row["absolute_delta_vs_overall"] for row in history_rows} == {0}
ok("typed Set/Era history RPC projects exact absolute score/reference/delta without source JSON")

# V5/V14 (or any other family) cannot enter this V4/V12 authority.
wrong_id = uid()
insert_staged(
    wrong_id,
    key="financial-history-wrong-model",
    day=DAY,
    manifest=manifest,
    canonical=False,
)
update_with_financial_guard(wrong_id, fail="non-canonical")
assert sql(
    f"SELECT publication_status FROM pokemon_rip_benchmark_publications_v1 WHERE id='{wrong_id}';"
) == "staged"
ok("model-version refusal leaves the candidate staged and prior publication readable")

# Mixed date must fail before any authority replacement.
mixed_id = uid()
mixed_manifest = dict(manifest)
mixed_manifest["model_source_date"] = "2026-09-24"
insert_staged(
    mixed_id,
    key="financial-history-mixed-date",
    day=DAY,
    manifest=mixed_manifest,
)
update_with_financial_guard(mixed_id, fail="same-day")
assert sql(
    f"SELECT publication_status FROM pokemon_rip_benchmark_publications_v1 WHERE id='{mixed_id}';"
) == "staged"
ok("mixed-date candidate is refused without clearing the current publication")

# A same-day but incomplete candidate reaches the row-count guard and fails closed.
incomplete_id = uid()
insert_staged(
    incomplete_id,
    key="financial-history-incomplete",
    day=DAY,
    manifest=manifest,
)
update_with_financial_guard(incomplete_id, fail="Set Financial authority is incomplete")
assert sql(
    f"SELECT publication_status FROM pokemon_rip_benchmark_publications_v1 WHERE id='{incomplete_id}';"
) == "staged"
assert sql(
    f"SELECT publication_status FROM pokemon_rip_benchmark_publications_v1 WHERE id='{success_id}';"
) == "published"
ok("incomplete N+1 cannot invalidate readable N")

# Scale reads: 366-day foundation fixture has 22 Sets + 2 Eras + 138 products/day.
scale_sets = [
    {
        "entity_type": "set",
        "entity_id": str(uuid.UUID(hashlib.md5(f"scale-entity-{i}".encode()).hexdigest())),
    }
    for i in range(1, 23)
]
scale_eras = [
    {
        "entity_type": "era",
        "entity_id": str(uuid.UUID(hashlib.md5(f"scale-entity-{i}".encode()).hexdigest())),
    }
    for i in (23, 24)
]
end = dt.date(2026, 9, 26)


def rpc_plan(name: str, requested: list[dict], start: dt.date, finish: dt.date, limit: int = 10000):
    query = (
        "SELECT get_pokemon_financial_rip_history_v1("
        f"{val(requested)},'{start}','{finish}','scale-cohort','scale-calibration-1',{limit},NULL);"
    )
    plan = decode(sql("EXPLAIN (ANALYZE,BUFFERS,FORMAT JSON) " + query, role="service_role"))
    payload = decode(sql(query, role="service_role"))
    return plan, payload


plans = {}
plan, payload = rpc_plan("22 sets / 30D", scale_sets, end - dt.timedelta(days=29), end)
assert len(payload["rows"]) == 22 * 30 and payload["has_more"] is False
plans["22_sets_30d"] = plan
ok("22 sets / 30D is one bounded Financial-only read")

plan, payload = rpc_plan("22 sets / 1Y", scale_sets, end - dt.timedelta(days=365), end)
assert len(payload["rows"]) == 22 * 366 and payload["has_more"] is False
plans["22_sets_1y"] = plan
ok("22 sets / 1Y fits one 10,000-row page")

plan, payload = rpc_plan("2 eras / 1Y", scale_eras, end - dt.timedelta(days=365), end)
assert len(payload["rows"]) == 2 * 366 and payload["has_more"] is False
plans["2_eras_1y"] = plan
ok("2 eras / 1Y is one bounded Financial-only read")

# ALL fixture history with a deliberately smaller page proves deterministic keyset pagination.
start = end - dt.timedelta(days=365)
page = decode(
    sql(
        "SELECT get_pokemon_financial_rip_history_v1("
        f"{val(scale_sets)},'{start}','{end}','scale-cohort','scale-calibration-1',1000,NULL);",
        role="service_role",
    )
)
all_rows = page["rows"][:]
pages = 1
while page["has_more"]:
    page = decode(
        sql(
            "SELECT get_pokemon_financial_rip_history_v1("
            f"{val(scale_sets)},'{start}','{end}','scale-cohort','scale-calibration-1',1000,"
            f"{val(page['next_cursor'])});",
            role="service_role",
        )
    )
    all_rows += page["rows"]
    pages += 1
assert len(all_rows) == 22 * 366
assert len(
    {
        (row["market_date"], row["entity_type"], row["entity_id"], row["publication_id"])
        for row in all_rows
    }
) == len(all_rows)
assert pages == 9
plans["all_history_1000_row_pages"] = {"pages": pages, "rows": len(all_rows)}
ok("ALL history keyset pagination has no gaps or duplicates")

# Prove the typed access path uses a history index on the 237,168-row fixture.
underlying = (
    "SELECT r.market_date,r.entity_type,r.entity_id,r.raw_model_value,r.benchmark_raw_value "
    f"FROM jsonb_to_recordset({val(scale_sets)}) e(entity_type text,entity_id uuid) "
    "JOIN pokemon_rip_benchmark_rows_v1 r "
    "ON r.entity_type=e.entity_type AND r.entity_id=e.entity_id "
    "JOIN pokemon_rip_benchmark_publications_v1 p ON p.id=r.publication_id "
    f"WHERE r.metric_key='financial' AND r.entity_type IN ('set','era') "
    f"AND r.market_date BETWEEN '{start}' AND '{end}' "
    "AND p.benchmark_key='scale-cohort' AND p.calibration_version='scale-calibration-1' "
    "AND p.publication_status='published' "
    "ORDER BY r.market_date,r.entity_type,r.entity_id,r.publication_id LIMIT 10000"
)
index_plan = decode(sql("EXPLAIN (ANALYZE,BUFFERS,FORMAT JSON) " + underlying))
index_text = json.dumps(index_plan)
assert (
    "rip_benchmark_financial_history_v1" in index_text
    or "rip_benchmark_row_history_v1" in index_text
), index_text
plans["underlying_financial_index"] = index_plan
ok("Financial history read uses an indexed typed-row access path")

(OUT / "financial-history-plans.json").write_text(json.dumps(plans, indent=2), encoding="utf-8")
result = {
    "passed": len(checks),
    "checks": checks,
    "foundation_checks": len(base["checks"]),
    "foundation_scale_rows": 237168,
    "postgres_version": sql("SHOW server_version;"),
    "migration": migration.name,
}
(OUT / "financial-history-results.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
print("FINANCIAL_HISTORY_RESULT", json.dumps(result), flush=True)
