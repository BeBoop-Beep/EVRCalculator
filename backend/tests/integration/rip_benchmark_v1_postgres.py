"""Isolated PostgreSQL 17 contract/scale proof. Never connect this test to production.
Run with PGHOST=127.0.0.1 PGPORT=5432 PGUSER=postgres PGDATABASE=benchmark_test.
The database must be an empty disposable local/CI database; source authorities are fixtures.
"""
from __future__ import annotations
import copy, datetime as dt, hashlib, json, os, pathlib, subprocess, sys, time, uuid

ROOT=pathlib.Path(__file__).resolve().parents[3]
OUT=ROOT/'benchmark-test-output'; OUT.mkdir(exist_ok=True)
if os.environ.get('PGHOST') not in ('127.0.0.1','localhost') or os.environ.get('PGDATABASE')!='benchmark_test':
    raise SystemExit('Refusing non-isolated database')
SQL=pathlib.Path(sys.argv[1]) if len(sys.argv)>1 else ROOT/'backend/db/benchmarks/rip_benchmark_foundation_v1.sql'

def sql(q: str, *, role: str|None=None, fail: str|None=None):
    p=subprocess.run(['psql','-X','-A','-t','-v','ON_ERROR_STOP=1'],input=(f'SET ROLE {role};\n' if role else '')+q,text=True,capture_output=True)
    if fail:
        if p.returncode==0 or fail.lower() not in p.stderr.lower(): raise AssertionError((fail,p.stdout,p.stderr))
        return p.stderr
    if p.returncode: raise AssertionError(p.stderr)
    return '\n'.join(l for l in p.stdout.splitlines() if l not in ('SET','BEGIN','COMMIT','ROLLBACK'))

def val(x): return "'"+json.dumps(x,separators=(',',':')).replace("'","''")+"'::jsonb"
def uid(): return str(uuid.uuid4())
A=uid(); RG=uid(); SG=uid(); ST=uid(); C=uid(); SET=uid(); ERA=uid(); PRODUCT=uid()
fp='a'*64
sql('''CREATE ROLE anon; CREATE ROLE authenticated; CREATE ROLE service_role BYPASSRLS;
GRANT USAGE ON SCHEMA public TO anon,authenticated,service_role;
CREATE TABLE public.pokemon_overall_rip_publication_runs(id uuid primary key,market_date date,status text,model_version text,financial_version text,chase_version text,collector_version text,collector_run_id uuid,formula_fingerprint text,cohort_fingerprint text,validation_json jsonb);
CREATE TABLE public.pokemon_overall_rip_current_publication(scope text primary key,publication_run_id uuid,rankings_generation_id uuid,set_page_generation_id uuid,activated_at timestamptz);
CREATE TABLE public.pokemon_rip_stats_snapshots(id uuid primary key,market_date date,publication_status text,contract_version text,methodology_version text,weighting_version text);
CREATE TABLE public.pokemon_collector_appeal_current(scope text,model_run_id uuid);
GRANT SELECT ON public.pokemon_overall_rip_publication_runs,public.pokemon_overall_rip_current_publication,public.pokemon_rip_stats_snapshots TO service_role;
''')
sql(f"INSERT INTO public.pokemon_overall_rip_publication_runs VALUES('{A}','2026-09-25','published','overall-test','financial-test','chase-test','collector-test','{C}','{fp}','{fp}','{{}}'); INSERT INTO public.pokemon_overall_rip_current_publication VALUES('pokemon','{A}','{RG}','{SG}',now()); INSERT INTO public.pokemon_rip_stats_snapshots VALUES('{ST}','2026-09-25','published','pokemon-rip-stats-v3','hierarchical_product_per_pack_empirical_v1','equal-set_equal-family_equal-sku-v1'); INSERT INTO public.pokemon_collector_appeal_current VALUES('pokemon','{C}');")
before=sql("SELECT md5((SELECT jsonb_agg(to_jsonb(x))::text FROM pokemon_overall_rip_current_publication x)||(SELECT jsonb_agg(to_jsonb(x))::text FROM pokemon_collector_appeal_current x));")
sql('BEGIN;\n'+SQL.read_text()+'\nCOMMIT;')
H=dict(id=uid(),market_date='2026-09-25',benchmark_key='test-cohort',calibration_version='test-calibration-1',expected_entity_count=3,expected_row_count=12,cohort_fingerprint=fp,source_fingerprint=fp,overall_model_version='overall-test',financial_model_version='financial-test',chase_model_version='chase-test',collector_model_version='collector-test',collector_run_id=C,collector_lineage_status='exact_run',active_overall_publication_id=A,opening_economics_snapshot_id=ST,opening_economics_contract_version='pokemon-rip-stats-v3',opening_economics_basis='all_modeled_products_per_pack_equivalent',source_manifest={'proof':'isolated fixture only'})
rows=[]
for typ,eid in [('set',SET),('era',ERA),('sealed_product',PRODUCT)]:
 for metric in ['financial','chase','collector','overall']:
  inherited=typ=='sealed_product' and metric in ('chase','collector')
  r=dict(entity_type=typ,entity_id=eid,metric_key=metric,parent_set_id=SET if typ=='sealed_product' else None,model_status='inherited' if inherited else 'available',benchmark_status='available',raw_model_value=50,benchmark_raw_value=50,benchmark_score=5,rank=None if inherited else 1,cohort_size=None if inherited else 3,source_model_version=metric+'-test',source_market_date='2026-09-25',source_entity_type='set' if inherited else typ,source_entity_id=SET if inherited else eid,source_publication_id=A if metric=='overall' else None,calculation_run_id=uid() if metric=='financial' else None,source_result_id=uid() if typ=='sealed_product' and metric=='financial' else None,collector_run_id=C if metric=='collector' else None,source_fingerprint=fp,benchmark_source_fingerprint=fp,reconstruction_status='inherited_parent_set' if inherited else 'persisted_exact',source_lineage={'proof':'fixture'},financial_evidence_status='available' if metric=='financial' else 'not_applicable')
  if metric=='financial': r.update(financial_evidence_market_date='2026-09-25',cost_per_pack=10,expected_value_per_pack=4,p10_value_per_pack=1,p25_value_per_pack=1.5,p50_value_per_pack=2,p75_value_per_pack=3,p90_value_per_pack=5,p95_value_per_pack=10,p99_value_per_pack=20,chance_to_recover_cost=.05,modeled_return_on_spend=.4)
  rows.append(r)
ENT=[{'entity_type':'set','entity_id':SET},{'entity_type':'era','entity_id':ERA},{'entity_type':'sealed_product','entity_id':PRODUCT}]

def publish(h,r,prior=None,fail=None):
 return sql(f"SELECT public.publish_pokemon_rip_benchmark_v1({val(h)},{val(r)},"+("NULL" if prior is None else "'"+prior+"'::uuid")+");",role='service_role',fail=fail)
def history(limit=500,after=None,entities=ENT,start='2026-09-25',end='2026-09-25'):
 return json.loads(sql(f"SELECT public.get_pokemon_rip_benchmark_history_v1({val(entities)},'{start}','{end}','test-cohort','test-calibration-1',{limit},"+('NULL' if after is None else val(after))+");",role='service_role'))
checks=[]
def ok(name): checks.append(name); print('PASS',name,flush=True)

assert publish(H,rows)==H['id']; ok('atomic complete three-entity publication')
assert publish(H,rows)==H['id']; ok('idempotent exact retry')
r=copy.deepcopy(rows); r[0]['raw_model_value']=51; r[0]['benchmark_score']=6
publish(H,r,fail='idempotency'); ok('idempotency content conflict')
cur=json.loads(sql(f"SELECT get_pokemon_rip_benchmark_current_v1({val(ENT)},'test-cohort','test-calibration-1');",role='service_role'))
assert len(cur['rows'])==12 and all(r['benchmark_score']==5 and r['score_delta']==0 and 'source_lineage' not in r for r in cur['rows']); ok('current bounded projection anchor and no source artifact')
assert all(r['rank'] is None for r in cur['rows'] if r['model_status']=='inherited'); ok('parent-set inheritance without fabricated product ranks')
for role in ['anon','authenticated']:
 for table in ['pokemon_rip_benchmark_publications_v1','pokemon_rip_benchmark_rows_v1']:
  for q in [f'SELECT * FROM {table};',f'DELETE FROM {table};',f'UPDATE {table} SET market_date=market_date;',f'INSERT INTO {table} DEFAULT VALUES;']:
   sql(q,role=role,fail='permission denied')
 for q in [f"SELECT get_pokemon_rip_benchmark_current_v1({val(ENT)},'test-cohort','test-calibration-1');",f"SELECT get_pokemon_rip_benchmark_history_v1({val(ENT)},'2026-09-25','2026-09-25','test-cohort','test-calibration-1');",f"SELECT publish_pokemon_rip_benchmark_v1({val(H)},{val(rows)});"]:
  sql(q,role=role,fail='permission denied')
ok('anon/authenticated table and RPC deny matrix')
assert sql("SELECT count(*) FROM pg_class WHERE oid IN ('pokemon_rip_benchmark_publications_v1'::regclass,'pokemon_rip_benchmark_rows_v1'::regclass) AND relrowsecurity;")=='2'; ok('both tables RLS enabled')
# Every failed publication must roll back both the new header and supersession of old data.
cases=[]
r=copy.deepcopy(rows); r[0]['benchmark_score']=0; cases.append(('neutral anchor exact 5',r,'check constraint'))
r=copy.deepcopy(rows); r[0]['benchmark_score']=11; cases.append(('score upper bound',r,'check constraint'))
r=copy.deepcopy(rows); r[0]['raw_model_value']='NaN'; cases.append(('NaN rejected',r,'check constraint'))
r=copy.deepcopy(rows); r[0]['raw_model_value']='Infinity'; cases.append(('infinity rejected',r,'check constraint'))
r=copy.deepcopy(rows); r[0]['raw_model_value']=60;r[0]['benchmark_score']=4;cases.append(('direction preserved',r,'check constraint'))
r=copy.deepcopy(rows); r[0]['model_status']='unavailable';r[0]['raw_model_value']=0;cases.append(('missing model not zero',r,'check constraint'))
r=copy.deepcopy(rows); r[0]['rank']=4;cases.append(('rank bounded by cohort',r,'check constraint'))
r=copy.deepcopy(rows); r[0]['source_model_version']='wrong';cases.append(('source model mismatch',r,'source model mismatch'))
r=copy.deepcopy(rows); r[0]['source_market_date']='2026-09-24';cases.append(('stale source not re-dated',r,'source date mismatch'))
r=copy.deepcopy(rows); r[0]['cost_per_pack']=None;cases.append(('financial evidence requires cost',r,'check constraint'))
r=copy.deepcopy(rows); r[0]['financial_evidence_market_date']=None;cases.append(('financial evidence requires date',r,'check constraint'))
r=copy.deepcopy(rows); r[0]['financial_evidence_status']='unavailable';r[0]['financial_evidence_reason']='missing';cases.append(('unavailable financial evidence null-only',r,'must remain null'))
r=copy.deepcopy(rows); r[9]['model_status']='available';r[9]['source_entity_type']='sealed_product';r[9]['source_entity_id']=PRODUCT;cases.append(('no fabricated product chase',r,'check constraint'))
r=copy.deepcopy(rows); r[0]['secret_extra']='x';cases.append(('unknown row keys rejected',r,'unknown or server-owned'))
r=copy.deepcopy(rows); r[0]['market_date']='2026-09-24';cases.append(('row date is server-owned',r,'unknown or server-owned'))
r=copy.deepcopy(rows);r[0].update(p25_value_per_pack=None,p10_value_per_pack=3);cases.append(('sparse quantile monotonicity',r,'nonmonotone'))
r=copy.deepcopy(rows);r[2]['collector_run_id']=uid();cases.append(('Collector run lineage',r,'Collector run mismatch'))
r=copy.deepcopy(rows);r[8]['source_result_id']=None;cases.append(('product result lineage',r,'exact run/result'))
cases.append(('partial cohort rejected',rows[:-1],'incomplete publication'))
cases.append(('duplicate metric rejected',rows[:-1]+[rows[0]],'duplicate key'))
for name,r,error in cases:
 h=copy.deepcopy(H);h['id']=uid();publish(h,r,H['id'],fail=error)
 assert sql(f"SELECT count(*) FROM pokemon_rip_benchmark_publications_v1 WHERE id='{h['id']}';")=='0'
 ok(name+'; atomic rollback')
# Independent availability: keep canonical model/rank when calibration is missing.
h=copy.deepcopy(H);h['id']=uid();h['calibration_version']='no-calibration'
r=copy.deepcopy(rows)
r[0].update(benchmark_status='unavailable',benchmark_reason='calibration_missing',benchmark_score=None)
publish(h,r);ok('canonical raw model and rank survive missing benchmark')
# Explicit unavailable score rows may still have proven per-pack evidence.
h=copy.deepcopy(H);h['id']=uid();h['calibration_version']='missing-model'
r=copy.deepcopy(rows);r[0].update(model_status='unavailable',model_reason='model_missing',raw_model_value=None,rank=None,cohort_size=None,benchmark_status='unavailable',benchmark_reason='model_missing',benchmark_score=None)
publish(h,r);ok('financial evidence survives missing model without score fabrication')
r[0]['model_reason']=None;h['id']=uid();publish(h,r,prior=None,fail='revision conflict')
h['calibration_version']='missing-reason';publish(h,r,fail='check constraint');ok('unavailable requires explicit reason')
h=copy.deepcopy(H);h['id']=uid();h['active_overall_publication_id']=uid();publish(h,rows,H['id'],fail='authority changed');ok('active source pointer CAS')
h=copy.deepcopy(H);h['id']=uid();h['opening_economics_snapshot_id']=None;publish(h,rows,H['id'],fail='compatible V3');ok('no unproven set/era pre-V3 evidence')
h=copy.deepcopy(H);h['id']=uid();publish(h,rows,fail='revision conflict');ok('daily benchmark replacement CAS')
# Pagination and query binding.
page=history(limit=5); assert len(page['rows'])==5 and page['has_more']; cursor=page['next_cursor']; acc=page['rows']
while page['has_more']:
 page=history(limit=5,after=page['next_cursor']);acc+=page['rows']
assert len(acc)==12 and len({(r['entity_type'],r['entity_id'],r['metric_key']) for r in acc})==12;ok('keyset pages no gaps or duplicates')
for ents,lim,start,end,error in [([],1,'2026-09-25','2026-09-25','1..10'),(ENT*4,1,'2026-09-25','2026-09-25','1..10'),(ENT[:1]*2,1,'2026-09-25','2026-09-25','duplicate'),(ENT,1001,'2026-09-25','2026-09-25','bounds'),(ENT,1,'2025-01-01','2026-09-25','366')]:
 sql(f"SELECT get_pokemon_rip_benchmark_history_v1({val(ents)},'{start}','{end}','test-cohort','test-calibration-1',{lim});",role='service_role',fail=error)
ok('read entity, row, duplicate and date bounds')
sql(f"SELECT get_pokemon_rip_benchmark_history_v1({val(ENT[:1])},'2026-09-25','2026-09-25','test-cohort','test-calibration-1',5,{val(cursor)});",role='service_role',fail='another query');ok('cursor is bound to filter')
replacement=copy.deepcopy(H);replacement['id']=uid();publish(replacement,rows,H['id']);ok('atomic benchmark-only supersession')
sql(f"SELECT get_pokemon_rip_benchmark_history_v1({val(ENT)},'2026-09-25','2026-09-25','test-cohort','test-calibration-1',5,{val(cursor)});",role='service_role',fail='publications changed');ok('pagination refuses mixed publication revisions')
sql(f"INSERT INTO pokemon_rip_benchmark_rows_v1 SELECT * FROM pokemon_rip_benchmark_rows_v1 WHERE publication_id='{H['id']}' LIMIT 1;",fail='generated column')
sql(f"UPDATE pokemon_rip_benchmark_rows_v1 SET benchmark_score=6 WHERE publication_id='{H['id']}';",fail='append-only');ok('published rows immutable')
sql(f"UPDATE pokemon_rip_benchmark_publications_v1 SET source_fingerprint='{'b'*64}' WHERE id='{H['id']}';",role='service_role',fail='immutable');ok('published lineage immutable')
assert before==sql("SELECT md5((SELECT jsonb_agg(to_jsonb(x))::text FROM pokemon_overall_rip_current_publication x)||(SELECT jsonb_agg(to_jsonb(x))::text FROM pokemon_collector_appeal_current x));");ok('source Overall/Rankings/Collector pointers unchanged')
# Scalability fixture: 162 entities/day = live 22 sets + 2 eras + 138 products, 4 metric rows, 366 days.
# Seed in disposable database only; no test data is sent to production.
print('Seeding isolated 366-day scale fixture',flush=True)
# Disable only our fixture triggers in the isolated database for fast scale seeding; contract validation above uses all triggers.
sql('ALTER TABLE pokemon_rip_benchmark_publications_v1 DISABLE TRIGGER USER; ALTER TABLE pokemon_rip_benchmark_rows_v1 DISABLE TRIGGER USER;')
cols=json.loads(sql("SELECT json_agg(attname ORDER BY attnum) FROM pg_attribute WHERE attrelid='pokemon_rip_benchmark_publications_v1'::regclass AND attnum>0 AND NOT attisdropped;"))
expr={c:'h.'+c for c in cols};expr.update(id="md5('scale-'||d)::uuid",market_date="date '2025-09-26'+d",benchmark_key="'scale-cohort'",calibration_version="'scale-calibration-1'",publication_status="'published'",expected_entity_count='162',expected_row_count='648',published_at='now()',superseded_at='NULL',previous_publication_id='NULL')
sql('INSERT INTO pokemon_rip_benchmark_publications_v1('+','.join(cols)+') SELECT '+','.join(expr[c] for c in cols)+f" FROM pokemon_rip_benchmark_publications_v1 h CROSS JOIN generate_series(0,365) d WHERE h.id='{replacement['id']}';")
cols=json.loads(sql("SELECT json_agg(attname ORDER BY attnum) FROM pg_attribute WHERE attrelid='pokemon_rip_benchmark_rows_v1'::regclass AND attnum>0 AND NOT attisdropped AND attgenerated='';"))
expr={c:'r.'+c for c in cols};expr.update(publication_id='h.id',market_date='h.market_date',entity_type="CASE WHEN e<=22 THEN 'set' WHEN e<=24 THEN 'era' ELSE 'sealed_product' END",entity_id="md5('scale-entity-'||e)::uuid",metric_key='m.metric',parent_set_id="CASE WHEN e>24 THEN md5('scale-parent')::uuid ELSE NULL END",model_status="'unavailable'",model_reason="'synthetic scale fixture'",benchmark_status="'unavailable'",benchmark_reason="'synthetic scale fixture'",raw_model_value='NULL',benchmark_score='NULL',rank='NULL',cohort_size='NULL',financial_evidence_status="CASE WHEN m.metric='financial' THEN 'available' ELSE 'not_applicable' END",financial_evidence_market_date='h.market_date',source_market_date='h.market_date')
# Keep missing evidence NULL on other metrics; the source is a synthetic financial row.
for c in cols:
 if c in ('cost_per_pack','expected_value_per_pack','chance_to_recover_cost','modeled_return_on_spend','mean_outcome_retention','top_1pct_ev_share','financial_evidence_market_date') or c.endswith('_per_pack') or c.startswith('normalized_p'):
  expr[c]="CASE WHEN m.metric='financial' THEN "+expr[c]+" ELSE NULL END"
expr['calculation_run_id']="CASE WHEN m.metric='financial' THEN md5('scale-run-'||e)::uuid ELSE NULL END"
expr['source_result_id']="CASE WHEN m.metric='financial' THEN md5('scale-result-'||e||'-'||h.market_date)::uuid ELSE NULL END"

sql('INSERT INTO pokemon_rip_benchmark_rows_v1('+','.join(cols)+') SELECT '+','.join(expr[c] for c in cols)+f" FROM pokemon_rip_benchmark_publications_v1 h CROSS JOIN generate_series(1,162) e CROSS JOIN (VALUES('financial'),('chase'),('collector'),('overall')) m(metric) CROSS JOIN (SELECT * FROM pokemon_rip_benchmark_rows_v1 WHERE publication_id='{replacement['id']}' AND entity_type='set' AND metric_key='financial') r WHERE h.benchmark_key='scale-cohort';")
sql('ALTER TABLE pokemon_rip_benchmark_publications_v1 ENABLE TRIGGER USER; ALTER TABLE pokemon_rip_benchmark_rows_v1 ENABLE TRIGGER USER; ANALYZE pokemon_rip_benchmark_publications_v1; ANALYZE pokemon_rip_benchmark_rows_v1;')
assert sql("SELECT count(*) FROM pokemon_rip_benchmark_rows_v1 r JOIN pokemon_rip_benchmark_publications_v1 p ON p.id=r.publication_id WHERE p.benchmark_key='scale-cohort';")=='237168'
plans={}; ids=[hashlib.md5(f'scale-entity-{n}'.encode()).hexdigest() for n in (1,2,3,4,5,23,24,25,26,27)]
entities=[dict(entity_type=('set' if n<=22 else 'era' if n<=24 else 'sealed_product'),entity_id=str(uuid.UUID(x))) for n,x in zip((1,2,3,4,5,23,24,25,26,27),ids)]
for days in (1,7,30,366):
 end=dt.date(2026,9,26); start=end-dt.timedelta(days=days-1)
 q=f"SELECT r.publication_id,r.market_date,r.entity_type,r.entity_id,r.metric_key,r.benchmark_score FROM jsonb_to_recordset({val(entities)}) e(entity_type text,entity_id uuid) CROSS JOIN LATERAL (SELECT r.* FROM pokemon_rip_benchmark_rows_v1 r JOIN pokemon_rip_benchmark_publications_v1 p ON p.id=r.publication_id WHERE r.entity_type=e.entity_type AND r.entity_id=e.entity_id AND r.market_date BETWEEN '{start}' AND '{end}' AND p.benchmark_key='scale-cohort' AND p.calibration_version='scale-calibration-1' AND p.publication_status='published' ORDER BY r.market_date,r.entity_type,r.entity_id,r.metric_key LIMIT 1001) r ORDER BY r.market_date,r.entity_type,r.entity_id,r.metric_key LIMIT 1001"
 plan=json.loads(sql('EXPLAIN (ANALYZE,BUFFERS,FORMAT JSON) '+q));plans[str(days)+'D']=plan
 text=json.dumps(plan)
 assert 'rip_benchmark_row_history_v1' in text or 'pokemon_rip_benchmark_rows_v1_pkey' in text, text
 rpc=json.loads(sql(f"EXPLAIN (ANALYZE,BUFFERS,FORMAT JSON) SELECT get_pokemon_rip_benchmark_history_v1({val(entities)},'{start}','{end}','scale-cohort','scale-calibration-1',1000);",role='service_role'))
 plans[str(days)+'D_rpc']=rpc
 ok(f'{days}D indexed bounded history on 237168 rows')
plans['current_header']=json.loads(sql("EXPLAIN (ANALYZE,BUFFERS,FORMAT JSON) SELECT id FROM pokemon_rip_benchmark_publications_v1 WHERE benchmark_key='scale-cohort' AND calibration_version='scale-calibration-1' AND publication_status='published' ORDER BY market_date DESC LIMIT 1;"))
assert 'rip_benchmark_pub_daily_v1' in json.dumps(plans['current_header'])
plans['current_rpc']=json.loads(sql(f"EXPLAIN (ANALYZE,BUFFERS,FORMAT JSON) SELECT get_pokemon_rip_benchmark_current_v1({val(entities)},'scale-cohort','scale-calibration-1');",role='service_role'));ok('current publication index and bounded RPC')
(OUT/'plans.json').write_text(json.dumps(plans,indent=2))
(OUT/'results.json').write_text(json.dumps({'checks':checks,'passed':len(checks),'synthetic_rows':237168,'entities_per_day':162,'days':366,'source_pointer_fingerprint':before,'postgres_version':sql('SHOW server_version;')},indent=2))
print('RESULT',json.dumps({'passed':len(checks),'synthetic_rows':237168}),flush=True)
