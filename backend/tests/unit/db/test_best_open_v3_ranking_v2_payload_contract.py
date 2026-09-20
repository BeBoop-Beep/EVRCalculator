"""Pins Ranking V2 / Best-Open V3 identity literals across Python, SQL and test fixtures."""
from pathlib import Path

import pytest

from backend.calculations.evr.best_open_price_v3 import BEST_OPEN_PRICE_V3_METHOD_VERSION
from backend.calculations.evr.budget_normalized_product_ranking import (
    ALLOCATION_METHOD_VERSION, BUDGET_COMPARISON_SCOPE_VERSION,
)
from backend.calculations.evr.financial_rip_v5_config import FINANCIAL_RIP_V5_VERSION
from backend.db.services import budget_v2_v3_publication_payloads as pay
from backend.desirability.scoring_config import OVERALL_RIP_V14_VERSION
from backend.tests.integration import _ranking_fixtures as fx

ROOT = Path(__file__).resolve().parents[4]
RANKING_SQL = (ROOT / 'backend/db/migrations/20260920120000_add_budget_product_ranking_v2_v5_v14.sql').read_text('utf-8')
BEST_OPEN_SQL = (ROOT / 'backend/db/migrations/20260920130000_add_best_open_price_v3_dual_financial_v5_overall_v14.sql').read_text('utf-8')


def test_fixture_literals_equal_python_constants():
    assert fx.RANKING_V2_IDENTITY == pay.RANKING_V2_IDENTITY
    assert fx.FIN_V5 == FINANCIAL_RIP_V5_VERSION and fx.OVERALL_V14 == OVERALL_RIP_V14_VERSION
    assert fx.ALLOC == ALLOCATION_METHOD_VERSION and fx.SCOPE == BUDGET_COMPARISON_SCOPE_VERSION


@pytest.mark.parametrize('sql', [RANKING_SQL, BEST_OPEN_SQL], ids=['ranking_v2', 'best_open_v3'])
def test_every_identity_literal_in_sql_matches_python(sql):
    for value in (FINANCIAL_RIP_V5_VERSION, OVERALL_RIP_V14_VERSION, ALLOCATION_METHOD_VERSION,
                  BUDGET_COMPARISON_SCOPE_VERSION, pay.RANKING_V2_IDENTITY['collector_appeal_version'],
                  pay.RANKING_V2_IDENTITY['chase_accessibility_version'],
                  pay.RANKING_V2_IDENTITY['chase_accessibility_transform_version'], 'budget_product_ranking_v2'):
        assert f"'{value}'" in sql, value
    assert f"'{BEST_OPEN_PRICE_V3_METHOD_VERSION}'" in BEST_OPEN_SQL


def test_sql_never_embeds_a_wrong_generation_identity_in_v2_v3_branches():
    # The V2/V3 branches must not require V4/V12 identities as authority (they may only
    # appear in guards/comments that reject them).
    for sql in (RANKING_SQL, BEST_OPEN_SQL):
        assert "IS DISTINCT FROM 'financial_rip_v4" not in sql
        assert "IS DISTINCT FROM 'overall_rip_v12" not in sql


def test_migrations_are_mirrored_between_trees():
    for name in ('20260920120000_add_budget_product_ranking_v2_v5_v14.sql',
                 '20260920130000_add_best_open_price_v3_dual_financial_v5_overall_v14.sql',
                 '20260920000000_add_sealed_product_financial_rip_v5.sql'):
        assert (ROOT / 'backend/db/migrations' / name).read_text('utf-8') == (ROOT / 'supabase/migrations' / name).read_text('utf-8')


def test_best_open_v3_row_builder_refuses_non_exact_or_wrong_method_axes():
    ranking = fx.ranking_v2_payload()[1]
    current = dict(ranking[1]); bench = dict(ranking[0])
    good = dict(status='exact', methodVersion=BEST_OPEN_PRICE_V3_METHOD_VERSION, benchmarkProductId=bench['sealed_product_id'],
                evaluationCount=5, wallSeconds=0.1,
                threshold=dict(priceCents=24000, quantity=5, financialRipV5Score=50.0, overallRipV14Score=55.5,
                               chanceToRecoverCapital=0.05, actualCommittedCapital=1200.0),
                exactness=dict(thresholdWins=True, oneCentMaximal=True))
    row = pay.build_best_open_v3_row(current=current, overall_result=good, financial_result=good,
                                     overall_benchmark=bench, financial_benchmark=bench)
    assert row['best_open_price'] == 240.0 and row['price_gap_dollars'] == 20.0
    assert not [k for k in row if '_v4_' in k or '_v12_' in k or k == 'current_financial_only_rank']
    for bad in (dict(good, status='unresolved_extreme_quantity'), dict(good, exactness=dict(thresholdWins=True, oneCentMaximal=False)),
                dict(good, methodVersion='budget_product_best_open_price_full_market_v2_dual_financial_v4_overall_v12')):
        with pytest.raises(ValueError):
            pay.build_best_open_v3_row(current=current, overall_result=bad, financial_result=good,
                                       overall_benchmark=bench, financial_benchmark=bench)
