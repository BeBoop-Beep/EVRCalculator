"""Builder output -> real RPCs. Proves the explicit Python payload builders serialize exactly
what the Ranking V2 / Best-Open V3 SQL accepts (no hand-written payloads).

Needs the backend runtime dependencies (numpy, supabase, python-dotenv) in addition to
psycopg; the CI Postgres job installs them for this file. Skips without a DSN.
"""
import json
import os

import pytest

from backend.tests.integration import _ranking_fixtures as fx

DSN = os.getenv('BEST_OPEN_TEST_DATABASE_URL')
pytestmark = pytest.mark.skipif(not DSN, reason='isolated PostgreSQL DSN required')
pytest.importorskip('numpy')
pytest.importorskip('dotenv')
os.environ.setdefault('SUPABASE_URL', 'https://example.supabase.co')
os.environ.setdefault('SUPABASE_SERVICE_ROLE_KEY', 'ci-placeholder')
os.environ.setdefault('SUPABASE_ANON_KEY', 'ci-placeholder')

from backend.calculations.evr.best_open_price_v3 import BEST_OPEN_PRICE_V3_METHOD_VERSION  # noqa: E402
from backend.calculations.evr.budget_normalized_product_ranking import rank_budget_cohort_v2  # noqa: E402
from backend.db.services import budget_v2_v3_publication_payloads as pay  # noqa: E402


def conn():
    return fx.connection(DSN)


@pytest.fixture(scope='module')
def db():
    fx.reset_database(DSN)
    for path in fx.RANKING_CHAIN + [fx.RANKING_V2_MIGRATION, fx.BEST_OPEN_V1_STORE, fx.BEST_OPEN_V1_HARDEN,
                                    fx.BEST_OPEN_V2, fx.BEST_OPEN_V3]:
        fx.apply(DSN, path)


def _ranked():
    strategies = [{
        'sealedProductId': pid, 'quantity': fx.QTY[i], 'targetBudget': fx.BUDGET,
        'actualCommittedCapital': fx.COMMITTED[i], 'financialRipV5Score': 50.0 - i,
        'financialRipV5Status': 'ready', 'financialRipV5Rankable': True, 'overallRipV14Score': 55.0 - 2 * i,
        'overallRipV14Status': 'ready', 'overallRipV14Rankable': True, 'chanceToRecoverCapital': 0.05,
        'expectedValue': 700.0, 'medianValue': 690.0, 'topOneOutcomeValueShare': 0.2,
    } for i, pid in enumerate(fx.PIDS)]
    return rank_budget_cohort_v2(list(reversed(strategies)))


def _axis(price_cents, quantity, bench_id, financial, overall, capital):
    return dict(status='exact', methodVersion=BEST_OPEN_PRICE_V3_METHOD_VERSION, benchmarkProductId=bench_id,
                evaluationCount=10, wallSeconds=0.5, bracketExpansions=0, bracketRefinements=0,
                monotonicityFallbackCount=0,
                threshold=dict(priceCents=price_cents, quantity=quantity, financialRipV5Score=financial,
                               overallRipV14Score=overall, chanceToRecoverCapital=0.05, actualCommittedCapital=capital),
                exactness=dict(thresholdWins=True, oneCentMaximal=True, nextPriceWins=False))


def test_builder_payloads_are_accepted_by_the_real_rpcs(db):
    ctx = {pid: dict(set_id=fx.SET, product_family='booster_box', product_market_price=fx.PRICES[i],
                     price_as_of=fx.PRICE_DATE, collector_appeal_score=60.0, chase_accessibility_raw=0.01,
                     source_calculation_run_id=fx.RUN, full_market_anchor=fx.BUDGET, max_eligible_sku_price=1299.0,
                     full_market_rounding_rule='ceil(max / 50) * 50', full_market_rounding_increment=50.0,
                     full_market_rounding_rule_version=fx.ROUNDING_RULE_VERSION)
           for i, pid in enumerate(fx.PIDS)}
    snap = pay.build_ranking_v2_snapshot(
        market_date='2026-09-14', built_at='2026-09-15T00:00:00+00:00', pinned_price_as_of=fx.PRICE_DATE,
        eligible_cohort_count=4, cohort_fingerprint='fp-builder', full_market_budget=fx.BUDGET,
        max_eligible_sku_price=1299.0, full_market_rounding_increment=50.0,
        full_market_rounding_rule_version=fx.ROUNDING_RULE_VERSION)
    rows = pay.build_ranking_v2_rows(_ranked(), ctx)
    with conn() as c:
        rid = c.execute('SELECT public.publish_budget_product_ranking_snapshot(%s::jsonb,%s::jsonb)',
                        (json.dumps(snap), json.dumps(rows))).fetchone()[0]
        live = c.execute('SELECT id::text, published_at, market_date, cohort_fingerprint, full_market_budget, '
                         'eligible_cohort_count FROM budget_product_ranking_snapshots WHERE id=%s', (rid,)).fetchone()
        persisted = {r[0]['sealed_product_id']: r[0] for r in c.execute(
            'SELECT to_jsonb(r) FROM budget_product_ranking_rows r WHERE snapshot_id=%s', (rid,)).fetchall()}
    src = dict(id=live[0], published_at=live[1].isoformat(), market_date=live[2], cohort_fingerprint=live[3],
               full_market_budget=float(live[4]), eligible_cohort_count=live[5])
    first, second = fx.PIDS[0], fx.PIDS[1]
    out = []
    for i, pid in enumerate(fx.PIDS):
        b = second if pid == first else first
        bench = persisted[b]
        th = [21000, 24000, 29000, 35000][i]
        q = int(fx.BUDGET * 100 // th)
        cap = q * th / 100
        overall = _axis(th, q, b, 50.0, bench['overall_rip_v14_score'] + 0.5, cap)
        financial = _axis(th, q, b, bench['financial_rip_v5_score'] + 0.5, 54.0, cap)
        out.append(pay.build_best_open_v3_row(current=persisted[pid], overall_result=overall,
                                              financial_result=financial, overall_benchmark=bench,
                                              financial_benchmark=bench))
    bsnap = pay.build_best_open_v3_snapshot(source_ranking_snapshot=src, built_at='2026-09-16T00:00:00+00:00',
                                            runtime_seconds=1.0, source_full_market_row_fingerprint='fp',
                                            resolved_count=4)
    with conn() as c:
        sid = c.execute('SELECT public.publish_budget_product_best_open_price_snapshot(%s::jsonb,%s::jsonb)',
                        (json.dumps(bsnap), json.dumps(out))).fetchone()[0]
        assert c.execute('SELECT count(*), bool_and(threshold_exact_verified) FROM '
                         'budget_product_best_open_price_rows WHERE snapshot_id=%s', (sid,)).fetchone() == (4, True)
        assert c.execute('SELECT best_open_price_method_version FROM budget_product_best_open_price_snapshots '
                         'WHERE id=%s', (sid,)).fetchone() == (BEST_OPEN_PRICE_V3_METHOD_VERSION,)
