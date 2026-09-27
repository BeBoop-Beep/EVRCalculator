from copy import deepcopy
from dataclasses import replace
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID
import pytest

from backend.domain.pokemon.rip_benchmark_v1 import (
    APPROVED_CALIBRATION_VERSIONS, BenchmarkError, Calibration, Reference,
    equal_weight_reference, fingerprint, history_windows, metric_row, number, preview_score, wire,
)
from backend.db.services.rip_benchmark_evidence_v1 import (
    V3_CONTRACT, V3_METHOD, V3_WEIGHT, V3_BASIS, attach_evidence, compatible_v3,
    evidence_from_scope, map_era_identities, product_evidence, select_exact_product_results,
)
from backend.db.services.rip_benchmark_preview_v1 import (
    CURRENT_RPC, HISTORY_RPC, PrivateBenchmarkReader, candidate_request,
)


def uid(n): return str(UUID(int=n))
DAY = '2026-09-25'
CAL = Calibration('shadow-fixture', 'financial', 'financial-fixture', 'set-fixture', Decimal('10'))


def source(metric='financial', raw=50, eid=None, typ='set', **updates):
    return {'entity_type': typ, 'entity_id': eid or uid(1), 'market_date': DAY,
            'model_version': metric+'-fixture', 'raw_model_value': raw,
            'rank': 2, 'cohort_size': 22, 'reconstruction_status': 'persisted_exact',
            'lineage': {'proof': 'synthetic'}, **updates}


def row(metric='financial', src=None, **updates):
    return metric_row(entity_type='set', entity_id=uid(1), metric_key=metric,
                      market_date=DAY, source=src or source(metric), **updates)


def ref(metric='financial', value=50):
    return Reference('set-fixture', metric, metric+'-fixture', DAY, Decimal(str(value)), 'a'*64)


@pytest.mark.parametrize('value', [None, True, False, float('nan'), float('inf'), '-Infinity', 'NaN', 'abc'])
def test_invalid_number(value):
    with pytest.raises(BenchmarkError): number(value)


@pytest.mark.parametrize('value', ['0', '50', '0.00000000000000000000001', '-3', '1e20'])
def test_exact_five_anchor(value):
    assert preview_score(value, value, CAL) == Decimal(5)


@pytest.mark.parametrize('offset', ['-100', '-20', '-0.000000001', '0', '0.000000001', '20', '100'])
def test_direction_range_and_monotonic(offset):
    x = Decimal(offset)
    score = preview_score(Decimal(50)+x, 50, CAL)
    assert 0 <= score <= 10
    assert (score > 5) == (x > 0)
    assert (score < 5) == (x < 0)


def test_monotone_shadow_sweep():
    values = [preview_score(Decimal(i)/10, 50, CAL) for i in range(-500, 1501)]
    assert all(a <= b for a,b in zip(values, values[1:]))


def test_display_rounding_does_not_pollute_storage():
    x = preview_score('50.001', 50, CAL)
    assert x == Decimal('5.0001')
    assert wire(x) == '5.0001'
    assert preview_score(50, 50, CAL) == Decimal(5)


def test_clipping_does_not_reassign_rank():
    a = row(src=source(raw=110, rank=1), reference=ref(), calibration=CAL)
    b = row(src=source(raw=100, rank=2), reference=ref(), calibration=CAL)
    assert a['benchmark_score'] == b['benchmark_score'] == 10
    assert (a['rank'], b['rank']) == (1,2)


def test_relative_score_does_not_measure_whole_market_improvement():
    assert preview_score(40,30,CAL) == preview_score(80,70,CAL)


@pytest.mark.parametrize('scale', [0, -1, float('inf'), None, True])
def test_bad_scale(scale):
    with pytest.raises(BenchmarkError): replace(CAL, scale=scale)


def test_no_approved_production_calibration():
    assert not APPROVED_CALIBRATION_VERSIONS
    r = row(reference=ref())
    assert r['raw_model_value'] == 50 and r['rank'] == 2
    assert r['benchmark_score'] is None and r['benchmark_reason'] == 'calibration_unapproved'


def test_reference_equal_weights_exact_members_not_filters():
    rows = [row(src=source(raw=10)), metric_row(entity_type='set', entity_id=uid(2),
            metric_key='financial', market_date=DAY, source=source(raw=30,eid=uid(2)))]
    kwargs = dict(expected_entity_ids=[uid(1),uid(2)], benchmark_key='set-fixture',
                  metric_key='financial', source_model_version='financial-fixture', market_date=DAY)
    r = equal_weight_reference(rows, **kwargs)
    assert r.raw_value == 20
    assert r == equal_weight_reference(rows[::-1], **kwargs)
    with pytest.raises(BenchmarkError): equal_weight_reference(rows[:1], **kwargs)
    with pytest.raises(BenchmarkError): equal_weight_reference(rows+rows[:1], **kwargs)
    with pytest.raises(BenchmarkError): equal_weight_reference(rows, **{**kwargs, 'expected_entity_ids':[uid(1),uid(1)]})


@pytest.mark.parametrize('field,value', [('source_market_date','2026-09-24'),('source_model_version','other'),('model_status','unavailable'),('model_status','inherited')])
def test_reference_rejects_mixed_source(field,value):
    r=row();r[field]=value
    with pytest.raises(BenchmarkError):
        equal_weight_reference([r], expected_entity_ids=[uid(1)], benchmark_key='set-fixture',
            metric_key='financial', source_model_version='financial-fixture', market_date=DAY)


@pytest.mark.parametrize('metric', ['chase','collector'])
def test_product_inherits_parent_not_fake_product_rank(metric):
    r=metric_row(entity_type='sealed_product',entity_id=uid(10),parent_set_id=uid(1),
                 metric_key=metric,market_date=DAY,source=source(metric))
    assert r['model_status']=='inherited' and r['rank'] is None and r['cohort_size'] is None
    assert r['source_entity_id']==uid(1)
    with pytest.raises(BenchmarkError):
        metric_row(entity_type='sealed_product',entity_id=uid(10),parent_set_id=uid(1),
                   metric_key=metric,market_date=DAY,source=source(metric,eid=uid(10),typ='sealed_product'))


@pytest.mark.parametrize('metric', ['financial','chase','collector','overall'])
def test_stale_or_future_model_rejected(metric):
    with pytest.raises(BenchmarkError): row(metric,source(metric,market_date='2026-09-24'))
    with pytest.raises(BenchmarkError): row(metric,source(metric,market_date='2026-09-26'))


def test_collector_proven_interval_not_implicit_forward_fill():
    old=source('collector', market_date='2026-09-11', collector_run_id=uid(90),
               lineage={'effective_from':'2026-09-11','effective_until':DAY})
    assert row('collector',old)['model_status']=='available'
    old['lineage']['effective_until']='2026-09-24'
    with pytest.raises(BenchmarkError):row('collector',old)


@pytest.mark.parametrize('rank,size', [(0,22),(23,22),(1,None),(None,22),(1.5,22),(True,22)])
def test_rank_validation(rank,size):
    with pytest.raises(BenchmarkError):row(src=source(rank=rank,cohort_size=size))


def test_calibration_model_key_and_reference_identity():
    for cal in [replace(CAL, source_model_version='other'),replace(CAL, benchmark_key='other'),replace(CAL,metric_key='chase')]:
        with pytest.raises(BenchmarkError): row(reference=ref(),calibration=cal)
    with pytest.raises(BenchmarkError):row(reference=replace(ref(),market_date='2026-09-24'))


def scope():
    return {'averageCostPerPack':10,'averageModelBreakEvenPerPack':4,
            'modeledReturnOnSpend':.4,'meanOutcomeRetention':.42,'chanceToRecoverCost':.1,
            'valuePerPackPercentiles':{'p05':0,'p50':2,'p95':10,'p99':30},
            'normalizedReturnPercentiles':{'p50':.2,'p95':1}}


def snapshot():
    return {'id':uid(80),'market_date':DAY,'publication_status':'published',
            'contract_version':V3_CONTRACT,'methodology_version':V3_METHOD,'weighting_version':V3_WEIGHT,
            'payload_json':{'openingEconomics':{'contractVersion':V3_CONTRACT,'marketDate':DAY,
                'basis':V3_BASIS,'status':'available','methodology':{'version':V3_METHOD,'weightingVersion':V3_WEIGHT}}}}


def test_v3_evidence_no_medians_or_ratios_recomputed():
    values=evidence_from_scope(scope())
    assert values['p50_value_per_pack']==2 and values['mean_outcome_retention']==Decimal('.42')
    assert values['p10_value_per_pack'] is None
    assert 'top_1pct_mean_per_pack' not in values
    assert values['modeled_return_on_spend']==Decimal('.4')


@pytest.mark.parametrize('field,value',[('contract_version','v2'),('publication_status','staged'),('market_date','2026-09-24'),('weighting_version','wrong')])
def test_bad_v3_snapshot(field,value):
    s=snapshot();s[field]=value
    with pytest.raises(BenchmarkError):compatible_v3(s,DAY)


def test_v3_valid_and_nested_version_required():
    assert compatible_v3(snapshot(),DAY)['status']=='available'
    s=snapshot();s['payload_json']['openingEconomics']['basis']='loose_pack'
    with pytest.raises(BenchmarkError):compatible_v3(s,DAY)


def test_sparse_quantile_inversion_rejected():
    s=scope();s['valuePerPackPercentiles']['p05']=3
    with pytest.raises(BenchmarkError):evidence_from_scope(s)


def test_financial_evidence_survives_missing_model():
    r=metric_row(entity_type='set',entity_id=uid(1),metric_key='financial',market_date=DAY)
    out=attach_evidence(r,evidence_from_scope(scope()),market_date=DAY,source_snapshot_id=uid(80))
    assert out['model_status']=='unavailable' and out['raw_model_value'] is None
    assert out['financial_evidence_status']=='available' and out['expected_value_per_pack']==4
    assert r['financial_evidence_status']=='unavailable'


def test_era_identity_uses_snapshot_member_ids():
    members=[{'setId':uid(1),'eraName':'Era A','eraId':uid(4)}, {'setId':uid(2),'eraName':'Era A','eraId':uid(4)}]
    eras=[{'eraName':'Era A','setCount':2}]
    assert map_era_identities(members,eras)=={'Era A':uid(4)}
    members[1]['eraId']=uid(5)
    with pytest.raises(BenchmarkError):map_era_identities(members,eras)


def test_era_partition_missing_and_duplicate_rejected():
    members=[{'setId':uid(1),'eraName':'Era A','eraId':uid(4)}]
    for eras in [[],[{'eraName':'Unknown','setCount':1}],[{'eraName':'Era A','setCount':2}]]:
        with pytest.raises(BenchmarkError):map_era_identities(members,eras)


def product():
    return {'id':uid(100),'sealed_product_id':uid(10),'set_id':uid(1),'calculation_run_id':uid(20),
            'pack_count':10,'random_pack_count':10,'price_as_of':DAY,'product_market_cost':100,
            'expected_value':50,'median_value':30,'p95_value':120,'p99_value':200,
            'guaranteed_component_market_value':10,'accessory_value_included':False,
            'chance_to_recover_cost':.1,'expected_loss_when_losing':70}


def test_exact_product_selection_ignores_other_runs_not_arbitrary_duplicates():
    published=[{'sealedProductId':uid(10),'setId':uid(1),'calculationRunId':uid(20)}]
    newer={**product(),'id':uid(101),'calculation_run_id':uid(21),'expected_value':99}
    assert select_exact_product_results(published,[newer,product()],run_by_set={uid(1):uid(20)})==[product()]
    with pytest.raises(BenchmarkError):select_exact_product_results(published,[product(),product()],run_by_set={uid(1):uid(20)})
    with pytest.raises(BenchmarkError):select_exact_product_results(published*2,[product()],run_by_set={uid(1):uid(20)})


def test_product_normalization_counts_guaranteed_value_once():
    p=product();e=product_evidence(p,market_date=DAY,expected_run_id=uid(20),expected_result_id=uid(100))
    assert e['expected_value_per_pack']==5  # NOT (50+10)/10
    assert e['cost_per_pack']==10 and e['p50_value_per_pack']==3
    assert e['normalized_p50']==Decimal('.3') and e['chance_to_recover_cost']==Decimal('.1')
    assert 'p10_value_per_pack' not in e


@pytest.mark.parametrize('field,value',[('pack_count',0),('pack_count',2.5),('random_pack_count',None),('random_pack_count',9),('accessory_value_included',True),('price_as_of','2026-09-24')])
def test_invalid_product_evidence(field,value):
    p=product();p[field]=value
    with pytest.raises(BenchmarkError): product_evidence(p,market_date=DAY,expected_run_id=uid(20),expected_result_id=uid(100))


def header():
    return {'id':uid(999),'market_date':DAY,'benchmark_key':'fixture','calibration_version':'unapproved',
            'active_overall_publication_id':uid(900),'expected_entity_count':1,'expected_row_count':4,
            'cohort_fingerprint':'a'*64,'source_fingerprint':'b'*64,
            **{m+'_model_version':m+'-fixture' for m in ['financial','chase','collector','overall']},
            'collector_lineage_status':'embedded_source','source_manifest':{'synthetic':True}}


def test_candidate_is_dry_run_and_deterministic_only():
    rows=[row(m) for m in ['financial','chase','collector','overall']]
    a=candidate_request(header(),rows)
    b=candidate_request(header(),rows[::-1])
    assert a==b and a['mode']=='dry_run_only' and not a['production_publish_enabled']
    assert 'request_fingerprint' not in a['arguments']['p_header']


def test_candidate_missing_duplicate_server_keys():
    rows=[row(m) for m in ['financial','chase','collector','overall']]
    for bad in [rows[:3],rows[:3]+[rows[0]],[{**rows[0],'raw_delta':1}]+rows[1:]]:
        with pytest.raises(BenchmarkError):candidate_request(header(),bad)
    with pytest.raises(BenchmarkError):candidate_request({**header(),'request_fingerprint':'c'*64},rows)


def test_all_windows_are_bounded_and_do_not_overlap():
    from datetime import date,timedelta
    windows=history_windows('2024-01-01','2026-09-25')
    assert windows[0][0]=='2024-01-01' and windows[-1][1]==DAY
    for start,end in windows:assert 0<=(date.fromisoformat(end)-date.fromisoformat(start)).days<=365
    for a,b in zip(windows,windows[1:]):assert date.fromisoformat(a[1])+timedelta(days=1)==date.fromisoformat(b[0])


def reader(data=None, deny=False):
    calls=[]
    class Client:
        def rpc(self, name,args):
            calls.append((name,args));return self
        def execute(self):
            return SimpleNamespace(data=data or {'contract_version':'rip-benchmark-read-v1','rows':[]})
    def access():
        calls.append('authorize')
        if deny:raise PermissionError('not entitled')
    def factory(timeout):calls.append(('timeout',timeout));return Client()
    return PrivateBenchmarkReader(require_access=access,client_factory=factory),calls


ENT=[{'entity_type':'set','entity_id':uid(1)}]
KW={'benchmark_key':'fixture','calibration_version':'fixture'}


def test_authorization_before_database_even_empty_response():
    r,calls=reader(deny=True)
    with pytest.raises(PermissionError):r.current(ENT,**KW)
    assert calls==['authorize']


def test_current_one_rpc_no_stale_fallback():
    r,calls=reader({'contract_version':'rip-benchmark-read-v1','status':'unavailable','reason':'no_published_benchmark','rows':[]})
    assert r.current(ENT,**KW)['reason']=='no_published_benchmark'
    assert calls[0]=='authorize' and calls[1]==('timeout',10.0) and calls[2][0]==CURRENT_RPC and len(calls)==3


@pytest.mark.parametrize('bad',[[],ENT*2,[{'entity_type':'card','entity_id':uid(1)}],ENT*11])
def test_bad_selectors_no_database(bad):
    r,calls=reader()
    with pytest.raises(BenchmarkError):r.current(bad,**KW)
    assert calls==[]


def test_history_passes_exact_cursor_and_date_bounds():
    r,calls=reader();cursor={'query_signature':'fixture'}
    r.history_page(ENT,start_date=DAY,end_date=DAY,after=cursor,limit=2,**KW)
    assert calls[-1][0]==HISTORY_RPC and calls[-1][1]['p_after']==cursor and calls[-1][1]['p_limit']==2
    with pytest.raises(BenchmarkError):r.history_page(ENT,start_date='2024-01-01',end_date=DAY,**KW)


def test_read_rejects_private_lineage_even_nested():
    r,_=reader({'contract_version':'rip-benchmark-read-v1','rows':[{'source_lineage':{'secret':'fixture'}}]})
    with pytest.raises(BenchmarkError):r.current(ENT,**KW)


def test_revision_conflict_not_retried_or_swallowed():
    calls=[]
    class Client:
        def rpc(self,*_):calls.append('rpc');return self
        def execute(self):raise RuntimeError('history publications changed; restart pagination')
    r=PrivateBenchmarkReader(require_access=lambda:None,client_factory=lambda _:Client())
    with pytest.raises(RuntimeError,match='restart pagination'):r.history_page(ENT,start_date=DAY,end_date=DAY,**KW)
    assert calls==['rpc']


def test_cli_cannot_enable_production_publish():
    from backend.scripts.run_rip_benchmark_v1 import main
    with pytest.raises(SystemExit):main(['prepare','--input','candidate.json','--commit'])


def test_cli_prepares_offline_without_importing_supabase(tmp_path,capsys):
    import json
    from backend.scripts.run_rip_benchmark_v1 import main
    p=tmp_path/'request.json'
    p.write_text(json.dumps(wire({'header':header(),'rows':[row(m) for m in ['financial','chase','collector','overall']]})),encoding='utf-8')
    assert main(['prepare','--input',str(p)])==0
    assert json.loads(capsys.readouterr().out)['production_publish_enabled'] is False


def test_reconstruction_proof_is_explicit_not_assumed():
    s=source();del s['reconstruction_status']
    with pytest.raises(BenchmarkError):row(src=s)
    s['reconstruction_status']='inherited_parent_set'
    with pytest.raises(BenchmarkError):row(src=s)


def test_boolean_access_denial_cannot_reach_database():
    r=PrivateBenchmarkReader(require_access=lambda:False,client_factory=lambda _:pytest.fail('DB accessed'))
    with pytest.raises(PermissionError):r.current(ENT,**KW)


def test_oversized_response_fails_closed():
    r,_=reader({'contract_version':'rip-benchmark-read-v1','rows':[{}]*5})
    with pytest.raises(BenchmarkError):r.current(ENT,**KW)


def test_available_benchmark_cannot_claim_a_different_header_calibration():
    rows=[row(m) for m in ['financial','chase','collector','overall']]
    rows[0]=row(reference=ref(),calibration=CAL)
    with pytest.raises(BenchmarkError,match='calibration version'):candidate_request(header(),rows)
    assert candidate_request({**header(),'calibration_version':CAL.version},rows)['mode']=='dry_run_only'
