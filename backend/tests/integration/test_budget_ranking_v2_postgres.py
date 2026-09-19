"""Real PostgreSQL tests for the Budget Product Ranking V2 publication branch.

Builds the REAL ranking migration chain (not a hand-made schema) on an isolated
loopback ``best_open_test`` database, then applies the V2 migration. CI provides
postgres:17; local runs need an explicit DSN and acknowledgement, otherwise the suite
skips rather than inventing DB passes. Never use production.
"""
from copy import deepcopy
import json
import os
from pathlib import Path

import pytest

# Deliberately no backend engine imports: the CI Postgres job installs only pytest and
# psycopg. Identity literals are pinned to the Python constants by a unit test
# (test_budget_v2_v3_publication_payloads.py), so drift is still caught.
RANKING_V2_IDENTITY = {
    'ranking_method_version': 'budget_product_ranking_v2',
    'allocation_method_version': 'budget_allocation_floor_quantity_v1',
    'comparison_scope_version': 'budget_constrained_whole_unit_cross_format_v1',
    'financial_rip_version': 'financial_rip_v5_shortfall_resilience_25_20_15_25_10_5',
    'financial_rip_v5_version': 'financial_rip_v5_shortfall_resilience_25_20_15_25_10_5',
    'overall_rip_version': 'overall_rip_v14_86_financial_v5_04_chase_accessibility_v1_10_collector_appeal_v5',
    'overall_rip_v14_version': 'overall_rip_v14_86_financial_v5_04_chase_accessibility_v1_10_collector_appeal_v5',
    'collector_appeal_version': 'collector_appeal_v5_contextual_roster_h_only_d_baseline_up4_down2',
    'chase_accessibility_version': 'chase_accessibility_v1_hc_value_squared_modeled_probability',
    'chase_accessibility_transform_version': 'chase_accessibility_overall_score_v1_saturating_k002',
}

DSN = os.getenv('BEST_OPEN_TEST_DATABASE_URL')
pytestmark = pytest.mark.skipif(not DSN, reason='isolated PostgreSQL DSN required')
ROOT = Path(__file__).resolve().parents[3]
SUPA = ROOT / 'supabase/migrations'
BACK = ROOT / 'backend/db/migrations'
CHAIN = [
    SUPA / '20260823193538_20260822213027_create_budget_normalized_product_rankings.sql',
    SUPA / '20260824025349_strengthen_budget_product_ranking_publication.sql',
    SUPA / '20260825154658_expose_budget_product_strategy_expected_value.sql',
    BACK / '20260902010000_add_budget_product_ranking_v12_authority_columns.sql',
    BACK / '20260903224637_extend_budget_product_ranking_publication_rpc_v12_atomic.sql',
    SUPA / '20260915233000_add_budget_opening_profile_strategy_metrics.sql',
]
V2_MIGRATION = BACK / '20260920120000_add_budget_product_ranking_v2_v5_v14.sql'
V2_MIGRATION_SUPA = SUPA / '20260920120000_add_budget_product_ranking_v2_v5_v14.sql'
V1 = 'budget_product_ranking_v1'
V2 = 'budget_product_ranking_v2'
ALLOC = 'budget_allocation_floor_quantity_v1'
PRICE_DATE = '2026-09-14'
PIDS = [f'00000000-0000-0000-0000-00000000{n:04d}' for n in range(1, 5)]
RUN = '00000000-0000-0000-0000-0000000000aa'
SET = '00000000-0000-0000-0000-0000000000bb'
BUDGET = 1300.0


def connection(**kwargs):
    import psycopg
    return psycopg.connect(DSN, **kwargs)


def reset_database():
    from psycopg.conninfo import conninfo_to_dict
    parsed = conninfo_to_dict(DSN)
    assert os.getenv('BEST_OPEN_ACK_DISPOSABLE') == 'yes'
    assert parsed.get('host') in {'127.0.0.1', 'localhost', 'postgres'}
    assert parsed.get('dbname') == 'best_open_test'
    with connection(autocommit=True) as c:
        c.execute('DROP SCHEMA IF EXISTS public CASCADE')
        c.execute('CREATE SCHEMA public')
        c.execute('CREATE SCHEMA IF NOT EXISTS extensions')
        c.execute('CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA extensions')
        for role in ('anon', 'authenticated', 'service_role'):
            if not c.execute('SELECT 1 FROM pg_roles WHERE rolname=%s', (role,)).fetchone():
                c.execute(f'CREATE ROLE {role} NOLOGIN')
        c.execute('ALTER ROLE service_role BYPASSRLS')
        c.execute('GRANT USAGE ON SCHEMA public TO anon, authenticated, service_role')


def apply(path: Path):
    with connection(autocommit=True) as c:
        c.execute(path.read_text(encoding='utf-8'))


@pytest.fixture(scope='module', autouse=True)
def database():
    if not DSN:
        return
    reset_database()
    for path in CHAIN:
        apply(path)
    apply(V2_MIGRATION)


def v2_payload(market_date='2026-09-14'):
    snapshot = {
        **RANKING_V2_IDENTITY, 'ranked_under_v14_authority': True, 'market_date': market_date,
        'built_at': '2026-09-15T00:00:00+00:00', 'pinned_price_as_of': PRICE_DATE,
        'eligible_cohort_count': len(PIDS), 'cohort_fingerprint': 'fp-v2', 'full_market_budget': BUDGET,
        'max_eligible_sku_price': 1299.0, 'full_market_rounding_increment': 50.0,
        'full_market_rounding_rule_version': 'full_market_next_50_above_max_eligible_sku_v1',
        'diagnostics_json': {},
    }
    rows = []
    for i, pid in enumerate(PIDS):
        committed = 1200.0 + 10 * i
        rows.append({
            'sealed_product_id': pid, 'set_id': SET, 'product_family': 'booster_box',
            'target_budget': BUDGET, 'budget_type': 'full_market', 'quantity': 4 + i,
            'actual_committed_capital': committed, 'unused_capital': BUDGET - committed,
            'unused_capital_percent': (BUDGET - committed) / BUDGET, 'capital_utilization': committed / BUDGET,
            'financial_rip_v5_score': 50.0 - i, 'financial_rip_v5_status': 'ready',
            'financial_rip_v5_rankable': True, 'overall_rip_v14_score': 55.0 - 2 * i,
            'overall_rip_v14_status': 'ready', 'overall_rip_v14_rankable': True,
            'budget_rank_v14': i + 1, 'budget_cohort_size_v14': len(PIDS), 'budget_tier_v14': 'B',
            'financial_only_rank_v5': i + 1, 'collector_appeal_score': 60.0,
            'chase_accessibility_raw': 0.01, 'chance_to_recover_capital': 0.05,
            'expected_value': 700.0 + i, 'median_value': 690.0 + i, 'top1_outcome_value_share': 0.2,
            'product_market_price': 250.0 + i, 'price_as_of': PRICE_DATE, 'full_market_anchor': BUDGET,
            'max_eligible_sku_price': 1299.0, 'full_market_rounding_rule': 'ceil(max / 50) * 50',
            'full_market_rounding_increment': 50.0,
            'full_market_rounding_rule_version': 'full_market_next_50_above_max_eligible_sku_v1',
            'source_calculation_run_id': RUN,
        })
    return snapshot, rows


def v1_payload(market_date='2026-09-14'):
    snapshot = dict(
        market_date=market_date, built_at='2026-09-15T00:00:00+00:00', ranking_method_version=V1,
        allocation_method_version=ALLOC, comparison_scope_version='budget_constrained_whole_unit_cross_format_v1',
        financial_rip_version='financial_rip_v4_outcome_profile_p95_only_25_20_15_25_10_5',
        overall_rip_version='overall_rip_v10_90_financial_v4_10_collector_appeal_v5',
        collector_appeal_version=RANKING_V2_IDENTITY['collector_appeal_version'],
        eligible_cohort_count=len(PIDS), cohort_fingerprint='fp-v1', pinned_price_as_of=PRICE_DATE,
        full_market_budget=BUDGET, max_eligible_sku_price=1299.0, full_market_rounding_increment=50.0,
        full_market_rounding_rule_version='full_market_next_50_above_max_eligible_sku_v1')
    rows = []
    for i, pid in enumerate(PIDS):
        rows.append(dict(
            sealed_product_id=pid, set_id=SET, product_family='booster_box', target_budget=BUDGET,
            budget_type='full_market', quantity=4 + i, actual_committed_capital=1200.0 + 10 * i,
            unused_capital=100.0 - 10 * i, unused_capital_percent=(100.0 - 10 * i) / BUDGET,
            capital_utilization=(1200.0 + 10 * i) / BUDGET, budget_rank=i + 1, budget_cohort_size=len(PIDS),
            budget_tier='B', financial_only_rank=i + 1, financial_rip_v4_score=45.0 - i,
            overall_rip_v10_score=50.0 - i, collector_appeal_score=60.0, chance_to_recover_capital=0.05,
            product_market_price=250.0 + i, price_as_of=PRICE_DATE, full_market_anchor=BUDGET,
            max_eligible_sku_price=1299.0, full_market_rounding_rule='r', full_market_rounding_increment=50.0,
            full_market_rounding_rule_version='full_market_next_50_above_max_eligible_sku_v1',
            source_calculation_run_id=RUN, expected_value=700.0, median_value=690.0,
            top1_outcome_value_share=0.2))
    return snapshot, rows


def publish(snapshot, rows, *, role=None):
    with connection() as c:
        if role:
            c.execute(f'SET LOCAL ROLE {role}')
        return c.execute('SELECT public.publish_budget_product_ranking_snapshot(%s::jsonb, %s::jsonb)',
                         (json.dumps(snapshot), json.dumps(rows))).fetchone()[0]


def q(sql, params=()):
    with connection() as c:
        return c.execute(sql, params).fetchall()


def state():
    return (q('SELECT count(*) FROM budget_product_ranking_snapshots')[0][0],
            q('SELECT count(*) FROM budget_product_ranking_rows')[0][0],
            sorted(q('SELECT ranking_method_version, snapshot_id::text FROM budget_product_ranking_latest')))


def test_v1_publish_still_works_and_v2_absent_columns_are_null():
    snap, rows = v1_payload()
    sid = publish(snap, rows)
    assert q('SELECT ranking_method_version, ranked_under_v14_authority, financial_rip_v5_version '
             'FROM budget_product_ranking_snapshots WHERE id=%s', (sid,)) == [(V1, None, None)]
    assert q('SELECT count(*), count(financial_rip_v5_score), min(financial_only_rank) '
             'FROM budget_product_ranking_rows WHERE snapshot_id=%s', (sid,)) == [(4, 0, 1)]
    assert q('SELECT ranking_method_version FROM budget_product_ranking_latest') == [(V1,)]


def test_v1_rejects_v5_v14_fields_and_null_legacy_ranks():
    snap, rows = v1_payload()
    before = state()
    bad = deepcopy(rows); bad[0]['financial_rip_v5_score'] = 40.0
    with pytest.raises(Exception, match='require ranking_method_version budget_product_ranking_v2'):
        publish(snap, bad)
    bad_snap = {**snap, 'overall_rip_v14_version': RANKING_V2_IDENTITY['overall_rip_v14_version']}
    with pytest.raises(Exception, match='require ranking_method_version budget_product_ranking_v2'):
        publish(bad_snap, rows)
    bad = deepcopy(rows); bad[0]['budget_rank'] = None
    with pytest.raises(Exception):
        publish(snap, bad)
    assert state() == before


def test_v2_publish_persists_versioned_evidence_and_moves_only_v2_pointer():
    v1_before = q("SELECT snapshot_id::text FROM budget_product_ranking_latest WHERE ranking_method_version=%s", (V1,))
    snap, rows = v2_payload()
    sid = publish(snap, rows)
    s = q('SELECT ranking_method_version, financial_rip_version, financial_rip_v5_version, overall_rip_version, '
          'overall_rip_v14_version, ranked_under_v14_authority, chase_accessibility_version, '
          'chase_accessibility_transform_version, collector_appeal_version, eligible_cohort_count, '
          'overall_rip_v12_version, ranked_under_v12_authority FROM budget_product_ranking_snapshots WHERE id=%s', (sid,))[0]
    assert s[0] == V2 and s[2] == RANKING_V2_IDENTITY['financial_rip_v5_version'] and s[5] is True
    assert s[10] is None and s[11] is None  # never V12 metadata
    r = q('SELECT budget_rank_v14, budget_cohort_size_v14, financial_only_rank_v5, budget_tier_v14, '
          'financial_rip_v5_score, overall_rip_v14_score, budget_rank, financial_only_rank, '
          'financial_rip_v4_score, overall_rip_v12_score, chase_accessibility_raw, chance_to_recover_capital, '
          'expected_value FROM budget_product_ranking_rows WHERE snapshot_id=%s ORDER BY budget_rank_v14', (sid,))
    assert [x[0] for x in r] == [1, 2, 3, 4] and {x[1] for x in r} == {4}
    assert all(x[6] is None and x[7] is None and x[8] is None and x[9] is None for x in r)
    assert sorted(x[2] for x in r) == [1, 2, 3, 4] and float(r[0][4]) == 50.0 and float(r[0][5]) == 55.0
    latest = dict(q('SELECT ranking_method_version, snapshot_id::text FROM budget_product_ranking_latest'))
    assert latest[V2] == str(sid) and [(latest[V1],)] == v1_before


def test_v2_republish_same_date_replaces_atomically():
    snap, rows = v2_payload()
    sid = publish(snap, rows)
    assert q('SELECT count(*) FROM budget_product_ranking_snapshots WHERE ranking_method_version=%s', (V2,)) == [(1,)]
    assert q('SELECT count(*) FROM budget_product_ranking_rows WHERE snapshot_id=%s', (sid,)) == [(4,)]


def _mut(fn, match, snap_fn=None):
    snap, rows = v2_payload()
    rows = deepcopy(rows)
    fn(rows) if fn else None
    if snap_fn:
        snap_fn(snap)
    before = state()
    with pytest.raises(Exception, match=match):
        publish(snap, rows)
    assert state() == before  # nothing persisted, pointers unmoved


@pytest.mark.parametrize('name,fn,snap_fn,match', [
    ('empty', lambda r: r.clear(), None, 'empty'),
    ('wrong_financial', None, lambda s: s.update(financial_rip_version='financial_rip_v4_outcome_profile_p95_only_25_20_15_25_10_5'), 'authority metadata'),
    ('wrong_v5_version', None, lambda s: s.update(financial_rip_v5_version='x'), 'authority metadata'),
    ('wrong_overall', None, lambda s: s.update(overall_rip_version='overall_rip_v12_86_financial_v4_04_chase_accessibility_v1_10_collector_appeal_v5'), 'authority metadata'),
    ('wrong_collector', None, lambda s: s.update(collector_appeal_version='collector_appeal_v7'), 'authority metadata'),
    ('wrong_chase', None, lambda s: s.update(chase_accessibility_version='x'), 'authority metadata'),
    ('wrong_transform', None, lambda s: s.update(chase_accessibility_transform_version='x'), 'authority metadata'),
    ('wrong_allocation', None, lambda s: s.update(allocation_method_version='other'), 'authority metadata'),
    ('not_ranked_under_v14', None, lambda s: s.update(ranked_under_v14_authority=False), 'authority metadata'),
    ('v12_snapshot_fields', None, lambda s: s.update(overall_rip_v12_version='v12'), 'V12 authority'),
    ('row_v4', lambda r: r[0].update(financial_rip_v4_score=40.0), None, 'mixed model generations'),
    ('row_v12', lambda r: r[0].update(overall_rip_v12_score=40.0), None, 'mixed model generations'),
    ('row_legacy_rank', lambda r: r[0].update(financial_only_rank=1), None, 'mixed model generations'),
    ('missing_v14', lambda r: r[0].update(overall_rip_v14_score=None), None, 'missing required'),
    ('missing_chase', lambda r: r[0].update(chase_accessibility_raw=None), None, 'missing required'),
    ('unranked', lambda r: r[0].update(overall_rip_v14_rankable=False), None, 'missing required'),
    ('v5_out_of_range', lambda r: r[0].update(financial_rip_v5_score=101.0), None, 'out-of-range'),
    ('pwin_out_of_range', lambda r: r[0].update(chance_to_recover_capital=1.5), None, 'out-of-range'),
    ('rank_gt_cohort', lambda r: r[0].update(budget_rank_v14=9), None, 'out-of-range'),
    ('nonfinite_json', lambda r: r[0].update(expected_value=float('nan')), None, 'json'),
    ('nonfinite_string', lambda r: r[0].update(expected_value='NaN'), None, 'non-finite'),
    ('infinity_string', lambda r: r[0].update(financial_rip_v5_score='Infinity'), None, 'non-finite'),
    ('duplicate', lambda r: r.append(deepcopy(r[0])), None, 'duplicate'),
    ('price_authority', lambda r: r[0].update(price_as_of='2026-09-13'), None, 'mixed price authority'),
    ('rank_gap', lambda r: r[0].update(budget_rank_v14=4), None, 'contiguity'),
    ('financial_rank_gap', lambda r: r[1].update(financial_only_rank_v5=r[0]['financial_only_rank_v5']), None, 'contiguity'),
    ('cohort_count', None, lambda s: s.update(eligible_cohort_count=9), 'Full Market count|cohort'),
    ('capital_recon', lambda r: r[0].update(unused_capital=5.0), None, 'check constraint'),
])
def test_v2_rejection_matrix_is_atomic(name, fn, snap_fn, match):
    _mut(fn, match, snap_fn)


def test_v2_rows_must_be_array_and_snapshot_object():
    snap, rows = v2_payload()
    with pytest.raises(Exception, match='array'):
        publish(snap, {'a': 1})
    with pytest.raises(Exception, match='object'):
        publish([snap], rows)


def test_table_check_rejects_mixed_shape_rows_even_with_direct_service_role_insert():
    sid = q('SELECT snapshot_id::text FROM budget_product_ranking_latest WHERE ranking_method_version=%s', (V2,))[0][0]
    with connection() as c:
        c.execute('SET LOCAL ROLE service_role')
        with pytest.raises(Exception, match='budget_ranking_rows_authority_shape'):
            c.execute('UPDATE budget_product_ranking_rows SET financial_rip_v4_score = 1 WHERE snapshot_id=%s', (sid,))
    with connection() as c:
        c.execute('SET LOCAL ROLE service_role')
        with pytest.raises(Exception, match='budget_ranking_snapshots_v2_authority_shape'):
            c.execute('UPDATE budget_product_ranking_snapshots SET ranked_under_v14_authority = FALSE WHERE id=%s', (sid,))


@pytest.mark.parametrize('role', ['anon', 'authenticated'])
def test_api_roles_cannot_execute_or_touch_v2(role):
    snap, rows = v2_payload()
    for fn in ('publish_budget_product_ranking_snapshot', 'publish_budget_product_ranking_snapshot_v2',
               'publish_budget_product_ranking_snapshot_v1_v12'):
        with pytest.raises(Exception, match='permission denied'):
            publish_named(fn, snap, rows, role)
    with connection() as c:
        c.execute(f'SET LOCAL ROLE {role}')
        with pytest.raises(Exception, match='permission denied'):
            c.execute('SELECT count(*) FROM budget_product_ranking_rows')


def publish_named(fn, snap, rows, role):
    with connection() as c:
        c.execute(f'SET LOCAL ROLE {role}')
        return c.execute(f'SELECT public.{fn}(%s::jsonb, %s::jsonb)', (json.dumps(snap), json.dumps(rows))).fetchone()[0]


def test_service_role_executes_dispatcher_only():
    snap, rows = v2_payload()
    assert publish(snap, rows, role='service_role')
    for fn in ('publish_budget_product_ranking_snapshot_v2', 'publish_budget_product_ranking_snapshot_v1_v12'):
        with pytest.raises(Exception, match='permission denied'):
            publish_named(fn, snap, rows, 'service_role')


def test_migration_is_mirrored_and_additive():
    assert V2_MIGRATION.read_text(encoding='utf-8') == V2_MIGRATION_SUPA.read_text(encoding='utf-8')
    body = V2_MIGRATION.read_text(encoding='utf-8').split('-- ROLLBACK')[-1] if False else V2_MIGRATION.read_text(encoding='utf-8')
    upper = body.upper()
    assert 'DROP TABLE' not in upper and 'DROP COLUMN' not in upper.replace('-- ROLLBACK: DROP THE V2 COLUMNS', '')
    assert 'ALTER COLUMN BUDGET_RANK DROP NOT NULL' in ' '.join(upper.split())
