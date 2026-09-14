"""Real PostgreSQL publication/permission/concurrency tests; never use production.

CI provides an isolated postgres:17 service. Local runs require an explicit DSN
and acknowledgement; absence skips the suite rather than inventing DB passes.
"""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import time
from uuid import UUID

import pytest

DSN = os.getenv('BEST_OPEN_TEST_DATABASE_URL')
pytestmark = pytest.mark.skipif(not DSN, reason='isolated PostgreSQL DSN required')
ROOT = Path(__file__).resolve().parents[3]
OLD = ROOT / 'supabase/migrations/20260914184759_create_budget_product_best_open_price_store.sql'
NEW = ROOT / 'supabase/migrations/20260914225000_harden_best_open_publication_review.sql'
SID = '00000000-0000-0000-0000-000000000100'
T1 = '2026-09-08T20:20:33+00:00'
T2 = '2026-09-09T20:20:33+00:00'
VERSIONS = dict(
    ranking_method_version='budget_product_ranking_v1',
    allocation_method_version='budget_allocation_floor_quantity_v1',
    comparison_scope_version='budget_constrained_whole_unit_cross_format_v1',
    financial_rip_version='financial_rip_v4_outcome_profile_p95_only_25_20_15_25_10_5',
    overall_rip_v12_version='overall_rip_v12_86_financial_v4_04_chase_accessibility_v1_10_collector_appeal_v5',
    collector_appeal_version='collector_appeal_v5_contextual_roster_h_only_d_baseline_up4_down2',
    chase_accessibility_version='chase_accessibility_v1_hc_value_squared_modeled_probability',
    chase_accessibility_transform_version='chase_accessibility_overall_score_v1_saturating_k002',
)
METHOD = 'budget_product_best_open_price_full_market_v1'


def connection(**kwargs):
    import psycopg
    return psycopg.connect(DSN, **kwargs)


@pytest.fixture(scope='module', autouse=True)
def database():
    if not DSN:
        return
    # Destructive fixture setup is deliberately restricted to an explicit,
    # loopback-only disposable test database, not a Supabase project DSN.
    from psycopg.conninfo import conninfo_to_dict
    parsed = conninfo_to_dict(DSN)
    assert os.getenv('BEST_OPEN_ACK_DISPOSABLE') == 'yes'
    assert parsed.get('host') in {'127.0.0.1', 'localhost', 'postgres'}
    assert parsed.get('dbname') == 'best_open_test'
    with connection(autocommit=True) as c:
        c.execute('CREATE SCHEMA IF NOT EXISTS extensions')
        c.execute('CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA extensions')
        for role in ('anon', 'authenticated', 'service_role'):
            if not c.execute('SELECT 1 FROM pg_roles WHERE rolname=%s', (role,)).fetchone():
                c.execute(f'CREATE ROLE {role} NOLOGIN')
        c.execute('ALTER ROLE service_role BYPASSRLS')
        c.execute('DROP TABLE IF EXISTS budget_product_best_open_price_latest, budget_product_best_open_price_rows, budget_product_best_open_price_snapshots CASCADE')
        c.execute('DROP TABLE IF EXISTS budget_product_ranking_latest, budget_product_ranking_rows, budget_product_ranking_snapshots CASCADE')
        c.execute('''CREATE TABLE budget_product_ranking_snapshots (
            id uuid PRIMARY KEY, published_at timestamptz, market_date date,
            cohort_fingerprint text, eligible_cohort_count int, full_market_budget numeric,
            ranking_method_version text, allocation_method_version text, comparison_scope_version text,
            financial_rip_version text, overall_rip_version text, overall_rip_v12_version text,
            collector_appeal_version text, chase_accessibility_version text, chase_accessibility_transform_version text,
            ranked_under_v12_authority boolean)''')
        c.execute('''CREATE TABLE budget_product_ranking_latest (
            ranking_method_version text, allocation_method_version text, snapshot_id uuid,
            PRIMARY KEY(ranking_method_version, allocation_method_version))''')
        c.execute('''CREATE TABLE budget_product_ranking_rows (
            snapshot_id uuid, sealed_product_id uuid, set_id uuid, product_family text,
            source_calculation_run_id uuid, budget_type text, target_budget numeric,
            product_market_price numeric, quantity int, budget_rank_v12 int,
            overall_rip_v12_score numeric, financial_rip_v4_score numeric, collector_appeal_score numeric,
            chase_accessibility_raw numeric, chance_to_recover_capital numeric, actual_committed_capital numeric,
            PRIMARY KEY(snapshot_id, sealed_product_id, budget_type))''')
        c.execute(OLD.read_text())
        c.execute(NEW.read_text())


def fixture_payload():
    snap = dict(VERSIONS, built_at=T2, source_budget_snapshot_id=SID, source_budget_published_at=T1,
                source_market_date='2026-09-08', source_cohort_fingerprint='cohort-fixture',
                source_full_market_row_fingerprint='source-fixture', source_full_market_budget=100,
                source_eligible_cohort_count=3, best_open_price_method_version=METHOD,
                resolved_count=3, unresolved_count=0, runtime_seconds=1, diagnostics_json={})
    rows=[]
    for n in (1,2,3):
        bench=2 if n==1 else 1
        threshold=12.5 if n==1 else 8.0
        rows.append(dict(
            sealed_product_id=str(UUID(int=n)), set_id=str(UUID(int=10+n)), product_family='booster_box',
            source_calculation_run_id=str(UUID(int=20+n)), current_market_price=10, current_quantity=10,
            current_budget_rank=n, current_overall_rip_v12_score=90-n,
            current_financial_rip_v4_score=80-n, current_collector_appeal_score=70-n,
            current_chase_accessibility_raw=0.002, current_chance_to_recover_capital=0.5,
            current_actual_committed_capital=100, status='current_number_one_with_headroom' if n==1 else 'resolved_below_market',
            best_open_price=threshold, threshold_quantity=int(100//threshold),
            price_gap_dollars=10-threshold, price_gap_percent=(10-threshold)/10,
            benchmark_sealed_product_id=str(UUID(int=bench)), benchmark_overall_rip_v12_score=90-bench,
            benchmark_financial_rip_v4_score=80-bench, benchmark_chance_to_recover_capital=0.5,
            benchmark_actual_committed_capital=100, candidate_price_evaluations=10,
            bracket_expansions=2, bracket_refinements=2, monotonicity_fallback_count=0, search_wall_seconds=0.5))
    return snap, rows


@pytest.fixture(autouse=True)
def seed(database):
    if not DSN: return
    snap, rows=fixture_payload()
    with connection(autocommit=True) as c:
        c.execute('TRUNCATE budget_product_best_open_price_latest, budget_product_best_open_price_rows, budget_product_best_open_price_snapshots, budget_product_ranking_latest, budget_product_ranking_rows, budget_product_ranking_snapshots')
        cols=['id','published_at','market_date','cohort_fingerprint','eligible_cohort_count','full_market_budget']+list(VERSIONS)+['overall_rip_version','ranked_under_v12_authority']
        vals=[SID,T1,'2026-09-08','cohort-fixture',3,100]+list(VERSIONS.values())+[VERSIONS['overall_rip_v12_version'],True]
        c.execute('INSERT INTO budget_product_ranking_snapshots ('+','.join(cols)+') VALUES ('+','.join(['%s']*len(cols))+')', vals)
        c.execute('INSERT INTO budget_product_ranking_latest VALUES (%s,%s,%s)', (VERSIONS['ranking_method_version'],VERSIONS['allocation_method_version'],SID))
        for row in rows:
            c.execute('''INSERT INTO budget_product_ranking_rows VALUES
                (%s,%s,%s,%s,%s,'full_market',100,%s,%s,%s,%s,%s,%s,%s,%s,%s)''',
                (SID,row['sealed_product_id'],row['set_id'],row['product_family'],row['source_calculation_run_id'],
                 row['current_market_price'],row['current_quantity'],row['current_budget_rank'],
                 row['current_overall_rip_v12_score'],row['current_financial_rip_v4_score'],row['current_collector_appeal_score'],
                 row['current_chase_accessibility_raw'],row['current_chance_to_recover_capital'],row['current_actual_committed_capital']))


def publish(c, snap=None, rows=None):
    from psycopg.types.json import Jsonb
    if snap is None: snap, rows=fixture_payload()
    return c.execute('SELECT public.publish_budget_product_best_open_price_snapshot(%s,%s)', (Jsonb(snap),Jsonb(rows))).fetchone()[0]


def counts(c):
    return c.execute('SELECT (SELECT count(*) FROM budget_product_best_open_price_snapshots), (SELECT count(*) FROM budget_product_best_open_price_rows), (SELECT count(*) FROM budget_product_best_open_price_latest)').fetchone()


def test_happy_idempotency_row_order_and_different_content_refusal():
    import psycopg
    with connection(autocommit=True) as c:
        first=publish(c)
        snap, rows=fixture_payload()
        assert publish(c,snap,list(reversed(rows)))==first
        assert counts(c)==(1,3,1)
        rows[0]['search_wall_seconds']=0.6
        with pytest.raises(psycopg.Error,match='non-deterministic'):
            publish(c,snap,rows)
        assert counts(c)==(1,3,1)


@pytest.mark.parametrize('side,field',[
    ('current','financial_rip_v4_score'),('current','collector_appeal_score'),('current','chase_accessibility_raw'),
    ('current','chance_to_recover_capital'),('current','actual_committed_capital'),('current','overall_rip_v12_score'),
    ('benchmark','financial_rip_v4_score'),('benchmark','chance_to_recover_capital'),
    ('benchmark','actual_committed_capital'),('benchmark','overall_rip_v12_score')])
def test_actual_numeric_evidence_mismatches_rejected(side,field):
    import psycopg
    snap, rows=fixture_payload(); key=f'{side}_{field}'; rows[1][key]+=0.01
    with connection(autocommit=True) as c:
        with pytest.raises(psycopg.Error): publish(c,snap,rows)
        assert counts(c)==(0,0,0)


@pytest.mark.parametrize('kind',[
    'duplicate','missing','extra','wrong_source','wrong_run','wrong_family','wrong_rank','wrong_price',
    'noncent','zero','negative','noninteger_q','wrong_q','gap','gap_percent','self_benchmark','wrong_benchmark',
    'status','method','version','timestamp','cohort','budget','null','nan','unresolved'])
def test_rejection_matrix_rolls_back_and_leaves_latest_unchanged(kind):
    import psycopg
    snap, rows=fixture_payload()
    with connection(autocommit=True) as c:
        original=publish(c)
        if kind=='duplicate': rows[2]=deepcopy(rows[1])
        elif kind=='missing': rows.pop()
        elif kind=='extra': rows.append(dict(rows[-1],sealed_product_id=str(UUID(int=4))))
        elif kind=='wrong_source': snap['source_budget_snapshot_id']=str(UUID(int=101))
        elif kind=='wrong_run': rows[1]['source_calculation_run_id']=str(UUID(int=99))
        elif kind=='wrong_family': rows[1]['product_family']='wrong'
        elif kind=='wrong_rank': rows[1]['current_budget_rank']=5
        elif kind=='wrong_price': rows[1]['current_market_price']=11
        elif kind in ('noncent','zero','negative'): rows[1]['best_open_price']={'noncent':8.001,'zero':0,'negative':-1}[kind]
        elif kind in ('noninteger_q','wrong_q'): rows[1]['threshold_quantity']=12.5 if kind=='noninteger_q' else 9
        elif kind=='gap': rows[1]['price_gap_dollars']=7
        elif kind=='gap_percent': rows[1]['price_gap_percent']=0.75
        elif kind in ('self_benchmark','wrong_benchmark'):
            benchmark=rows[1] if kind=='self_benchmark' else rows[2]
            rows[1]['benchmark_sealed_product_id']=benchmark['sealed_product_id']
            for f in ('overall_rip_v12_score','financial_rip_v4_score','chance_to_recover_capital','actual_committed_capital'):
                rows[1]['benchmark_'+f]=benchmark['current_'+f]
        elif kind=='status': rows[1]['status']='current_number_one_with_headroom'
        elif kind=='method': snap['best_open_price_method_version']='wrong'
        elif kind=='version': snap['overall_rip_v12_version']='wrong'
        elif kind=='timestamp': snap['source_budget_published_at']=T2
        elif kind=='cohort': snap['source_cohort_fingerprint']='wrong'
        elif kind=='budget': snap['source_full_market_budget']=200
        elif kind=='null': rows[1]['current_financial_rip_v4_score']=None
        elif kind=='nan': rows[1]['current_financial_rip_v4_score']='NaN'
        elif kind=='unresolved': snap['unresolved_count']=1
        with pytest.raises(psycopg.Error): publish(c,snap,rows)
        assert counts(c)==(1,3,1)
        assert c.execute('SELECT snapshot_id FROM budget_product_best_open_price_latest').fetchone()[0]==original


def test_live_v12_flag_cannot_be_bypassed_by_matching_version_strings():
    import psycopg
    with connection(autocommit=True) as c:
        c.execute('UPDATE budget_product_ranking_snapshots SET ranked_under_v12_authority=false')
        with pytest.raises(psycopg.Error,match='V12'): publish(c)
        assert counts(c)==(0,0,0)


def wait_for_block(observer, application_name):
    deadline=time.monotonic()+10
    while time.monotonic()<deadline:
        blocked=observer.execute("SELECT EXISTS (SELECT 1 FROM pg_stat_activity WHERE application_name=%s AND wait_event_type='Lock')",(application_name,)).fetchone()[0]
        if blocked: return
        time.sleep(0.03)
    pytest.fail('publication did not actually block on the concurrent source lock')


def test_concurrent_same_id_republish_blocks_then_rejects_old_threshold():
    import psycopg
    # T2 is uncommitted when a second connection starts publication against T1.
    # The old unlocked function would publish a stale snapshot before T2 commits.
    with connection() as writer, connection(autocommit=True) as observer, ThreadPoolExecutor(max_workers=1) as pool:
        writer.execute('UPDATE budget_product_ranking_snapshots SET published_at=%s WHERE id=%s',(T2,SID))
        def competing():
            with connection(autocommit=True,application_name='best_open_race') as c:
                c.execute("SET statement_timeout='15s'")
                with pytest.raises(psycopg.Error,match='source binding'): publish(c)
        result=pool.submit(competing)
        try: wait_for_block(observer,'best_open_race')
        finally: writer.commit()
        result.result(timeout=15)
        assert counts(observer)==(0,0,0)


def test_two_concurrent_identical_publishers_return_one_snapshot():
    with connection() as first, connection(autocommit=True) as observer, ThreadPoolExecutor(max_workers=1) as pool:
        snapshot=publish(first) # transaction deliberately remains open
        def competing():
            with connection(autocommit=True,application_name='best_open_dupe') as c:
                return publish(c)
        second=pool.submit(competing)
        try: wait_for_block(observer,'best_open_dupe')
        finally: first.commit()
        assert second.result(timeout=15)==snapshot
        assert counts(observer)==(1,3,1)


@pytest.mark.parametrize('role',['anon','authenticated'])
def test_real_roles_cannot_read_write_or_execute(role):
    import psycopg
    with connection(autocommit=True) as c:
        c.execute(f'SET ROLE {role}')
        for table in ('snapshots','rows','latest'):
            with pytest.raises(psycopg.Error): c.execute(f'SELECT * FROM budget_product_best_open_price_{table}')
        with pytest.raises(psycopg.Error): publish(c)


def test_service_role_can_execute_and_rls_is_enabled_without_public_policies():
    with connection(autocommit=True) as c:
        assert c.execute("SELECT count(*) FROM pg_class WHERE relname LIKE 'budget_product_best_open_price_%' AND relkind='r' AND relrowsecurity").fetchone()[0]==3
        assert c.execute("SELECT count(*) FROM pg_policies WHERE tablename LIKE 'budget_product_best_open_price_%'").fetchone()[0]==0
        c.execute('SET ROLE service_role')
        assert publish(c) is not None


@pytest.mark.parametrize('field',[key for key in VERSIONS if key!='overall_rip_v12_version'])
def test_mutually_matching_but_unsupported_live_model_is_rejected(field):
    import psycopg
    snap, rows=fixture_payload(); snap[field]='unsupported-model'
    with connection(autocommit=True) as c:
        c.execute(f'UPDATE budget_product_ranking_snapshots SET {field}=%s',('unsupported-model',))
        # Keep latest pointer selectors matching so this reaches the model gate.
        if field in ('ranking_method_version','allocation_method_version'):
            c.execute(f'UPDATE budget_product_ranking_latest SET {field}=%s',('unsupported-model',))
        with pytest.raises(psycopg.Error): publish(c,snap,rows)
        assert counts(c)==(0,0,0)
