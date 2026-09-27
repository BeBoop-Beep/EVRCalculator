"""Backend-generated payloads against the exact PR388 SQL; disposable PG only."""
from __future__ import annotations
import json
import os
from pathlib import Path
import subprocess
from decimal import Decimal

from backend.domain.pokemon.rip_benchmark_v1 import wire
from backend.db.services.rip_benchmark_preview_v1 import candidate_request
from backend.db.services.rip_benchmark_evidence_v1 import attach_evidence, evidence_from_scope
from backend.tests.benchmark_v1.test_core import DAY, CAL, header, ref, row, scope, source, uid

if os.environ.get('PGHOST') not in ('127.0.0.1','localhost') or os.environ.get('PGDATABASE') != 'benchmark_backend_test':
    raise SystemExit('Refusing non-isolated PostgreSQL target')


def sql(text,fail=False):
    process=subprocess.run(['psql','-X','-A','-t','-v','ON_ERROR_STOP=1'],input=text,
                           text=True,capture_output=True,timeout=30)
    if fail:
        assert process.returncode != 0, 'invalid payload unexpectedly succeeded'
        return process.stderr
    if process.returncode:raise AssertionError(process.stderr)
    return '\n'.join(line for line in process.stdout.splitlines() if line not in ('SET','BEGIN','COMMIT','ROLLBACK'))


def lit(value):return "'"+json.dumps(wire(value),separators=(',',':')).replace("'","''")+"'::jsonb"


def publish(request,fail=False):
    args=request['arguments']
    return sql('SET ROLE service_role; SELECT public.publish_pokemon_rip_benchmark_v1('
               +lit(args['p_header'])+','+lit(args['p_rows'])+',NULL);',fail=fail)


sql('''CREATE ROLE anon; CREATE ROLE authenticated; CREATE ROLE service_role BYPASSRLS;
GRANT USAGE ON SCHEMA public TO anon,authenticated,service_role;
CREATE TABLE public.pokemon_overall_rip_publication_runs(id uuid primary key,market_date date,status text,model_version text);
CREATE TABLE public.pokemon_overall_rip_current_publication(scope text primary key,publication_run_id uuid,rankings_generation_id uuid,set_page_generation_id uuid);
CREATE TABLE public.pokemon_rip_stats_snapshots(id uuid primary key,market_date date,publication_status text,contract_version text,methodology_version text,weighting_version text);
GRANT SELECT ON public.pokemon_overall_rip_publication_runs,public.pokemon_overall_rip_current_publication,public.pokemon_rip_stats_snapshots TO service_role;''')
sql(f"INSERT INTO public.pokemon_overall_rip_publication_runs VALUES('{uid(900)}','2026-09-10','published','overall-fixture'); INSERT INTO public.pokemon_overall_rip_current_publication VALUES('pokemon','{uid(900)}','{uid(901)}','{uid(902)}'); INSERT INTO public.pokemon_rip_stats_snapshots VALUES('{uid(80)}','{DAY}','published','pokemon-rip-stats-v3','hierarchical_product_per_pack_empirical_v1','equal-set_equal-family_equal-sku-v1');")
root=Path(__file__).resolve().parents[2]
# parents[2] is backend; mirror path is deliberately explicit and checked below.
migration=root/'db/migrations/20260926233908_rip_benchmark_foundation_v1.sql'
sql('BEGIN;\n'+migration.read_text(encoding='utf-8')+'\nCOMMIT;')
protected=sql('SELECT row_to_json(p) FROM pokemon_overall_rip_current_publication p;')
rows=[row(m) for m in ['financial','chase','collector','overall']]
rows[0]=row(src=source(raw='50.001'),reference=ref(),calibration=CAL)
rows[0]=attach_evidence(rows[0],evidence_from_scope(scope()),market_date=DAY,source_snapshot_id=uid(80))
h=header();h['calibration_version']=CAL.version;h.update(opening_economics_snapshot_id=uid(80),opening_economics_contract_version='pokemon-rip-stats-v3',opening_economics_basis='all_modeled_products_per_pack_equivalent')
request=candidate_request(h,rows)
assert publish(request)==uid(999)
print('PASS backend-generated four-metric payload accepted')
assert publish(request)==uid(999)
print('PASS exact idempotent retry')
entities=[{'entity_type':'set','entity_id':uid(1)}]
current=json.loads(sql('SET ROLE service_role; SELECT get_pokemon_rip_benchmark_current_v1('+lit(entities)+",'fixture','shadow-fixture');"),parse_float=Decimal)
financial=next(r for r in current['rows'] if r['metric_key']=='financial')
assert financial['benchmark_score']==Decimal('5.0001') and financial['raw_delta']==Decimal('.001')
assert financial['rank']==2 and financial['expected_value_per_pack']==4
print('PASS unrounded benchmark direction, canonical rank and per-pack evidence')
assert current['active_overall_market_date']=='2026-09-10' and current['market_date']==DAY
print('PASS release selection date distinct from score/evidence date')
assert all('source_lineage' not in r for r in current['rows'])
assert next(r for r in current['rows'] if r['metric_key']=='collector')['benchmark_score'] is None
print('PASS compact read omits private lineage; missing calibration preserves raw model')
h['id']=uid(998);h['benchmark_key']='bad-date'
bad=candidate_request(h,rows);bad['arguments']['p_rows'][0]['source_market_date']='2026-09-24'
assert 'source date mismatch' in publish(bad,fail=True)
print('PASS database rejects unproven stale source after backend construction')
assert protected==sql('SELECT row_to_json(p) FROM pokemon_overall_rip_current_publication p;')
print('PASS existing source pointer untouched')
print('Backend/PostgreSQL smoke: 7 checks passed; isolated synthetic database only')
