"""Global reference regression suite. Disposable PostgreSQL only; no production credentials.
Run with PGHOST=127.0.0.1 PGDATABASE=benchmark_test and RIP_REFERENCE_MIGRATION set.
Runs the unchanged 46-check foundation suite first, retaining its 237,168-row scale fixture.
"""
from __future__ import annotations
import copy
import datetime as dt
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / 'benchmark-test-output'
if os.environ.get('PGHOST') not in ('127.0.0.1', 'localhost') or os.environ.get('PGDATABASE') != 'benchmark_test':
    raise SystemExit('Refusing non-isolated PostgreSQL target')
migration = Path(os.environ['RIP_REFERENCE_MIGRATION']).resolve()
if not migration.is_relative_to(ROOT):
    raise SystemExit('Migration must be in this checkout')
original_argv = sys.argv[:]
sys.argv = [str(ROOT / 'backend/tests/integration/rip_benchmark_v1_postgres.py')]
base = runpy.run_path(sys.argv[0])
sys.argv = original_argv
(OUT / 'foundation-results.json').write_bytes((OUT / 'results.json').read_bytes())
(OUT / 'foundation-plans.json').write_bytes((OUT / 'plans.json').read_bytes())


def sql(text, *, role=None, error=None):
    command = (f'SET ROLE {role};\n' if role else '') + text
    p = subprocess.run(['psql', '-X', '-A', '-t', '-v', 'ON_ERROR_STOP=1'],
                       input=command, text=True, capture_output=True, timeout=45)
    if error is not None:
        assert p.returncode != 0 and error.lower() in p.stderr.lower(), (error, p.stdout, p.stderr)
        return p.stderr
    assert p.returncode == 0, p.stderr
    return '\n'.join(x for x in p.stdout.splitlines() if x not in ('SET','BEGIN','COMMIT','ROLLBACK'))


def lit(value):
    return "'" + json.dumps(value, separators=(',', ':')).replace("'", "''") + "'::jsonb"


def decode(value):
    return json.loads(value, parse_float=Decimal)


def uid():
    return str(uuid.uuid4())


checks = []
def ok(name):
    checks.append(name)
    print('PASS reference:', name, flush=True)


METHOD = 'hierarchical_product_per_pack_empirical_v1'
WEIGHT = 'equal-set_equal-family_equal-sku-v1'
CONTRACT = 'pokemon-rip-stats-v3'
BASIS = 'all_modeled_products_per_pack_equivalent'
DAY = '2026-09-25'
SOURCE = base['ST']
ENTITIES = base['ENT']
original_header = copy.deepcopy(base['H'])
original_rows = copy.deepcopy(base['rows'])
# Extend only this disposable fixture to match the already-existing production source schema.
sql('ALTER TABLE pokemon_rip_stats_snapshots ADD COLUMN payload_json jsonb, ADD COLUMN source_run_fingerprint text;')


def payload(day=DAY, cost=20.125, ev=10.26375, ros=0.5100000000000001, mean=0.63):
    return {'contractVersion': CONTRACT, 'marketDate': day,
            'openingEconomics': {'contractVersion': CONTRACT, 'marketDate': day, 'basis': BASIS,
              'status': 'available', 'methodology': {'version': METHOD, 'weightingVersion': WEIGHT},
              'inputFingerprint': 'c' * 64,
              'global': {'averageCostPerPack': cost, 'averageModelBreakEvenPerPack': ev,
                         'modeledReturnOnSpend': ros, 'meanOutcomeRetention': mean,
                         'coverageStatus': 'complete', 'methodologyVersion': METHOD, 'weightingVersion': WEIGHT},
              # Deliberately misleading set medians/percentages must not be used for the reference.
              'sets': [{'typicalOpeningPerPack': 999, 'modeledReturnOnSpend': .99}],
              'eras': [{'typicalOpeningPerPack': 888, 'modeledReturnOnSpend': .88}]}}


P1 = payload()
sql(f"UPDATE pokemon_rip_stats_snapshots SET payload_json={lit(P1)},source_run_fingerprint='{'b'*64}' WHERE id='{SOURCE}';")
protected_query = "SELECT md5((SELECT jsonb_agg(to_jsonb(p) ORDER BY scope)::text FROM pokemon_overall_rip_current_publication p)||(SELECT jsonb_agg(to_jsonb(p) ORDER BY scope)::text FROM pokemon_collector_appeal_current p));"
protected = sql(protected_query)
old_columns = decode(sql("SELECT json_agg(attname ORDER BY attnum) FROM pg_attribute WHERE attrelid='pokemon_rip_benchmark_publications_v1'::regclass AND attnum>0 AND NOT attisdropped;"))
old_projection = 'SELECT ' + ','.join(old_columns) + ' FROM pokemon_rip_benchmark_publications_v1 ORDER BY id'
old_state = sql('SELECT md5(jsonb_agg(to_jsonb(x))::text) FROM (' + old_projection + ') x;')
old_rows = sql('SELECT count(*) FROM pokemon_rip_benchmark_rows_v1;')
publisher_definition = sql("SELECT pg_get_functiondef('publish_pokemon_rip_benchmark_v1(jsonb,jsonb,uuid)'::regprocedure);")
source_state = sql('SELECT md5(jsonb_agg(to_jsonb(x) ORDER BY id)::text) FROM pokemon_rip_stats_snapshots x;')
sql('BEGIN;\n' + migration.read_text(encoding='utf-8') + '\nCOMMIT;')
assert old_state == sql('SELECT md5(jsonb_agg(to_jsonb(x))::text) FROM (' + old_projection + ') x;')
assert old_rows == sql('SELECT count(*) FROM pokemon_rip_benchmark_rows_v1;')
assert source_state == sql('SELECT md5(jsonb_agg(to_jsonb(x) ORDER BY id)::text) FROM pokemon_rip_stats_snapshots x;')
assert publisher_definition == sql("SELECT pg_get_functiondef('publish_pokemon_rip_benchmark_v1(jsonb,jsonb,uuid)'::regprocedure);")
ok('migration preserves existing headers, rows, source snapshots and publisher definition')
assert sql("SELECT count(*) FROM pokemon_rip_benchmark_publications_v1 WHERE global_financial_reference_status<>'unavailable' OR global_cost_per_pack IS NOT NULL;") == '0'
ok('legacy publications remain explicitly unavailable; no silent backfill')


def make_request(*, key='global-reference-fixture', day=DAY, source=SOURCE):
    h = copy.deepcopy(original_header)
    h.update(id=uid(), market_date=day, benchmark_key=key, opening_economics_snapshot_id=source)
    r = copy.deepcopy(original_rows)
    for row in r:
        row['source_market_date'] = day
        if row['metric_key'] == 'financial':
            row['financial_evidence_market_date'] = day
    return h, r


def publish(h, r, prior=None, error=None):
    return sql('SELECT publish_pokemon_rip_benchmark_v1(' + lit(h) + ',' + lit(r) + ',' +
               ('NULL' if prior is None else "'" + prior + "'::uuid") + ');', role='service_role', error=error)


def current(key='global-reference-fixture', entities=ENTITIES):
    return decode(sql('SELECT get_pokemon_rip_benchmark_current_v1(' + lit(entities) + ", '" + key + "','test-calibration-1');", role='service_role'))


def history(*, limit=5, after=None, start=DAY, end='2026-09-26', key='global-reference-fixture', entities=ENTITIES, error=None):
    result = sql('SELECT get_pokemon_rip_benchmark_history_v1(' + lit(entities) + f",'{start}','{end}','{key}','test-calibration-1',{limit}," +
                 ('NULL' if after is None else lit(after)) + ');', role='service_role', error=error)
    return result if error else decode(result)


h1, r1 = make_request()
assert publish(h1, r1) == h1['id']
assert publish(h1, r1) == h1['id']
ref1 = current()['opening_economics_reference']
assert ref1['status'] == 'available' and ref1['snapshot_id'] == SOURCE
assert ref1['market_date'] == ref1['source_market_date'] == DAY
assert ref1['cost_per_pack'] == Decimal('20.125') and ref1['expected_value_per_pack'] == Decimal('10.26375')
assert ref1['modeled_return_on_spend'] == Decimal('0.5100000000000001') and ref1['mean_outcome_retention'] == Decimal('0.63')
assert ref1['source_fingerprint'] == 'b'*64 and ref1['input_fingerprint'] == 'c'*64 and len(ref1['global_fingerprint']) == 64
ok('exact same-date V3 global values, decimal precision and source lineage')
for row in current()['rows']:
    assert row['opening_economics_reference'] == ref1
    assert row['benchmark_raw_value'] == 50 and row['benchmark_score'] == 5
    if row['metric_key'] == 'financial':
        assert row['cost_per_pack'] == 10 and row['expected_value_per_pack'] == 4 and row['modeled_return_on_spend'] == Decimal('.4')
ok('set/era/product chart points preserve entity evidence and separate model benchmark')
assert ref1['modeled_return_on_spend'] != ref1['mean_outcome_retention']
assert ref1['modeled_return_on_spend'] != ref1['expected_value_per_pack']/ref1['cost_per_pack']
ok('global source copied rather than set averages, medians, ratio recomputation or mean retention')


def snapshot(p, *, day=DAY, contract=CONTRACT, method=METHOD, weight=WEIGHT, status='published', fingerprint='d'*64):
    sid = uid()
    sql(f"INSERT INTO pokemon_rip_stats_snapshots(id,market_date,publication_status,contract_version,methodology_version,weighting_version,payload_json,source_run_fingerprint) VALUES('{sid}','{day}','{status}','{contract}','{method}','{weight}',{lit(p)}," + ('NULL' if fingerprint is None else "'"+fingerprint+"'") + ');')
    return sid


source2 = snapshot(payload('2026-09-26',30,18,.6,.77), day='2026-09-26')
assert current()['opening_economics_reference'] == ref1
ok('no latest-snapshot fallback on reads')
h2, r2 = make_request(day='2026-09-26', source=source2)
publish(h2, r2)
ref2 = current()['opening_economics_reference']
assert ref2['snapshot_id'] == source2 and ref2['cost_per_pack'] == 30 and ref2['modeled_return_on_spend'] == Decimal('.6')
page = history()
all_rows = page['rows'][:]
while page['has_more']:
    page = history(after=page['next_cursor'])
    all_rows += page['rows']
assert len(all_rows) == 24 and len({(x['publication_id'],x['entity_type'],x['entity_id'],x['metric_key']) for x in all_rows}) == 24
assert all(x['opening_economics_reference'] == (ref1 if x['market_date']==DAY else ref2) for x in all_rows)
ok('history pagination carries the contemporaneous publication reference on every point')
# Read-time source access is impossible under this temporary fixture grant: both RPCs must still work.
sql('REVOKE SELECT ON pokemon_rip_stats_snapshots FROM service_role;')
assert current()['opening_economics_reference'] == ref2
assert history(limit=1000)['rows'] == all_rows
sql('GRANT SELECT ON pokemon_rip_stats_snapshots TO service_role;')
ok('current/history require no source-table permission or request-time source scan')

# Missing reference stays independent of model/evidence availability.
h, rows = make_request(key='no-snapshot', source=None)
h['opening_economics_contract_version'] = None
h['opening_economics_basis'] = None
for r in rows:
    if r['metric_key']=='financial':
        for field in list(r):
            if field.endswith('_per_pack') or field.startswith('normalized_p') or field in ('chance_to_recover_cost','modeled_return_on_spend','mean_outcome_retention','top_1pct_ev_share'):
                r[field] = None
        r.update(financial_evidence_status='unavailable', financial_evidence_reason='fixture missing snapshot', financial_evidence_market_date=None)
publish(h, rows)
missing = current('no-snapshot')['opening_economics_reference']
assert missing['status']=='unavailable' and missing['reason']=='opening_economics_snapshot_missing'
assert all(missing[k] is None for k in ('cost_per_pack','expected_value_per_pack','modeled_return_on_spend','mean_outcome_retention'))
ok('missing snapshot is unavailable, never zero or an invented global entity')

cases = []
p=payload(); del p['openingEconomics']['global']; cases.append(('missing global scope',p,'opening_economics_global_scope_missing'))
p=payload(); del p['openingEconomics']['global']['modeledReturnOnSpend']; cases.append(('missing required global value',p,'opening_economics_global_values_missing'))
p=payload(); p['openingEconomics']['global']['coverageStatus']='partial'; cases.append(('partial global coverage',p,'opening_economics_global_coverage_incomplete'))
p=payload(); p['openingEconomics']['status']='unavailable'; cases.append(('unavailable source',p,'opening_economics_unavailable'))
p=payload(); del p['openingEconomics']; cases.append(('absent Opening Economics scope',p,'opening_economics_scope_missing'))
for name,p,reason in cases:
    h, rows=make_request(key=uid(),source=snapshot(p)); publish(h,rows)
    result=current(h['benchmark_key'])
    assert result['opening_economics_reference']['reason']==reason
    assert result['opening_economics_reference']['status']=='unavailable'
    assert all(result['opening_economics_reference'][k] is None for k in ('cost_per_pack','expected_value_per_pack','modeled_return_on_spend','mean_outcome_retention'))
    assert next(r for r in result['rows'] if r['metric_key']=='financial')['expected_value_per_pack']==4
    ok(name+' preserves entity evidence without a reference')
p=payload(); del p['openingEconomics']['global']['meanOutcomeRetention']
h,rows=make_request(key=uid(),source=snapshot(p));publish(h,rows)
assert current(h['benchmark_key'])['opening_economics_reference']['status']=='available'
assert current(h['benchmark_key'])['opening_economics_reference']['mean_outcome_retention'] is None
ok('optional global mean retention absent without substituting another statistic')
h,rows=make_request(key=uid(),source=snapshot(payload(),fingerprint=None));publish(h,rows)
assert current(h['benchmark_key'])['opening_economics_reference']['reason']=='opening_economics_source_fingerprint_missing'
ok('missing source fingerprint cannot produce an available reference')

bad = []
p=payload(); p['openingEconomics']['contractVersion']='pokemon-rip-stats-v2'; bad.append(('payload V2 refused',p,'incompatible V3'))
p=payload(); p['openingEconomics']['basis']='one_pack_per_set'; bad.append(('wrong payload basis refused',p,'incompatible V3'))
p=payload(); p['openingEconomics']['marketDate']='2026-09-24'; bad.append(('payload date mismatch refused',p,'incompatible V3'))
p=payload(); p['marketDate']='2026-09-24'; bad.append(('outer payload date mismatch refused',p,'incompatible V3'))
p=payload(); p['openingEconomics']['methodology']['weightingVersion']='wrong'; bad.append(('wrong weighting refused',p,'incompatible V3'))
p=payload(); p['openingEconomics']['global']['methodologyVersion']='wrong'; bad.append(('incompatible global scope refused',p,'incompatible V3'))
for field,value in [('averageCostPerPack','NaN'),('averageModelBreakEvenPerPack','Infinity'),('modeledReturnOnSpend','0.5'),('meanOutcomeRetention',False)]:
    p=payload();p['openingEconomics']['global'][field]=value;bad.append(('invalid '+field,p,'invalid numeric'))
for field,value in [('averageCostPerPack',0),('averageCostPerPack',-1),('averageModelBreakEvenPerPack',-1),('modeledReturnOnSpend',-1),('meanOutcomeRetention',-1)]:
    p=payload();p['openingEconomics']['global'][field]=value;bad.append(('out of bounds '+field+str(value),p,'check constraint'))
for name,p,error in bad:
    h,rows=make_request(key=uid(),source=snapshot(p));publish(h,rows,error=error)
    assert sql(f"SELECT count(*) FROM pokemon_rip_benchmark_publications_v1 WHERE id='{h['id']}';")=='0'
    ok(name+'; whole publication rolled back')
for sid in (snapshot(payload(),contract='pokemon-rip-stats-v2'),source2):
    h,rows=make_request(key=uid(),source=sid);publish(h,rows,error='incompatible Opening Economics authority')
ok('wrong source-row contract and source-row date refused')
h,rows=make_request(key=uid());h['global_cost_per_pack']=123;publish(h,rows,error='unknown header field')
ok('caller cannot inject reference values through existing publisher')
p=payload(cost=10,ev=0,ros=0,mean=0)
h,rows=make_request(key=uid(),source=snapshot(p));publish(h,rows)
assert current(h['benchmark_key'])['opening_economics_reference']['modeled_return_on_spend']==0
ok('proven true zero is available and distinguishable from missing evidence')
p=payload(cost=10,ev=20,ros=2,mean=3)
h,rows=make_request(key=uid(),source=snapshot(p));publish(h,rows)
assert current(h['benchmark_key'])['opening_economics_reference']['modeled_return_on_spend']==2
ok('return ratios are not incorrectly capped as probabilities')

# Freeze exact revision; even source corrections cannot rewrite an existing chart point.
old_cursor=history()['next_cursor']
sql(f"UPDATE pokemon_rip_stats_snapshots SET payload_json={lit(payload(cost=40,ev=28,ros=.7,mean=.8))} WHERE id='{SOURCE}';")
assert publish(h1,r1)==h1['id']
assert history(limit=1000)['rows'][0]['opening_economics_reference']==ref1
ok('reference remains frozen across source corrections and idempotent retries')
h1new=copy.deepcopy(h1);h1new['id']=uid();publish(h1new,r1,prior=h1['id'])
history(after=old_cursor,error='publications changed')
new_rows=history(limit=1000)['rows']
new_ref=next(r['opening_economics_reference'] for r in new_rows if r['market_date']==DAY)
assert new_ref['cost_per_pack']==40 and new_ref['global_fingerprint']!=ref1['global_fingerprint']
assert all(r['opening_economics_reference']==ref2 for r in new_rows if r['market_date']!='2026-09-25')
retained=decode(sql(f"SELECT project_rip_benchmark_global_reference_v1(p) FROM pokemon_rip_benchmark_publications_v1 p WHERE id='{h1['id']}';",role='service_role'))
assert retained==ref1
ok('revision replacement invalidates cursor, retains old reference, and leaves other dates unchanged')
sql(f"UPDATE pokemon_rip_benchmark_publications_v1 SET global_cost_per_pack=999 WHERE id='{h1new['id']}';",role='service_role',error='immutable')
sql(f"UPDATE pokemon_rip_benchmark_publications_v1 SET opening_economics_source_fingerprint='{'f'*64}' WHERE id='{h1['id']}';",role='service_role',error='immutable')
ok('new reference values and lineage inherit publication immutability')

for role in ('anon','authenticated'):
    for q in ("SELECT global_cost_per_pack FROM pokemon_rip_benchmark_publications_v1;",
              "SELECT project_rip_benchmark_global_reference_v1(null::pokemon_rip_benchmark_publications_v1);",
              "SELECT capture_rip_benchmark_global_reference_v1();",
              'SELECT get_pokemon_rip_benchmark_current_v1('+lit(ENTITIES)+",'global-reference-fixture','test-calibration-1');",
              'SELECT get_pokemon_rip_benchmark_history_v1('+lit(ENTITIES)+",'2026-09-25','2026-09-26','global-reference-fixture','test-calibration-1');"):
        sql(q,role=role,error='permission denied')
ok('anonymous/authenticated denial includes new columns, helper, trigger and both read RPCs')
assert sql("SELECT count(*) FROM pg_class WHERE oid IN ('pokemon_rip_benchmark_publications_v1'::regclass,'pokemon_rip_benchmark_rows_v1'::regclass) AND relrowsecurity;")=='2'
assert sql("SELECT count(*) FROM pg_proc WHERE proname IN ('capture_rip_benchmark_global_reference_v1','project_rip_benchmark_global_reference_v1','get_pokemon_rip_benchmark_history_v1','get_pokemon_rip_benchmark_current_v1') AND prosecdef;")=='0'
ok('RLS and security-invoker boundary retained')
history(entities=[],error='1..10')
history(entities=[{'entity_type':'set','entity_id':uid()} for _ in range(11)],error='1..10')
history(start='2025-09-25',end='2026-09-26',error='366')
history(start='2025-09-26',end='2026-09-26',limit=1000)
history(limit=1001,error='bounds')
ok('1–10 entities, 366 inclusive days and 1,000-row cap unchanged')
assert protected==sql(protected_query)
ok('Overall/Rankings/set-page and Collector pointer fixtures unchanged')

# Exercise the unmodified PR389 request builder against the extended database contract.
from backend.domain.pokemon.rip_benchmark_v1 import wire
from backend.benchmarking.preview_v1 import candidate_request
from backend.benchmarking.evidence_v1 import attach_evidence,evidence_from_scope
from backend.tests.benchmark_v1.test_core import CAL,header,ref,row,scope,source
bh=header();bh.update(id=uid(),active_overall_publication_id=base['A'],calibration_version=CAL.version,
  opening_economics_snapshot_id=SOURCE,opening_economics_contract_version=CONTRACT,opening_economics_basis=BASIS)
br=[row(m) for m in ('financial','chase','collector','overall')]
br[0]=attach_evidence(row(src=source(raw='50.001'),reference=ref(),calibration=CAL),evidence_from_scope(scope()),market_date=DAY,source_snapshot_id=SOURCE)
args=wire(candidate_request(bh,br)['arguments'])
assert publish(args['p_header'],args['p_rows'])==bh['id']
bcurrent=decode(sql('SELECT get_pokemon_rip_benchmark_current_v1('+lit([{'entity_type':'set','entity_id':br[0]['entity_id']}])+",'fixture','shadow-fixture');",role='service_role'))
assert bcurrent['opening_economics_reference']['status']=='available'
assert next(r for r in bcurrent['rows'] if r['metric_key']=='financial')['benchmark_score']==Decimal('5.0001')
ok('unchanged PR389-generated request remains compatible and automatically captures reference')

# Loaded-read regression: baseline 237,168-row fixture plus the reference-specific cases above.
plans={}
for days in (1,7,30,366):
    end=dt.date(2026,9,26);start=end-dt.timedelta(days=days-1)
    q='SELECT get_pokemon_rip_benchmark_history_v1('+lit(base['entities'])+f",'{start}','{end}','scale-cohort','scale-calibration-1',1000);"
    plans[str(days)+'D_rpc']=decode(sql('EXPLAIN (ANALYZE,BUFFERS,FORMAT JSON) '+q,role='service_role'))
    result=decode(sql(q,role='service_role'))
    assert len(result['rows'])<=1000 and all('opening_economics_reference' in r for r in result['rows'])
plans['366D_indexed_rows']=decode(sql('EXPLAIN (ANALYZE,BUFFERS,FORMAT JSON) '+base['q']))
assert 'rip_benchmark_row_history_v1' in json.dumps(plans['366D_indexed_rows'],default=str)
plans['current_rpc']=decode(sql('EXPLAIN (ANALYZE,BUFFERS,FORMAT JSON) SELECT get_pokemon_rip_benchmark_current_v1('+lit(base['entities'])+",'scale-cohort','scale-calibration-1');",role='service_role'))
ok('bounded current/1D/7D/30D/366D projections on production-cardinality fixture')
assert protected==sql(protected_query)
result={'passed':len(checks),'checks':checks,'foundation_checks':len(base['checks']),
        'scale_rows':237168,'migration':migration.name,'migration_sha256':hashlib.sha256(migration.read_bytes()).hexdigest(),
        'postgres_version':sql('SHOW server_version;'),'pointer_fingerprint':protected,
        'reference_example':new_ref,'scope':'disposable PostgreSQL only; no production writes'}
(OUT/'global-reference-results.json').write_text(json.dumps(result,indent=2,default=str))
(OUT/'global-reference-plans.json').write_text(json.dumps(plans,indent=2,default=str))
print('GLOBAL_REFERENCE_RESULT',json.dumps(result,default=str),flush=True)
