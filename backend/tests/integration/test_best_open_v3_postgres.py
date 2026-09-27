"""Real PostgreSQL migration-chain and publication tests for Best-Open Price V3.

Starts from the V1-shaped store (what production has today), publishes V1, applies the
pending V2 migration, publishes V2, applies the V3 migration, and proves V1/V2 remain
intact and re-publishable while V3 publishes against a Ranking V2 source. The ranking
tables are the REAL migration chain (including the Ranking V2 migration), not a
hand-made schema. CI provides postgres:17; local runs need an explicit DSN and
acknowledgement, otherwise the suite skips. Never use production.
"""
from copy import deepcopy
import json
import os

import pytest

from backend.tests.integration import _ranking_fixtures as fx

DSN = os.getenv('BEST_OPEN_TEST_DATABASE_URL')
pytestmark = pytest.mark.skipif(not DSN, reason='isolated PostgreSQL DSN required')

M1 = 'budget_product_best_open_price_full_market_v1'
M2 = 'budget_product_best_open_price_full_market_v2_dual_financial_v4_overall_v12'
M3 = 'budget_product_best_open_price_full_market_v3_dual_financial_v5_overall_v14'
TH = [210.0, 240.0, 290.0, 350.0]
TQ = [int(fx.BUDGET // t) for t in TH]
CAP = [q * t for q, t in zip(TQ, TH)]
V3_ONLY_ROW_KEYS = (
    'current_overall_rip_v14_score', 'current_financial_rip_v5_score', 'current_financial_only_rank_v5',
    'benchmark_overall_rip_v14_score', 'benchmark_financial_rip_v5_score', 'threshold_financial_rip_v5_score',
    'threshold_overall_rip_v14_score', 'financial_benchmark_financial_rip_v5_score',
    'financial_benchmark_overall_rip_v14_score', 'financial_threshold_financial_rip_v5_score',
    'financial_threshold_overall_rip_v14_score', 'threshold_exact_verified',
    'financial_threshold_exact_verified')


def connection(**kwargs):
    return fx.connection(DSN, **kwargs)


def q(sql, params=()):
    with connection() as c:
        return c.execute(sql, params).fetchall()


def rank_publish(payload):
    snap, rows = payload
    with connection() as c:
        return c.execute('SELECT public.publish_budget_product_ranking_snapshot(%s::jsonb,%s::jsonb)',
                         (json.dumps(snap), json.dumps(rows))).fetchone()[0]


def live(method):
    sid, published, market_date, fp = q(
        'SELECT s.id::text, s.published_at, s.market_date, s.cohort_fingerprint '
        'FROM budget_product_ranking_latest l JOIN budget_product_ranking_snapshots s ON s.id=l.snapshot_id '
        'WHERE l.ranking_method_version=%s', (method,))[0]
    return dict(id=sid, published_at=published.isoformat(), market_date=str(market_date), fingerprint=fp)


def bo_snapshot(kind, src):
    base = dict(
        built_at='2026-09-16T00:00:00+00:00', source_budget_snapshot_id=src['id'],
        source_budget_published_at=src['published_at'], source_market_date=src['market_date'],
        source_cohort_fingerprint=src['fingerprint'], source_full_market_row_fingerprint='src-fp',
        source_full_market_budget=fx.BUDGET, source_eligible_cohort_count=len(fx.PIDS),
        resolved_count=len(fx.PIDS), unresolved_count=0, runtime_seconds=1, diagnostics_json={},
        allocation_method_version=fx.ALLOC, comparison_scope_version=fx.SCOPE,
        collector_appeal_version=fx.COLLECTOR, chase_accessibility_version=fx.CHASE,
        chase_accessibility_transform_version=fx.TRANSFORM)
    if kind == 3:
        return dict(base, ranking_method_version=fx.V2, financial_rip_version=fx.FIN_V5,
                    overall_rip_v14_version=fx.OVERALL_V14, best_open_price_method_version=M3)
    return dict(base, ranking_method_version=fx.V1, financial_rip_version=fx.FIN_V4,
                overall_rip_v12_version=fx.OVERALL_V12,
                best_open_price_method_version=M1 if kind == 1 else M2)


def bo_rows(kind):
    rows = []
    for i, pid in enumerate(fx.PIDS):
        b = 1 if i == 0 else 0
        gap = fx.PRICES[i] - TH[i]
        status = 'current_number_one_with_headroom' if i == 0 else 'resolved_below_market'
        row = dict(
            sealed_product_id=pid, set_id=fx.SET, product_family='booster_box', source_calculation_run_id=fx.RUN,
            current_market_price=fx.PRICES[i], current_quantity=fx.QTY[i], current_budget_rank=i + 1,
            current_collector_appeal_score=60.0, current_chase_accessibility_raw=0.01,
            current_chance_to_recover_capital=0.05, current_actual_committed_capital=fx.COMMITTED[i],
            status=status, best_open_price=TH[i], threshold_quantity=TQ[i], price_gap_dollars=gap,
            price_gap_percent=gap / fx.PRICES[i], benchmark_sealed_product_id=fx.PIDS[b],
            benchmark_chance_to_recover_capital=0.05, benchmark_actual_committed_capital=fx.COMMITTED[b],
            candidate_price_evaluations=10, bracket_expansions=0, bracket_refinements=0,
            monotonicity_fallback_count=0, search_wall_seconds=0.5)
        if kind == 3:
            row.update(
                current_overall_rip_v14_score=55.0 - 2 * i, current_financial_rip_v5_score=50.0 - i,
                current_financial_only_rank_v5=i + 1,
                benchmark_overall_rip_v14_score=55.0 - 2 * b, benchmark_financial_rip_v5_score=50.0 - b,
                threshold_financial_rip_v5_score=50.0, threshold_overall_rip_v14_score=55.0 - 2 * b + 0.5,
                financial_benchmark_financial_rip_v5_score=50.0 - b,
                financial_benchmark_overall_rip_v14_score=55.0 - 2 * b,
                financial_threshold_financial_rip_v5_score=50.0 - b + 0.5,
                financial_threshold_overall_rip_v14_score=54.0,
                threshold_exact_verified=True, financial_threshold_exact_verified=True)
        else:
            row.update(current_overall_rip_v12_score=52.0 - i, current_financial_rip_v4_score=45.0 - i,
                       benchmark_overall_rip_v12_score=52.0 - b, benchmark_financial_rip_v4_score=45.0 - b)
        if kind >= 2:
            row.update(
                financial_status=status, financial_best_open_price=TH[i], financial_threshold_quantity=TQ[i],
                financial_price_gap_dollars=gap, financial_price_gap_percent=gap / fx.PRICES[i],
                financial_benchmark_sealed_product_id=fx.PIDS[b],
                threshold_chance_to_recover_capital=0.05, threshold_actual_committed_capital=CAP[i],
                financial_threshold_chance_to_recover_capital=0.05,
                financial_threshold_actual_committed_capital=CAP[i])
        if kind == 2:
            row.update(
                current_financial_only_rank=i + 1, financial_benchmark_financial_rip_v4_score=45.0 - b,
                financial_benchmark_overall_rip_v12_score=52.0 - b,
                threshold_financial_rip_v4_score=45.0 - i, threshold_overall_rip_v12_score=52.0 - i,
                financial_threshold_financial_rip_v4_score=45.0 - i,
                financial_threshold_overall_rip_v12_score=52.0 - i)
        rows.append(row)
    return rows


def bo_publish(snap, rows, *, role=None, fn='publish_budget_product_best_open_price_snapshot'):
    with connection() as c:
        if role:
            c.execute(f'SET LOCAL ROLE {role}')
        return c.execute(f'SELECT public.{fn}(%s::jsonb,%s::jsonb)',
                         (json.dumps(snap), json.dumps(rows))).fetchone()[0]


def bo_state():
    return (q('SELECT count(*) FROM budget_product_best_open_price_snapshots')[0][0],
            q('SELECT count(*) FROM budget_product_best_open_price_rows')[0][0],
            sorted(q('SELECT best_open_price_method_version, snapshot_id::text '
                     'FROM budget_product_best_open_price_latest')))


def stored_rows(snapshot_id):
    return q('SELECT to_jsonb(r) - %s - %s FROM budget_product_best_open_price_rows r '
             'WHERE snapshot_id=%s ORDER BY sealed_product_id', ('id', 'snapshot_id', snapshot_id))


def assert_preserved(after, before):
    """Every pre-migration column value is unchanged; every newly added column is NULL."""
    assert len(after) == len(before)
    for (a,), (b,) in zip(after, before):
        assert {k: a[k] for k in b} == b
        assert all(a[k] is None for k in a if k not in b)


@pytest.fixture(scope='module')
def chain():
    if not DSN:
        return None
    fx.reset_database(DSN)
    for path in fx.RANKING_CHAIN + [fx.RANKING_V2_MIGRATION, fx.BEST_OPEN_V1_STORE, fx.BEST_OPEN_V1_HARDEN]:
        fx.apply(DSN, path)
    rank_publish(fx.ranking_v1_v12_payload())
    rank_publish(fx.ranking_v2_payload())
    src1, src2 = live(fx.V1), live(fx.V2)
    ev = dict(src1=src1, src2=src2)

    # Stage A: V1-shaped production store.
    assert not q("SELECT 1 FROM information_schema.columns WHERE table_name='budget_product_best_open_price_rows' "
                 "AND column_name IN ('financial_status','current_overall_rip_v14_score')")
    ev['id1'] = bo_publish(bo_snapshot(1, src1), bo_rows(1))
    ev['v1_rows_stage_a'] = stored_rows(ev['id1'])

    # Stage B: pending V2 migration.
    fx.apply(DSN, fx.BEST_OPEN_V2)
    assert_preserved(stored_rows(ev['id1']), ev['v1_rows_stage_a'])
    assert bo_publish(bo_snapshot(1, src1), bo_rows(1)) == ev['id1']
    ev['id2'] = bo_publish(bo_snapshot(2, src1), bo_rows(2))
    ev['v2_rows_stage_b'] = stored_rows(ev['id2'])

    # Stage C: V3 migration.
    fx.apply(DSN, fx.BEST_OPEN_V3)
    ev['after_v3_v1_rows'] = stored_rows(ev['id1'])
    ev['after_v3_v2_rows'] = stored_rows(ev['id2'])
    ev['repub1'] = bo_publish(bo_snapshot(1, src1), bo_rows(1))
    ev['repub2'] = bo_publish(bo_snapshot(2, src1), bo_rows(2))
    ev['id3'] = bo_publish(bo_snapshot(3, src2), bo_rows(3))
    return ev


def test_v1_v2_v3_chain_preserves_v1_and_v2_and_publishes_v3(chain):
    assert len({chain['id1'], chain['id2'], chain['id3']}) == 3
    assert_preserved(chain['after_v3_v1_rows'], chain['v1_rows_stage_a'])
    assert_preserved(chain['after_v3_v2_rows'], chain['v2_rows_stage_b'])
    assert chain['repub1'] == chain['id1'] and chain['repub2'] == chain['id2']
    assert dict(q('SELECT best_open_price_method_version, snapshot_id::text FROM budget_product_best_open_price_latest')) == {
        M1: str(chain['id1']), M2: str(chain['id2']), M3: str(chain['id3'])}


def test_v1_v2_rows_never_carry_v3_evidence(chain):
    for key in ('id1', 'id2'):
        r = q('SELECT count(*), count(current_overall_rip_v14_score), count(threshold_exact_verified), '
              'count(benchmark_overall_rip_v12_score) FROM budget_product_best_open_price_rows WHERE snapshot_id=%s',
              (chain[key],))
        assert r == [(4, 0, 0, 4)]
        assert q('SELECT overall_rip_v12_version, overall_rip_v14_version FROM budget_product_best_open_price_snapshots '
                 'WHERE id=%s', (chain[key],)) == [(fx.OVERALL_V12, None)]


def test_v3_snapshot_and_rows_are_truthfully_versioned(chain):
    s = q('SELECT ranking_method_version, allocation_method_version, comparison_scope_version, financial_rip_version, '
          'overall_rip_v14_version, overall_rip_v12_version, collector_appeal_version, chase_accessibility_version, '
          'chase_accessibility_transform_version, best_open_price_method_version, source_budget_snapshot_id::text '
          'FROM budget_product_best_open_price_snapshots WHERE id=%s', (chain['id3'],))[0]
    assert s == (fx.V2, fx.ALLOC, fx.SCOPE, fx.FIN_V5, fx.OVERALL_V14, None, fx.COLLECTOR, fx.CHASE,
                 fx.TRANSFORM, M3, chain['src2']['id'])
    r = q('SELECT current_budget_rank, current_overall_rip_v14_score, current_financial_rip_v5_score, '
          'current_financial_only_rank_v5, threshold_overall_rip_v14_score, financial_threshold_financial_rip_v5_score, '
          'threshold_exact_verified, financial_threshold_exact_verified, current_overall_rip_v12_score, '
          'current_financial_rip_v4_score, benchmark_overall_rip_v12_score, benchmark_financial_rip_v4_score, '
          'current_financial_only_rank, threshold_overall_rip_v12_score FROM budget_product_best_open_price_rows '
          'WHERE snapshot_id=%s ORDER BY current_budget_rank', (chain['id3'],))
    assert [x[0] for x in r] == [1, 2, 3, 4] and float(r[0][1]) == 55.0 and float(r[0][2]) == 50.0
    assert all(x[6] is True and x[7] is True for x in r)
    assert all(v is None for x in r for v in x[8:])


def test_v3_republish_is_idempotent_and_changed_content_is_refused(chain):
    snap, rows = bo_snapshot(3, chain['src2']), bo_rows(3)
    before = bo_state()
    assert bo_publish(snap, list(reversed(rows))) == chain['id3']
    changed = deepcopy(rows); changed[0]['search_wall_seconds'] = 0.6
    with pytest.raises(Exception, match='non-deterministic'):
        bo_publish(snap, changed)
    assert bo_state() == before


def _bad(chain, fn=None, snap_fn=None, kind=3, match=None):
    snap, rows = bo_snapshot(kind, chain['src2']), deepcopy(bo_rows(kind))
    if fn:
        fn(rows)
    if snap_fn:
        snap_fn(snap)
    before = bo_state()
    with pytest.raises(Exception, match=match) if match else pytest.raises(Exception):
        bo_publish(snap, rows)
    assert bo_state() == before


R = lambda i, **kw: (lambda rows: rows[i].update(kw))  # noqa: E731
S = lambda **kw: (lambda snap: snap.update(kw))  # noqa: E731


@pytest.mark.parametrize('name,fn,snap_fn,match', [
    ('wrong_ranking_method', None, S(ranking_method_version=fx.V1), 'authority metadata'),
    ('wrong_financial_version', None, S(financial_rip_version=fx.FIN_V4), 'authority metadata'),
    ('wrong_overall_version', None, S(overall_rip_v14_version=fx.OVERALL_V12), 'authority metadata'),
    ('wrong_collector', None, S(collector_appeal_version='collector_appeal_v7'), 'authority metadata'),
    ('wrong_chase', None, S(chase_accessibility_version='x'), 'authority metadata'),
    ('wrong_transform', None, S(chase_accessibility_transform_version='x'), 'authority metadata'),
    ('wrong_allocation', None, S(allocation_method_version='x'), 'authority metadata'),
    ('v12_snapshot_field', None, S(overall_rip_v12_version=fx.OVERALL_V12), 'V12 authority'),
    ('wrong_source_snapshot', None, S(source_budget_snapshot_id='00000000-0000-0000-0000-00000000ffff'), 'source binding'),
    ('wrong_source_published', None, S(source_budget_published_at='2001-01-01T00:00:00+00:00'), 'source binding'),
    ('wrong_source_fingerprint', None, S(source_cohort_fingerprint='other'), 'source binding'),
    ('wrong_source_budget', None, S(source_full_market_budget=1350), 'source binding'),
    ('v1_source_snapshot', None, lambda s: s.update(source_budget_snapshot_id=live(fx.V1)['id']), 'source binding'),
    ('row_v12_evidence', R(0, current_overall_rip_v12_score=50.0), None, 'mixed model generations'),
    ('row_v4_evidence', R(0, benchmark_financial_rip_v4_score=40.0), None, 'mixed model generations'),
    ('row_legacy_rank', R(0, current_financial_only_rank=1), None, 'mixed model generations'),
    ('missing_v5', R(1, current_financial_rip_v5_score=None), None, 'missing or non-finite'),
    ('missing_v14', R(1, current_overall_rip_v14_score=None), None, 'missing or non-finite'),
    ('nan_string', R(1, threshold_overall_rip_v14_score='NaN'), None, 'missing or non-finite'),
    ('exact_false', R(1, threshold_exact_verified=False), None, 'exact-search evidence'),
    ('fin_exact_missing', R(1, financial_threshold_exact_verified=None), None, 'exact-search evidence'),
    ('wrong_current_v14', R(1, current_overall_rip_v14_score=54.99), None, 'live Full Market ranking rows'),
    ('wrong_current_v5', R(1, current_financial_rip_v5_score=49.99), None, 'live Full Market ranking rows'),
    ('wrong_rank', R(1, current_budget_rank=3), None, 'arithmetic|live Full Market'),
    ('wrong_fin_rank', R(1, current_financial_only_rank_v5=3), None, 'live Full Market|arithmetic'),
    ('wrong_pwin', R(1, current_chance_to_recover_capital=0.06), None, 'live Full Market ranking rows'),
    ('wrong_capital', R(1, current_actual_committed_capital=1.0), None, 'arithmetic|live Full Market'),
    ('wrong_family', R(1, product_family='etb'), None, 'live Full Market ranking rows'),
    ('wrong_run', R(1, source_calculation_run_id='00000000-0000-0000-0000-00000000ffff'), None, 'live Full Market ranking rows'),
    ('wrong_set', R(1, set_id='00000000-0000-0000-0000-00000000ffff'), None, 'live Full Market ranking rows'),
    ('wrong_price', R(1, current_market_price=261.0), None, 'arithmetic|live Full Market'),
    ('self_benchmark', R(1, benchmark_sealed_product_id=fx.PIDS[1]), None, 'benchmark ranking row'),
    ('wrong_benchmark_row', R(1, benchmark_sealed_product_id=fx.PIDS[2]), None, 'benchmark ranking row'),
    ('wrong_benchmark_score', R(1, benchmark_overall_rip_v14_score=54.0), None, 'benchmark ranking row'),
    ('wrong_fin_benchmark_row', R(1, financial_benchmark_sealed_product_id=fx.PIDS[3]), None, 'Financial benchmark'),
    ('wrong_fin_benchmark_score', R(1, financial_benchmark_financial_rip_v5_score=1.0), None, 'Financial benchmark'),
    ('threshold_loses_overall', R(1, threshold_overall_rip_v14_score=54.0), None, 'benchmark win'),
    ('threshold_loses_financial', R(1, financial_threshold_financial_rip_v5_score=49.0), None, 'benchmark win'),
    ('score_out_of_range', R(1, threshold_financial_rip_v5_score=101.0), None, 'range|arithmetic|benchmark'),
    ('pwin_out_of_range', R(1, threshold_chance_to_recover_capital=1.5), None, 'range'),
    ('noncent', R(1, best_open_price=240.001), None, 'arithmetic|exact-cent'),
    ('zero_price', R(1, best_open_price=0), None, 'arithmetic'),
    ('wrong_threshold_q', R(1, threshold_quantity=9), None, 'arithmetic'),
    ('noninteger_q', R(1, threshold_quantity=5.5), None, 'non-integral'),
    ('wrong_gap', R(1, price_gap_dollars=1.0), None, 'arithmetic'),
    ('wrong_gap_percent', R(1, price_gap_percent=0.9), None, 'arithmetic'),
    ('threshold_capital', R(1, threshold_actual_committed_capital=1.0), None, 'range|reconcil'),
    ('direction_leader', R(0, best_open_price=190.0, threshold_quantity=6, price_gap_dollars=10.0,
                           price_gap_percent=0.05), None, 'arithmetic'),
    ('status_missing', R(1, financial_status=None), None, 'required'),
    ('unresolved', None, S(unresolved_count=1, resolved_count=4), 'complete Full Market'),
    ('count_mismatch', None, S(resolved_count=3), 'does not equal resolved_count'),
    ('missing_product', lambda r: r.pop(), None, 'resolved_count'),
    ('extra_product', lambda r: r.append(dict(r[0], sealed_product_id='00000000-0000-0000-0000-00000000ffff')), S(resolved_count=5), 'complete Full Market'),
    ('duplicate', lambda r: r.__setitem__(3, deepcopy(r[2])), None, 'duplicate'),
    ('empty', lambda r: r.clear(), None, 'empty'),
    ('bad_runtime', None, S(runtime_seconds=-1), 'timing'),
    ('no_source_fp', None, S(source_full_market_row_fingerprint=''), 'timing'),
])
def test_v3_rejection_matrix_is_atomic(chain, name, fn, snap_fn, match):
    _bad(chain, fn, snap_fn, match=match)


def test_v3_fails_when_source_ranking_pointer_advanced(chain):
    snap, rows = bo_snapshot(3, chain['src2']), bo_rows(3)
    before = bo_state()
    payload = fx.ranking_v2_payload('2026-09-15')
    rank_publish(payload)  # V2 pointer moves to a newer generation
    try:
        with pytest.raises(Exception, match='source binding'):
            bo_publish(snap, rows)
        assert bo_state() == before
    finally:
        # restore the original generation so later tests see the frozen source
        with connection(autocommit=True) as c:
            c.execute('UPDATE budget_product_ranking_latest SET snapshot_id=%s::uuid, market_date=%s '
                      'WHERE ranking_method_version=%s', (chain['src2']['id'], chain['src2']['market_date'], fx.V2))


def test_v3_source_must_be_ranking_v2_not_v1(chain):
    snap = bo_snapshot(3, chain['src1'])
    with pytest.raises(Exception, match='authority metadata|source binding'):
        bo_publish(snap, bo_rows(3))


def test_dispatcher_rejects_v3_fields_on_v1_and_v2_methods(chain):
    before = bo_state()
    for kind in (1, 2):
        rows = deepcopy(bo_rows(kind)); rows[0]['current_overall_rip_v14_score'] = 50.0
        with pytest.raises(Exception, match='require the V3 method version'):
            bo_publish(bo_snapshot(kind, chain['src1']), rows)
        with pytest.raises(Exception, match='require the V3 method version'):
            bo_publish(dict(bo_snapshot(kind, chain['src1']), overall_rip_v14_version=fx.OVERALL_V14), bo_rows(kind))
    with pytest.raises(Exception, match='object'):
        bo_publish([bo_snapshot(3, chain['src2'])], bo_rows(3))
    assert bo_state() == before


def test_table_checks_reject_mixed_shape_writes_even_for_the_table_owner(chain):
    with connection() as c:
        with pytest.raises(Exception, match='budget_best_open_rows_authority_shape'):
            c.execute('UPDATE budget_product_best_open_price_rows SET current_financial_rip_v4_score = 1 '
                      'WHERE snapshot_id=%s', (chain['id3'],))
    with connection() as c:
        with pytest.raises(Exception, match='budget_best_open_snapshots_authority_shape'):
            c.execute('UPDATE budget_product_best_open_price_snapshots SET overall_rip_v12_version = %s WHERE id=%s',
                      (fx.OVERALL_V12, chain['id3']))


def test_service_role_has_no_direct_table_write_privilege_rpc_only(chain):
    """Unchanged V1/V2 posture: mutation happens only through the SECURITY DEFINER RPC."""
    for table in ('budget_product_best_open_price_rows', 'budget_product_best_open_price_snapshots',
                  'budget_product_best_open_price_latest'):
        assert q("SELECT has_table_privilege('service_role', %s, 'INSERT') OR "
                 "has_table_privilege('service_role', %s, 'UPDATE') OR "
                 "has_table_privilege('service_role', %s, 'DELETE')", (table, table, table)) == [(False,)]
        assert q("SELECT relrowsecurity FROM pg_class WHERE relname=%s", (table,)) == [(True,)]


FUNCS = ('publish_budget_product_best_open_price_snapshot', 'publish_budget_product_best_open_price_snapshot_v3',
         'publish_budget_product_best_open_price_snapshot_v1_v2')


@pytest.mark.parametrize('role', ['anon', 'authenticated'])
def test_api_roles_cannot_execute_or_read_best_open(chain, role):
    snap, rows = bo_snapshot(3, chain['src2']), bo_rows(3)
    for fn in FUNCS:
        with pytest.raises(Exception, match='permission denied'):
            bo_publish(snap, rows, role=role, fn=fn)
    for table in ('budget_product_best_open_price_rows', 'budget_product_best_open_price_snapshots',
                  'budget_product_best_open_price_latest'):
        with connection() as c:
            c.execute(f'SET LOCAL ROLE {role}')
            with pytest.raises(Exception, match='permission denied'):
                c.execute(f'SELECT count(*) FROM {table}')


def test_service_role_executes_dispatcher_only(chain):
    snap, rows = bo_snapshot(3, chain['src2']), bo_rows(3)
    assert bo_publish(snap, rows, role='service_role') == chain['id3']
    for fn in FUNCS[1:]:
        with pytest.raises(Exception, match='permission denied'):
            bo_publish(snap, rows, role='service_role', fn=fn)


def test_migrations_are_mirrored_and_additive():
    text = fx.BEST_OPEN_V3.read_text(encoding='utf-8')
    assert text == (fx.SUPA / fx.BEST_OPEN_V3.name).read_text(encoding='utf-8')
    upper = ' '.join(text.upper().split())
    assert 'DROP TABLE' not in upper and 'DROP COLUMN' not in upper.replace('ROLLBACK: DROP THE V3 COLUMNS', '')
    assert 'ALTER COLUMN BENCHMARK_OVERALL_RIP_V12_SCORE DROP NOT NULL' in upper


def test_zz_v3_refuses_a_v1_only_database_it_never_duplicates_v2_schema():
    fx.reset_database(DSN)
    for path in fx.RANKING_CHAIN + [fx.RANKING_V2_MIGRATION, fx.BEST_OPEN_V1_STORE, fx.BEST_OPEN_V1_HARDEN]:
        fx.apply(DSN, path)
    with pytest.raises(Exception, match='financial_status|does not exist'):
        fx.apply(DSN, fx.BEST_OPEN_V3)
    assert not q("SELECT 1 FROM information_schema.columns WHERE table_name='budget_product_best_open_price_rows' "
                 "AND column_name='current_overall_rip_v14_score'")
