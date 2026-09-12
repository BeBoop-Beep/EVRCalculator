"""Execute the SQL proposal on an ephemeral PostgreSQL 17 service.

Requires a Docker service container id and the deliberately named test database.
No DSN, Supabase credential, external database, or production connection accepted.
The pricing preview is a synthetic controlled fixture, NOT a restored live dataset.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor
import unittest

REPO = Path(__file__).resolve().parents[2]
ROOT_ID = "11111111-1111-4111-8111-111111111111"
SUBSET_ID = "22222222-2222-4222-8222-222222222222"
DAY = "2026-09-06"

FIXTURE_SQL = """
CREATE ROLE anon NOLOGIN;
CREATE ROLE authenticated NOLOGIN;
CREATE ROLE service_role NOLOGIN BYPASSRLS;
GRANT USAGE ON SCHEMA public TO service_role,anon,authenticated;
CREATE SCHEMA test_support;
GRANT USAGE ON SCHEMA test_support TO service_role;
CREATE TABLE test_support.previews(root_id uuid PRIMARY KEY, payload jsonb NOT NULL);
GRANT SELECT ON test_support.previews TO service_role;
CREATE TABLE public.price_storage_v2_scope_stage_runs (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, root_set_id uuid NOT NULL,
 market_date date NOT NULL, definition_version text NOT NULL,
 status text NOT NULL CHECK(status IN ('parity_passed','blocked')), reason text NOT NULL,
 evidence_signature text NOT NULL, evidence jsonb NOT NULL,
 publication_authorized boolean NOT NULL DEFAULT false CHECK(publication_authorized=false),
 created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(root_set_id,market_date,evidence_signature)
);
CREATE TABLE public.price_storage_v2_scoped_value_candidates (
 run_id bigint NOT NULL REFERENCES public.price_storage_v2_scope_stage_runs(id),
 universe_scope text NOT NULL CHECK(universe_scope IN ('member','root')),
 set_id uuid NOT NULL, market_scope text NOT NULL CHECK(market_scope='standard'),
 value_scope text NOT NULL CHECK(value_scope IN ('standard','hits','top10')),
 set_value numeric, expected_card_count integer NOT NULL, priced_card_count integer NOT NULL,
 subset_priced_card_count integer NOT NULL, fresh_card_count integer NOT NULL,
 coverage_pct numeric, oldest_observed_date date, newest_observed_date date,
 basket_fingerprint text NOT NULL,
 PRIMARY KEY(run_id,universe_scope,set_id,market_scope,value_scope)
);
ALTER TABLE public.price_storage_v2_scope_stage_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.price_storage_v2_scoped_value_candidates ENABLE ROW LEVEL SECURITY;
GRANT SELECT,INSERT ON public.price_storage_v2_scope_stage_runs,
 public.price_storage_v2_scoped_value_candidates TO service_role;
GRANT USAGE,SELECT ON SEQUENCE public.price_storage_v2_scope_stage_runs_id_seq TO service_role;
CREATE FUNCTION public.preview_price_storage_v2_scoped_values(p_root_set_id uuid,p_market_date date)
RETURNS jsonb LANGUAGE sql STABLE SECURITY INVOKER SET search_path='' AS $$
 SELECT payload FROM test_support.previews
 WHERE root_id=p_root_set_id AND payload#>>'{context,market_date}'=p_market_date::text;
$$;
CREATE FUNCTION public.preview_price_storage_v2_scoped_values_v2(p_root_set_id uuid,p_market_date date)
RETURNS jsonb LANGUAGE sql STABLE SECURITY INVOKER SET search_path='' AS $$
 SELECT payload FROM test_support.previews
 WHERE root_id=p_root_set_id AND payload#>>'{context,market_date}'=p_market_date::text;
$$;
REVOKE ALL ON FUNCTION public.preview_price_storage_v2_scoped_values(uuid,date),
 public.preview_price_storage_v2_scoped_values_v2(uuid,date) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.preview_price_storage_v2_scoped_values(uuid,date),
 public.preview_price_storage_v2_scoped_values_v2(uuid,date) TO service_role;
-- Sentinels model protected data. The proposal must not reference or modify them.
CREATE TABLE public.pokemon_set_value_daily_history(id integer PRIMARY KEY, payload jsonb);
CREATE TABLE public.pokemon_set_page_snapshot_latest(id integer PRIMARY KEY, payload jsonb);
CREATE TABLE public.simulation_input_cards(id integer PRIMARY KEY, payload jsonb);
INSERT INTO public.pokemon_set_value_daily_history VALUES(1,'{"frozen":"published-history"}');
INSERT INTO public.pokemon_set_page_snapshot_latest VALUES(1,'{"frozen":"snapshot"}');
INSERT INTO public.simulation_input_cards VALUES(1,'{"frozen":"simulation"}');
"""


def candidates():
    out = []
    for universe, set_id, total, value, subset in (
        ("member", ROOT_ID, 160, 254.87, 0),
        ("member", SUBSET_ID, 70, 2379.60, 70),
        ("root", ROOT_ID, 230, 2634.47, 70),
    ):
        for scope in ("standard", "hits", "top10"):
            count = min(10, total) if scope == "top10" else total
            out.append(dict(universe_scope=universe,set_id=set_id,market_scope="standard",
                value_scope=scope,set_value=value,expected_card_count=count,priced_card_count=count,
                subset_priced_card_count=min(count,subset),fresh_card_count=count,coverage_pct=100,
                oldest_observed_date=DAY,newest_observed_date=DAY,basket_fingerprint=f"{universe}-{set_id}-{scope}"))
    return sorted(out,key=lambda r:(r['universe_scope'],r['set_id'],r['value_scope']))


def sql_literal(value):
    return "'" + value.replace("'", "''") + "'"


@unittest.skipUnless(os.environ.get("PRICE_STORAGE_V2_TEST_CONTAINER"), "requires the isolated PostgreSQL CI service")
class PostgresScopeTests(unittest.TestCase):
    @classmethod
    def raw(cls, sql, role=None, check=True):
        container = os.environ["PRICE_STORAGE_V2_TEST_CONTAINER"]
        if not re.fullmatch(r"[a-f0-9]{12,64}",container):
            raise RuntimeError("Only an explicit local Docker container id is accepted")
        if role not in (None,"service_role","anon","authenticated"):
            raise ValueError("unexpected role")
        prefix = (f"SET ROLE {role};\n" if role else "")
        proc = subprocess.run(["docker","exec","-i",container,"psql","-X","-qAt",
            "-v","ON_ERROR_STOP=1","-v","VERBOSITY=verbose","-U","postgres","-d","price_storage_v2_ci"],
            input=prefix+sql,text=True,capture_output=True,timeout=30)
        if check and proc.returncode:
            raise AssertionError(proc.stderr)
        return proc

    @classmethod
    def value(cls,sql,role=None):
        text=cls.raw(sql,role).stdout.strip()
        return json.loads(text)

    @classmethod
    def setUpClass(cls):
        identity=cls.value("SELECT jsonb_build_object('db',current_database(),'version',current_setting('server_version_num'));")
        if identity['db']!='price_storage_v2_ci' or int(identity['version'])//10000 != 17:
            raise RuntimeError("Tests require the designated disposable PostgreSQL 17 database")
        cls.raw(FIXTURE_SQL)
        cls.raw((REPO/'backend/db/proposals/price_storage_v2_scoped_publication.sql').read_text())
        print("ISOLATED_POSTGRES_IDENTITY="+json.dumps(identity),flush=True)

    def setUp(self):
        self.raw("""TRUNCATE public.pokemon_member_set_value_daily_history_v2,
 public.pokemon_root_set_value_daily_history_v2,public.price_storage_v2_scoped_value_candidates,
 public.price_storage_v2_scope_stage_runs,test_support.previews;
 UPDATE public.price_storage_v2_scoped_release_gate SET enabled=false;""")
        preview=dict(status="parity_passed",reason="exact_source_gated_scope_parity_v2",publication_authorized=False,
            context=dict(root_set_id=ROOT_ID,market_date=DAY,definition_version="canonical_asof_scope_split_v2",source_generation="fixture-generation-1"),
            candidate_values=candidates())
        encoded=sql_literal(json.dumps(preview))
        self.raw(f"""INSERT INTO test_support.previews VALUES('{ROOT_ID}',{encoded}::jsonb);
 INSERT INTO public.price_storage_v2_scope_stage_runs(id,root_set_id,market_date,definition_version,
 status,reason,evidence_signature,evidence) OVERRIDING SYSTEM VALUE
 SELECT 1001,'{ROOT_ID}','{DAY}','canonical_asof_scope_split_v2','parity_passed','accepted',md5(payload::text),payload-'candidate_values'
 FROM test_support.previews;
 INSERT INTO public.price_storage_v2_scoped_value_candidates
 SELECT 1001,r.* FROM test_support.previews p CROSS JOIN LATERAL jsonb_to_recordset(p.payload->'candidate_values') AS r(
 universe_scope text,set_id uuid,market_scope text,value_scope text,set_value numeric,
 expected_card_count integer,priced_card_count integer,subset_priced_card_count integer,
 fresh_card_count integer,coverage_pct numeric,oldest_observed_date date,newest_observed_date date,basket_fingerprint text);""")

    def tearDown(self):
        for table, frozen in (("pokemon_set_value_daily_history","published-history"),
                              ("pokemon_set_page_snapshot_latest","snapshot"),("simulation_input_cards","simulation")):
            self.assertEqual(self.value(f"SELECT jsonb_agg(payload) FROM public.{table};"),[{"frozen":frozen}])

    def enable(self):
        self.raw("UPDATE public.price_storage_v2_scoped_release_gate SET enabled=true;")

    def call_sql(self,scope="root",run=1001,root=ROOT_ID,day=DAY):
        return f"SELECT public.publish_price_storage_v2_{scope}_run({run},'{root}','{day}');"

    def call(self,scope="root",**kw):
        return self.value(self.call_sql(scope,**kw),"service_role")

    def counts(self):
        return self.value("SELECT jsonb_build_array((SELECT count(*) FROM public.pokemon_member_set_value_daily_history_v2),(SELECT count(*) FROM public.pokemon_root_set_value_daily_history_v2));")

    def assert_sql_error(self,sql,code="55000",role="service_role"):
        result=self.raw(sql,role,check=False)
        self.assertNotEqual(result.returncode,0)
        self.assertIn(code,result.stderr)

    def fingerprint(self,exclude_timestamps=False):
        minus="-'created_at'-'updated_at'" if exclude_timestamps else ""
        return self.value(f"SELECT jsonb_build_array((SELECT jsonb_agg(to_jsonb(t){minus} ORDER BY set_id,value_scope) FROM public.pokemon_member_set_value_daily_history_v2 t),(SELECT jsonb_agg(to_jsonb(t){minus} ORDER BY set_id,value_scope) FROM public.pokemon_root_set_value_daily_history_v2 t));")

    def test_01_disabled_gate_rejects_before_writes(self):
        self.assert_sql_error(self.call_sql()); self.assertEqual(self.counts(),[0,0])

    def test_02_member_destination_never_writes_root(self):
        self.enable(); self.assertEqual(self.call('member')['rows_inserted'],6); self.assertEqual(self.counts(),[6,0])

    def test_03_root_destination_never_writes_member(self):
        self.enable(); self.assertEqual(self.call()['rows_inserted'],3); self.assertEqual(self.counts(),[0,3])
        self.assertEqual(self.value("SELECT priced_card_count FROM public.pokemon_root_set_value_daily_history_v2 WHERE value_scope='standard';"),230)

    def test_04_both_writer_orders_identical(self):
        self.enable(); self.call('member'); self.call('root'); expected=self.fingerprint(True)
        self.raw("TRUNCATE public.pokemon_member_set_value_daily_history_v2,public.pokemon_root_set_value_daily_history_v2;")
        self.call('root'); self.call('member'); self.assertEqual(self.fingerprint(True),expected)

    def test_05_repeat_is_noop_including_timestamps(self):
        self.enable(); self.call('root'); self.call('member'); expected=self.fingerprint()
        self.assertEqual(self.call('root')['status'],'noop'); self.assertEqual(self.call('member')['status'],'noop')
        self.assertEqual(self.fingerprint(),expected)

    def test_06_stale_source_generation_rejected(self):
        self.enable(); self.raw("UPDATE test_support.previews SET payload=jsonb_set(payload,'{context,source_generation}','\"generation-2\"');")
        self.assert_sql_error(self.call_sql()); self.assertEqual(self.counts(),[0,0])

    def test_07_tampered_candidate_rejected(self):
        self.enable(); self.raw("UPDATE public.price_storage_v2_scoped_value_candidates SET set_value=set_value+1 WHERE universe_scope='root';")
        self.assert_sql_error(self.call_sql()); self.assertEqual(self.counts(),[0,0])

    def test_08_missing_scope_rejected(self):
        self.enable(); self.raw("DELETE FROM public.price_storage_v2_scoped_value_candidates WHERE universe_scope='root' AND value_scope='hits';")
        self.assert_sql_error(self.call_sql()); self.assertEqual(self.counts(),[0,0])

    def test_09_wrong_root_date_and_run_rejected(self):
        self.enable()
        for kwargs in ({'root':SUBSET_ID},{'day':'2026-09-05'},{'run':999}):
            self.assert_sql_error(self.call_sql(**kwargs))
        self.assertEqual(self.counts(),[0,0])

    def test_10_service_role_cannot_enable_or_rewrite(self):
        self.assert_sql_error("UPDATE public.price_storage_v2_scoped_release_gate SET enabled=true;","42501")
        self.enable(); self.call()
        for sql in ("UPDATE public.pokemon_root_set_value_daily_history_v2 SET set_value=0;",
                    "DELETE FROM public.pokemon_root_set_value_daily_history_v2;",
                    "TRUNCATE public.pokemon_root_set_value_daily_history_v2;"):
            self.assert_sql_error(sql,"42501")

    def test_11_public_roles_cannot_read_or_publish(self):
        self.enable()
        for role in ('anon','authenticated'):
            self.assert_sql_error(self.call_sql(),'42501',role)
            self.assert_sql_error('SELECT * FROM public.pokemon_root_set_value_daily_history_v2;','42501',role)

    def test_12_conflicting_existing_rows_rollback_partial_insert(self):
        self.enable(); self.call()
        self.raw("DELETE FROM public.pokemon_root_set_value_daily_history_v2 WHERE value_scope<>'standard'; UPDATE public.pokemon_root_set_value_daily_history_v2 SET set_value=999;")
        before=self.fingerprint(); self.assert_sql_error(self.call_sql()); self.assertEqual(self.fingerprint(),before)
        self.assertEqual(self.counts(),[0,1])

    def test_13_outer_transaction_can_rollback_both_writers(self):
        self.enable(); self.assert_sql_error('BEGIN;'+self.call_sql('member')+self.call_sql(run=999)+'COMMIT;')
        self.assertEqual(self.counts(),[0,0])

    def test_14_concurrent_same_run_is_complete_plus_noop(self):
        self.enable()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda _:self.call(),range(2)))
        self.assertEqual(sorted(r['status'] for r in results),['complete','noop'])
        self.assertEqual(self.counts(),[0,3])

    def test_15_concurrent_member_root_do_not_cross(self):
        self.enable()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(self.call,('member','root')))
        self.assertEqual([r['status'] for r in results],['complete','complete'])
        self.assertEqual(self.counts(),[6,3])

    def test_16_blocked_preview_rejected(self):
        self.enable(); self.raw("UPDATE test_support.previews SET payload=jsonb_set(payload,'{status}','\"blocked\"');")
        self.assert_sql_error(self.call_sql()); self.assertEqual(self.counts(),[0,0])

    def test_17_null_inputs_rejected(self):
        self.enable()
        self.assert_sql_error(f"SELECT public.publish_price_storage_v2_root_run(NULL,'{ROOT_ID}','{DAY}');",'22023')

    def test_18_noop_still_requires_enabled_gate(self):
        self.enable(); self.call(); before=self.fingerprint()
        self.raw('UPDATE public.price_storage_v2_scoped_release_gate SET enabled=false;')
        self.assert_sql_error(self.call_sql()); self.assertEqual(self.fingerprint(),before)

    def test_19_individual_rpc_failure_keeps_other_committed_scope(self):
        self.enable(); self.call('member'); self.assert_sql_error(self.call_sql(run=999))
        self.assertEqual(self.counts(),[6,0]); self.call('root'); self.assertEqual(self.counts(),[6,3])

    def test_20_missing_preview_rejected(self):
        self.enable(); self.raw('DELETE FROM test_support.previews;')
        self.assert_sql_error(self.call_sql()); self.assertEqual(self.counts(),[0,0])


if __name__=='__main__':
    if not os.environ.get('PRICE_STORAGE_V2_TEST_CONTAINER'):
        raise SystemExit('An isolated Docker PostgreSQL service is required; no production DSN accepted')
    unittest.main(verbosity=2)
