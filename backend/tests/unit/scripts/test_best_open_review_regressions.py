"""Adversarial regressions found while reviewing PRs 191 and 192.

These tests exercise behavior, not source-string presence. No production I/O.
"""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

import pytest

from backend.scripts import publish_best_open_price_if_ready as publisher
from backend.db.services import budget_product_best_open_price_service as store
from backend.domain.access import index_plan_access as access
from backend.tests.unit.scripts.test_publish_best_open_price_if_ready import SOURCE, engine_result
from backend.tests.unit.calculations.test_prepared_financial_rip_and_best_open_price import _engine


def valid_result():
    result = deepcopy(engine_result())
    result['methodVersion'] = publisher.BEST_OPEN_PRICE_METHOD_VERSION
    result['source'].update(publishedAt=SOURCE['published_at'], fullMarketBudget=SOURCE['full_market_budget'], authorityUnchangedAtCompletion=True)
    for row in result['products']:
        cents = round(row['bestOpenPrice'] * 100)
        row['bestOpenPriceCents'] = cents
        row['exactness']['nextPriceCents'] = cents + 1
    return result


@pytest.mark.parametrize('kind', ['missing_next_verdict', 'wrong_next_cent', 'wrong_quantity', 'fractional_cent', 'wrong_method', 'missing_current_quantity'])
def test_publication_validator_rejects_invalid_or_incomplete_engine_evidence(kind):
    result = valid_result()
    row = result['products'][1]
    if kind == 'missing_next_verdict':
        row['exactness'].pop('nextPriceWins')
    elif kind == 'wrong_next_cent':
        row['exactness']['nextPriceCents'] += 20
    elif kind == 'wrong_quantity':
        row['thresholdQuantity'] += 1
    elif kind == 'fractional_cent':
        row['bestOpenPrice'] = 90.001
    elif kind == 'wrong_method':
        result['methodVersion'] = 'another_method'
    else:
        row.pop('currentQuantity')
    assert publisher.validate_engine_result(result, SOURCE), kind


def test_checkpoint_identity_changes_on_model_or_budget_change(tmp_path):
    original = publisher._checkpoint_path(tmp_path, SOURCE)
    assert publisher._checkpoint_path(tmp_path, dict(SOURCE, full_market_budget=1400)) != original
    assert publisher._checkpoint_path(tmp_path, dict(SOURCE, financial_rip_version='changed')) != original


def test_detail_capability_is_independent_of_product_rip_and_does_not_mutate_input():
    payload = {'product': {'id': 'p'}, 'rip': {'available': True, 'bestOpenPrice': {'bestOpenPrice': 13.23}}}
    with patch.object(access, 'has_index_feature_access', side_effect=lambda plan, feature: feature != access.FEATURE_BEST_OPEN_PRICE):
        result = access.project_sealed_product_detail_response(payload, 'plus')
    assert result['rip']['available'] is True
    assert 'bestOpenPrice' not in result['rip']
    assert payload['rip']['bestOpenPrice']['bestOpenPrice'] == 13.23


def test_source_reader_rejects_model_drift_even_if_id_and_timestamps_did_not_change():
    live = dict(SOURCE)
    snap = {'source_budget_snapshot_id': live['id'], 'source_budget_published_at': live['published_at'],
            'source_market_date': live['market_date'], 'source_cohort_fingerprint': live['cohort_fingerprint'],
            'ranking_method_version': live['ranking_method_version'], 'allocation_method_version': live['allocation_method_version'],
            'financial_rip_version': 'different-financial-model'}
    with patch.object(store, '_live_budget_source_identity', return_value=live):
        assert store._source_binding_reason(object(), snap) is not None


def test_leader_threshold_is_global_not_only_the_first_losing_bracket():
    # Fixed-quantity intervals may have different outcomes; a one-cent neighbor
    # check certifies a local boundary, NOT the highest winning price overall.
    winning = set(range(100, 131)) | set(range(200, 241))
    result = _engine(leader=True, budget=1000, current=100, winning=winning).search()
    assert result['threshold']['priceCents'] == 240


def test_price_sentinels_cannot_rule_out_an_unsampled_winning_island():
    winning = {500, 690, 691, 692}
    result = _engine(leader=True, budget=1000, current=500, winning=winning).search()
    assert result['threshold']['priceCents'] == 692


def test_global_search_matches_arbitrary_nonmonotone_bruteforce_oracles():
    import random
    rng = random.Random(29314)
    for _ in range(1000):
        budget = rng.randint(30, 350)
        current = rng.randint(2, budget)
        leader = bool(rng.getrandbits(1))
        domain = range(current, budget + 1) if leader else range(1, current + 1)
        winning = {p for p in domain if rng.random() < 0.22}
        if leader:
            winning.add(current)
        else:
            winning.discard(current)  # source nonleader must actually lose
        result = _engine(leader=leader, budget=budget, current=current, winning=winning).search()
        actual = (result.get('threshold') or {}).get('priceCents')
        assert actual == (max(winning) if winning else None)


def test_prepared_price_cache_is_bounded_during_exact_cent_scan():
    engine = _engine(leader=True, budget=10000, current=5000, winning={5000})
    assert engine.search()['threshold']['priceCents'] == 5000
    assert len(engine._evaluations) <= 2048
    assert engine.evaluation_count >= 5001


def test_checkpoint_atomic_replacement_keeps_old_valid_file_on_failure(tmp_path, monkeypatch):
    from backend.scripts import research_best_open_price_bucket2 as runner
    import json
    target = tmp_path / 'checkpoint.json'
    runner._write_checkpoint(target, {'version': 'old'})
    def fail(*args): raise OSError('interrupted replacement')
    monkeypatch.setattr(runner.os, 'replace', fail)
    with pytest.raises(OSError): runner._write_checkpoint(target, {'version': 'new'})
    assert json.loads(target.read_text()) == {'version': 'old'}
    assert list(tmp_path.iterdir()) == [target]


def test_checkpoint_manifest_binds_models_source_values_batch_and_numpy():
    from backend.scripts import research_best_open_price_bucket2 as runner
    rows = [{'sealed_product_id': 'p1', 'collector_appeal_score': 5}]
    original = runner._checkpoint_manifest(SOURCE, rows, ['p1'], 24)
    changed = runner._checkpoint_manifest(SOURCE, [dict(rows[0], collector_appeal_score=6)], ['p1'], 24)
    assert changed != original
    assert runner._checkpoint_manifest(SOURCE, rows, ['p1'], 8) != original
    assert original['numpyVersion'] == runner.np.__version__


def test_published_strategy_parity_refuses_wrong_counterfactual_seed_or_scorer():
    from backend.scripts import research_best_open_price_bucket2 as runner
    from types import SimpleNamespace
    source = {'sealed_product_id':'p1','product_market_price':10,'budget_rank_v12':1,
              'financial_rip_v4_score':80,'overall_rip_v12_score':78,'chance_to_recover_capital':.4,'actual_committed_capital':100}
    good = {'wins':True,'financialRipV4Score':80,'overallRipV12Score':78,'chanceToRecoverCapital':.4,'actualCommittedCapital':100}
    runner._check_published_strategy(SimpleNamespace(evaluate=lambda *_: good), source, {})
    with pytest.raises(RuntimeError, match='parity'):
        runner._check_published_strategy(SimpleNamespace(evaluate=lambda *_: dict(good, overallRipV12Score=77)),source,{})


def test_engine_uses_persisted_collector_not_mutable_simulation_input():
    # AST inspection pins both actual candidate constructor arguments; source
    # equality is separately covered by runtime publication evidence tests.
    import ast, inspect
    from backend.scripts import research_best_open_price_bucket2 as runner
    tree = ast.parse(inspect.getsource(runner))
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == 'PreparedCanonicalCandidate']
    assert len(calls)==2
    for call in calls:
        assert ast.unparse(call.args[3]) == "float(source['collector_appeal_score'])"
