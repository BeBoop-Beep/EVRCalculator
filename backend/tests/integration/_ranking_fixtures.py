"""Shared real-PostgreSQL fixtures for the Ranking V2 / Best-Open V3 integration tests.

No backend engine imports: the CI Postgres job installs only pytest and psycopg. Identity
literals are pinned to the Python constants by a unit test
(test_budget_v2_v3_publication_payloads.py).
"""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SUPA = ROOT / 'supabase/migrations'
BACK = ROOT / 'backend/db/migrations'
RANKING_CHAIN = [
    SUPA / '20260823193538_20260822213027_create_budget_normalized_product_rankings.sql',
    SUPA / '20260824025349_strengthen_budget_product_ranking_publication.sql',
    SUPA / '20260825154658_expose_budget_product_strategy_expected_value.sql',
    BACK / '20260902010000_add_budget_product_ranking_v12_authority_columns.sql',
    BACK / '20260903224637_extend_budget_product_ranking_publication_rpc_v12_atomic.sql',
    SUPA / '20260915233000_add_budget_opening_profile_strategy_metrics.sql',
]
RANKING_V2_MIGRATION = BACK / '20260920120000_add_budget_product_ranking_v2_v5_v14.sql'
BEST_OPEN_V1_STORE = SUPA / '20260914184759_create_budget_product_best_open_price_store.sql'
BEST_OPEN_V1_HARDEN = SUPA / '20260914225000_harden_best_open_publication_review.sql'
BEST_OPEN_V2 = SUPA / '20260916120000_add_best_open_price_v2_dual_threshold.sql'
BEST_OPEN_V3 = BACK / '20260920130000_add_best_open_price_v3_dual_financial_v5_overall_v14.sql'

V1 = 'budget_product_ranking_v1'
V2 = 'budget_product_ranking_v2'
ALLOC = 'budget_allocation_floor_quantity_v1'
SCOPE = 'budget_constrained_whole_unit_cross_format_v1'
PRICE_DATE = '2026-09-14'
BUDGET = 1300.0
RUN = '00000000-0000-0000-0000-0000000000aa'
SET = '00000000-0000-0000-0000-0000000000bb'
PIDS = [f'00000000-0000-0000-0000-00000000{n:04d}' for n in range(1, 5)]
PRICES = [200.0, 260.0, 310.0, 400.0]
QTY = [int(BUDGET // p) for p in PRICES]
COMMITTED = [q * p for q, p in zip(QTY, PRICES)]
ROUNDING_RULE_VERSION = 'full_market_next_50_above_max_eligible_sku_v1'

FIN_V4 = 'financial_rip_v4_outcome_profile_p95_only_25_20_15_25_10_5'
FIN_V5 = 'financial_rip_v5_shortfall_resilience_25_20_15_25_10_5'
OVERALL_V10 = 'overall_rip_v10_90_financial_v4_10_collector_appeal_v5'
OVERALL_V12 = 'overall_rip_v12_86_financial_v4_04_chase_accessibility_v1_10_collector_appeal_v5'
OVERALL_V14 = 'overall_rip_v14_86_financial_v5_04_chase_accessibility_v1_10_collector_appeal_v5'
COLLECTOR = 'collector_appeal_v5_contextual_roster_h_only_d_baseline_up4_down2'
CHASE = 'chase_accessibility_v1_hc_value_squared_modeled_probability'
TRANSFORM = 'chase_accessibility_overall_score_v1_saturating_k002'

RANKING_V2_IDENTITY = {
    'ranking_method_version': V2, 'allocation_method_version': ALLOC, 'comparison_scope_version': SCOPE,
    'financial_rip_version': FIN_V5, 'financial_rip_v5_version': FIN_V5,
    'overall_rip_version': OVERALL_V14, 'overall_rip_v14_version': OVERALL_V14,
    'collector_appeal_version': COLLECTOR, 'chase_accessibility_version': CHASE,
    'chase_accessibility_transform_version': TRANSFORM,
}


def connection(dsn=None, **kwargs):
    import psycopg
    return psycopg.connect(dsn or os.environ['BEST_OPEN_TEST_DATABASE_URL'], **kwargs)


def assert_disposable(dsn):
    from psycopg.conninfo import conninfo_to_dict
    parsed = conninfo_to_dict(dsn)
    assert os.getenv('BEST_OPEN_ACK_DISPOSABLE') == 'yes'
    assert parsed.get('host') in {'127.0.0.1', 'localhost', 'postgres'}
    assert parsed.get('dbname') == 'best_open_test'


def reset_database(dsn):
    assert_disposable(dsn)
    with connection(dsn, autocommit=True) as c:
        c.execute('DROP SCHEMA IF EXISTS public CASCADE')
        c.execute('CREATE SCHEMA public')
        c.execute('CREATE SCHEMA IF NOT EXISTS extensions')
        c.execute('CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA extensions')
        for role in ('anon', 'authenticated', 'service_role'):
            if not c.execute('SELECT 1 FROM pg_roles WHERE rolname=%s', (role,)).fetchone():
                c.execute(f'CREATE ROLE {role} NOLOGIN')
        c.execute('ALTER ROLE service_role BYPASSRLS')
        c.execute('GRANT USAGE ON SCHEMA public TO anon, authenticated, service_role')


def apply(dsn, path: Path):
    with connection(dsn, autocommit=True) as c:
        c.execute(path.read_text(encoding='utf-8'))


def _full_market(i):
    return dict(
        sealed_product_id=PIDS[i], set_id=SET, product_family='booster_box', target_budget=BUDGET,
        budget_type='full_market', quantity=QTY[i], actual_committed_capital=COMMITTED[i],
        unused_capital=BUDGET - COMMITTED[i], unused_capital_percent=(BUDGET - COMMITTED[i]) / BUDGET,
        capital_utilization=COMMITTED[i] / BUDGET, collector_appeal_score=60.0, chance_to_recover_capital=0.05,
        product_market_price=PRICES[i], price_as_of=PRICE_DATE, full_market_anchor=BUDGET,
        max_eligible_sku_price=1299.0, full_market_rounding_rule='ceil(max / 50) * 50',
        full_market_rounding_increment=50.0, full_market_rounding_rule_version=ROUNDING_RULE_VERSION,
        source_calculation_run_id=RUN, expected_value=700.0 + i, median_value=690.0 + i,
        top1_outcome_value_share=0.2)


def _snapshot_common(market_date, fingerprint):
    return dict(market_date=market_date, built_at='2026-09-15T00:00:00+00:00',
                pinned_price_as_of=PRICE_DATE, eligible_cohort_count=len(PIDS),
                cohort_fingerprint=fingerprint, full_market_budget=BUDGET, max_eligible_sku_price=1299.0,
                full_market_rounding_increment=50.0, full_market_rounding_rule_version=ROUNDING_RULE_VERSION)


def ranking_v1_v12_payload(market_date='2026-09-14'):
    """A V1-method snapshot ranked under explicit V12 authority (what Best-Open V1/V2 source)."""
    snapshot = dict(
        _snapshot_common(market_date, 'fp-v1'), ranking_method_version=V1, allocation_method_version=ALLOC,
        comparison_scope_version=SCOPE, financial_rip_version=FIN_V4, overall_rip_version=OVERALL_V12,
        overall_rip_v12_version=OVERALL_V12, collector_appeal_version=COLLECTOR,
        chase_accessibility_version=CHASE, chase_accessibility_transform_version=TRANSFORM,
        ranked_under_v12_authority=True)
    rows = []
    for i in range(len(PIDS)):
        rows.append(dict(
            _full_market(i), budget_rank=i + 1, budget_cohort_size=len(PIDS), budget_tier='B',
            financial_only_rank=i + 1, financial_rip_v4_score=45.0 - i, overall_rip_v10_score=50.0 - i,
            overall_rip_v12_score=52.0 - i, overall_rip_v12_rankable=True, overall_rip_v12_status='ready',
            chase_accessibility_raw=0.01, budget_rank_v12=i + 1, budget_cohort_size_v12=len(PIDS)))
    return snapshot, rows


def ranking_v1_plain_payload(market_date='2026-09-13'):
    """A plain V1/V10-authority snapshot (no V12 fields)."""
    snapshot = dict(
        _snapshot_common(market_date, 'fp-v1-plain'), ranking_method_version=V1,
        allocation_method_version=ALLOC, comparison_scope_version=SCOPE, financial_rip_version=FIN_V4,
        overall_rip_version=OVERALL_V10, collector_appeal_version=COLLECTOR)
    rows = []
    for i in range(len(PIDS)):
        rows.append(dict(
            _full_market(i), budget_rank=i + 1, budget_cohort_size=len(PIDS), budget_tier='B',
            financial_only_rank=i + 1, financial_rip_v4_score=45.0 - i, overall_rip_v10_score=50.0 - i))
    return snapshot, rows


def ranking_v2_payload(market_date='2026-09-14'):
    snapshot = dict(_snapshot_common(market_date, 'fp-v2'), **RANKING_V2_IDENTITY,
                    ranked_under_v14_authority=True, diagnostics_json={})
    rows = []
    for i in range(len(PIDS)):
        rows.append(dict(
            _full_market(i), financial_rip_v5_score=50.0 - i, financial_rip_v5_status='ready',
            financial_rip_v5_rankable=True, overall_rip_v14_score=55.0 - 2 * i,
            overall_rip_v14_status='ready', overall_rip_v14_rankable=True, budget_rank_v14=i + 1,
            budget_cohort_size_v14=len(PIDS), budget_tier_v14='B', financial_only_rank_v5=i + 1,
            chase_accessibility_raw=0.01))
    return snapshot, rows
