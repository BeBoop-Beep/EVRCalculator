"""Execute the exact restored Price Storage V2 source contracts on PostgreSQL 17.6.

Unlike test_price_storage_v2_postgres.py, this suite does not replace the pricing
preview with a test stub. It loads the exact restored raw as-of resolver, V2
as-of resolver, canonical root-universe function and scope-staging migrations
from the repository, then applies the review-only separated writer proposal.

The database is synthetic and disposable, but the SQL under test is the exact
production migration source. No network DSN or Supabase credential is accepted.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[2]
DB = "price_storage_v2_real_source_ci"
DAY = "2026-09-06"
NM = "4f8d1181-670e-4aea-937c-4d98d2e531a6"

SETS = {
    "Evolving Skies": "10000000-0000-4000-8000-000000000001",
    "Crown Zenith": "10000000-0000-4000-8000-000000000002",
    "Galarian Gallery": "10000000-0000-4000-8000-000000000003",
    "Celebrations": "10000000-0000-4000-8000-000000000004",
    "Classic Collection": "10000000-0000-4000-8000-000000000005",
}
ROOTS = (SETS["Evolving Skies"], SETS["Crown Zenith"], SETS["Celebrations"])

# parent set, card suffix, price
CARDS = (
    (SETS["Evolving Skies"], 1, 10), (SETS["Evolving Skies"], 2, 20),
    (SETS["Crown Zenith"], 3, 1), (SETS["Crown Zenith"], 4, 2),
    (SETS["Galarian Gallery"], 5, 30), (SETS["Galarian Gallery"], 6, 40),
    (SETS["Celebrations"], 7, 3), (SETS["Celebrations"], 8, 4),
    (SETS["Classic Collection"], 9, 50), (SETS["Classic Collection"], 10, 60),
)

BASE_SCHEMA = r"""
DO $$ BEGIN CREATE ROLE anon NOLOGIN; EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE ROLE authenticated NOLOGIN; EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE ROLE service_role NOLOGIN BYPASSRLS; EXCEPTION WHEN duplicate_object THEN NULL; END $$;
GRANT USAGE ON SCHEMA public TO service_role,anon,authenticated;

CREATE TABLE public.conditions(id uuid PRIMARY KEY,name text,abbreviation text);
CREATE TABLE public.sets(
 id uuid PRIMARY KEY,name text NOT NULL,canonical_key text,era_id uuid,release_date date,
 logo_image_url text,symbol_image_url text,parent_opening_set_id uuid,
 catalog_only boolean NOT NULL DEFAULT false,ready_for_daily_scrape boolean NOT NULL DEFAULT true,
 counts_toward_parent_set_value boolean NOT NULL DEFAULT false,subset_type text
);
CREATE TABLE public.cards(
 id uuid PRIMARY KEY,set_id uuid NOT NULL,pokemon_tcg_api_id text,name text,card_number text,rarity text
);
CREATE TABLE public.card_variants(
 id uuid PRIMARY KEY,card_id uuid NOT NULL,pokemon_tcg_api_id text,
 printing_type text,special_type text,edition text
);
CREATE TABLE public.pokemon_canonical_cards(
 id uuid PRIMARY KEY,set_id uuid NOT NULL,pokemon_tcg_api_card_id text,name text,
 number text,printed_number text,rarity text,set_value_eligible boolean NOT NULL DEFAULT true,
 canonical_review_status text NOT NULL DEFAULT 'approved',image_small_url text,image_large_url text
);
CREATE TABLE public.pokemon_canonical_card_legacy_identity_links(
 canonical_card_id uuid NOT NULL,legacy_card_id uuid NOT NULL
);
CREATE TABLE public.card_variant_price_observations(
 id uuid PRIMARY KEY,card_variant_id uuid NOT NULL,condition_id uuid NOT NULL,
 source text,currency text,captured_at date,market_price numeric,high_price numeric,low_price numeric,
 created_at timestamptz NOT NULL
);
CREATE TABLE public.card_variant_price_events_v2(
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,card_variant_id uuid NOT NULL,condition_id uuid NOT NULL,
 source text NOT NULL,currency text NOT NULL,effective_date date NOT NULL,event_type text NOT NULL,
 market_price numeric,high_price numeric,low_price numeric,source_observation_id uuid,source_created_at timestamptz,
 UNIQUE(card_variant_id,condition_id,source,currency,effective_date)
);
CREATE TABLE public.card_variant_price_observation_ranges_v2(
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,card_variant_id uuid NOT NULL,condition_id uuid NOT NULL,
 source text NOT NULL,currency text NOT NULL,observed_from date NOT NULL,observed_through date NOT NULL,
 observed_day_count integer NOT NULL DEFAULT 1
);
CREATE TABLE public.card_variant_price_current_v2(
 card_variant_id uuid NOT NULL,condition_id uuid NOT NULL,source text NOT NULL,currency text NOT NULL,
 event_id bigint NOT NULL,effective_date date NOT NULL,state text NOT NULL,market_price numeric,
 high_price numeric,low_price numeric,source_observation_id uuid,last_observed_date date,
 last_observation_id uuid,last_observation_created_at timestamptz,updated_at timestamptz DEFAULT now(),
 PRIMARY KEY(card_variant_id,condition_id,source,currency)
);
CREATE TABLE public.pokemon_canonical_card_market_prices_latest(
 canonical_card_id uuid NOT NULL,set_id uuid NOT NULL,pokemon_tcg_api_card_id text,legacy_card_id uuid,
 card_variant_id uuid,condition_id uuid,printing_type text,market_price numeric,captured_at date,
 source text,price_selection_reason text
);
CREATE TABLE public.pokemon_market_explorer_card_current_metadata(
 card_variant_id uuid PRIMARY KEY,canonical_card_id uuid NOT NULL,legacy_card_id uuid,set_id uuid NOT NULL,
 card_name text,card_number text,rarity text,edition text,printing_type text,special_type text,
 image_url text,identity_basis text
);
CREATE TABLE public.pokemon_market_date_quality(market_date date,tcg text,status text);
CREATE TABLE public.scrape_jobs(
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,set_id uuid,market_date date,status text,
 completed_at timestamptz,created_at timestamptz DEFAULT now()
);
CREATE TABLE public.price_storage_v2_shadow_queue(
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,set_id uuid,market_date date,status text,
 source_completed_at timestamptz,completed_at timestamptz
);
CREATE TABLE public.pokemon_edition_split_root_sets_v2(set_id uuid PRIMARY KEY);
CREATE TABLE public.pokemon_card_desirability_links(
 pokemon_canonical_card_id uuid NOT NULL,pokemon_reference_id bigint,is_hit_eligible boolean NOT NULL DEFAULT false
);
CREATE TABLE public.pokemon_set_value_daily_history(
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,set_id uuid,snapshot_date date,value_scope text,
 set_value numeric,priced_card_count integer,total_card_count integer,canonical_card_count integer,
 linked_card_count integer,included_card_count integer,coverage_pct numeric,source text,
 created_at timestamptz DEFAULT now(),updated_at timestamptz DEFAULT now(),
 UNIQUE(set_id,snapshot_date,value_scope)
);
CREATE TABLE public.price_storage_v2_migration_audit(
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,phase text NOT NULL,captured_at timestamptz DEFAULT now(),
 details jsonb NOT NULL DEFAULT '{}'::jsonb
);
CREATE TABLE public.simulation_input_cards(
 id uuid PRIMARY KEY,calculation_run_id uuid,card_id uuid,card_variant_id uuid,condition_id uuid,
 card_name text,rarity_bucket text,price_source text,price_used numeric,captured_at date,
 effective_pull_rate numeric,ev_contribution numeric,created_at timestamptz DEFAULT now()
);
"""


def uuid_for(prefix: int, suffix: int) -> str:
    return f"{prefix:08x}-0000-4000-8000-{suffix:012x}"


@unittest.skipUnless(os.environ.get("PRICE_STORAGE_V2_TEST_CONTAINER"), "requires disposable PostgreSQL CI service")
class RealSourceContractTests(unittest.TestCase):
    @classmethod
    def run(cls, sql: str, *, db: str = DB, check: bool = True):
        container = os.environ["PRICE_STORAGE_V2_TEST_CONTAINER"]
        if not re.fullmatch(r"[a-f0-9]{12,64}", container):
            raise RuntimeError("isolated Docker container id required")
        proc = subprocess.run(
            ["docker","exec","-i",container,"psql","-X","-qAt","-v","ON_ERROR_STOP=1",
             "-U","postgres","-d",db], input=sql,text=True,capture_output=True,timeout=45
        )
        if check and proc.returncode:
            raise AssertionError(proc.stderr)
        return proc

    @classmethod
    def value(cls, sql: str):
        text = cls.run(sql).stdout.strip()
        return json.loads(text)

    @classmethod
    def migration(cls, version: str, name: str):
        path = ROOT / "docs/price_storage_v2/applied_migrations" / f"{version}_{name}.sql"
        if not path.exists():
            raise AssertionError(f"missing exact restored migration {path.name}")
        cls.run(path.read_text(encoding="utf-8"))

    @classmethod
    def seed(cls):
        q = [f"INSERT INTO public.conditions VALUES('{NM}','Near Mint','NM');"]
        q += [
            f"INSERT INTO public.sets(id,name,canonical_key,parent_opening_set_id,catalog_only,ready_for_daily_scrape,counts_toward_parent_set_value,subset_type) VALUES('{SETS['Evolving Skies']}','Evolving Skies','evolvingSkies',NULL,false,true,false,NULL);",
            f"INSERT INTO public.sets(id,name,canonical_key,parent_opening_set_id,catalog_only,ready_for_daily_scrape,counts_toward_parent_set_value,subset_type) VALUES('{SETS['Crown Zenith']}','Crown Zenith','crownZenith',NULL,false,true,false,NULL);",
            f"INSERT INTO public.sets(id,name,canonical_key,parent_opening_set_id,catalog_only,ready_for_daily_scrape,counts_toward_parent_set_value,subset_type) VALUES('{SETS['Galarian Gallery']}','Crown Zenith Galarian Gallery','crownZenithGallery','{SETS['Crown Zenith']}',false,false,true,'subset');",
            f"INSERT INTO public.sets(id,name,canonical_key,parent_opening_set_id,catalog_only,ready_for_daily_scrape,counts_toward_parent_set_value,subset_type) VALUES('{SETS['Celebrations']}','Celebrations','celebrations',NULL,false,true,false,NULL);",
            f"INSERT INTO public.sets(id,name,canonical_key,parent_opening_set_id,catalog_only,ready_for_daily_scrape,counts_toward_parent_set_value,subset_type) VALUES('{SETS['Classic Collection']}','Celebrations Classic Collection','celebrationsClassic','{SETS['Celebrations']}',false,false,true,'subset');",
            f"INSERT INTO public.pokemon_market_date_quality VALUES('{DAY}','pokemon','READY');",
        ]
        for set_id, suffix, price in CARDS:
            card_id = uuid_for(0x20000000, suffix)
            canonical_id = uuid_for(0x30000000, suffix)
            variant_id = uuid_for(0x40000000, suffix)
            obs_id = uuid_for(0x50000000, suffix)
            api_id = f"fixture-{suffix}"
            q += [
                f"INSERT INTO public.cards VALUES('{card_id}','{set_id}','{api_id}','Card {suffix}','{suffix}', 'Rare');",
                f"INSERT INTO public.card_variants VALUES('{variant_id}','{card_id}','{api_id}','holo',NULL,NULL);",
                f"INSERT INTO public.pokemon_canonical_cards(id,set_id,pokemon_tcg_api_card_id,name,number,printed_number,rarity,set_value_eligible,canonical_review_status) VALUES('{canonical_id}','{set_id}','{api_id}','Card {suffix}','{suffix}','{suffix}','Rare',true,'approved');",
                f"INSERT INTO public.pokemon_market_explorer_card_current_metadata(card_variant_id,canonical_card_id,legacy_card_id,set_id,card_name,card_number,rarity,edition,printing_type,special_type,image_url,identity_basis) VALUES('{variant_id}','{canonical_id}','{card_id}','{set_id}','Card {suffix}','{suffix}','Rare',NULL,'holo',NULL,NULL,'parent_pokemon_tcg_api_id');",
                f"INSERT INTO public.card_variant_price_observations VALUES('{obs_id}','{variant_id}','{NM}','TCGPlayer','USD','{DAY}',{price},{price+1},{max(price-1,0)},'{DAY} 12:00:00+00');",
                f"INSERT INTO public.card_variant_price_events_v2(card_variant_id,condition_id,source,currency,effective_date,event_type,market_price,high_price,low_price,source_observation_id,source_created_at) VALUES('{variant_id}','{NM}','TCGPlayer','USD','{DAY}','PRICE',{price},{price+1},{max(price-1,0)},'{obs_id}','{DAY} 12:00:00+00');",
                f"INSERT INTO public.card_variant_price_observation_ranges_v2(card_variant_id,condition_id,source,currency,observed_from,observed_through,observed_day_count) VALUES('{variant_id}','{NM}','TCGPlayer','USD','{DAY}','{DAY}',1);",
                f"INSERT INTO public.pokemon_card_desirability_links VALUES('{canonical_id}',{suffix},true);",
            ]
        q.append("""
INSERT INTO public.card_variant_price_current_v2(
 card_variant_id,condition_id,source,currency,event_id,effective_date,state,market_price,high_price,low_price,
 source_observation_id,last_observed_date,last_observation_id,last_observation_created_at)
SELECT e.card_variant_id,e.condition_id,e.source,e.currency,e.id,e.effective_date,e.event_type,e.market_price,e.high_price,e.low_price,
       e.source_observation_id,e.effective_date,e.source_observation_id,e.source_created_at
FROM public.card_variant_price_events_v2 e;

INSERT INTO public.pokemon_canonical_card_market_prices_latest(
 canonical_card_id,set_id,pokemon_tcg_api_card_id,legacy_card_id,card_variant_id,condition_id,printing_type,
 market_price,captured_at,source,price_selection_reason)
SELECT p.id,p.set_id,p.pokemon_tcg_api_card_id,c.id,v.id,'""" + NM + r"""','holo',
       cur.market_price,cur.last_observed_date,cur.source,'fixture_current_v2'
FROM public.pokemon_canonical_cards p
JOIN public.cards c ON c.set_id=p.set_id AND c.pokemon_tcg_api_id=p.pokemon_tcg_api_card_id
JOIN public.card_variants v ON v.card_id=c.id
JOIN public.card_variant_price_current_v2 cur ON cur.card_variant_id=v.id AND cur.condition_id='""" + NM + r"""';
""")
        # Completion receipts are deliberately exact for main sets and subsets.
        for idx, set_id in enumerate(SETS.values(), 1):
            ts = f"2026-09-06 18:{idx:02d}:00+00"
            q += [
                f"INSERT INTO public.scrape_jobs(set_id,market_date,status,completed_at,created_at) VALUES('{set_id}','{DAY}','completed','{ts}','{ts}');",
                f"INSERT INTO public.price_storage_v2_shadow_queue(set_id,market_date,status,source_completed_at,completed_at) VALUES('{set_id}','{DAY}','complete','{ts}','{ts}'::timestamptz + interval '1 minute');",
            ]
        # One frozen simulation row gives the exact cutover view something to compare.
        first_set, suffix, _ = CARDS[2]
        q.append(
            f"INSERT INTO public.simulation_input_cards(id,calculation_run_id,card_id,card_variant_id,condition_id,card_name,rarity_bucket,price_source,price_used,captured_at,effective_pull_rate,ev_contribution) VALUES('{uuid_for(0x60000000,1)}','{uuid_for(0x61000000,1)}','{uuid_for(0x20000000,suffix)}','{uuid_for(0x40000000,suffix)}','{NM}','Card {suffix}','rare','TCGPlayer',1,'{DAY}',0.01,0.01);"
        )
        cls.run("\n".join(q))

    @classmethod
    def setUpClass(cls):
        # Separate database prevents the synthetic writer-contract suite from contaminating this one.
        cls.run(f"DROP DATABASE IF EXISTS {DB} WITH (FORCE); CREATE DATABASE {DB};", db="postgres")
        cls.run(BASE_SCHEMA)
        cls.seed()

        # Load exact production migration sources, not copied function bodies.
        cls.migration("20260906061919", "add_set_value_canonical_prices_as_of_v2_shadow")
        cls.migration("20260906062417", "add_set_value_raw_as_of_validation_oracle")
        cls.migration("20260906180118", "add_stable_canonical_variant_preferences_v2")

        # Load the exact pre-V2 root contract from main, then the exact V2 promotion pair.
        root_sql = ROOT / "supabase/migrations/20260904173530_canonical_market_root_set_universe_v1.sql"
        if not root_sql.exists():
            raise AssertionError("canonical root-universe migration missing from repository")
        cls.run(root_sql.read_text(encoding="utf-8"))
        cls.migration("20260906033445", "add_market_root_latest_price_v2_shadow_fixed")
        cls.migration("20260906033554", "promote_market_root_latest_price_to_v2")

        # Exact scope-stage migration must accept the exact function-definition hashes above.
        cls.migration("20260906233426", "add_isolated_member_root_price_scope_staging")
        cls.migration("20260906233651", "restrict_scope_stage_to_append_only_backend_access")

        # Exact simulator cutover source is also executable against this fixture.
        cls.migration("20260906022241", "cutover_simulation_current_nm_view_to_price_storage_v2")

        # Finally install the review-only separated writer proposal; release remains disabled.
        cls.run((ROOT / "backend/db/proposals/price_storage_v2_scoped_publication.sql").read_text(encoding="utf-8"))

    def test_01_exact_function_hashes_match_scope_gate(self):
        got = self.value("""
SELECT jsonb_build_object(
 'raw',md5(pg_get_functiondef('public.get_pokemon_set_value_canonical_prices_as_of_raw_oracle(uuid,date)'::regprocedure)),
 'v2',md5(pg_get_functiondef('public.get_pokemon_set_value_canonical_prices_as_of_v2_shadow(uuid,date)'::regprocedure)));
""")
        self.assertEqual(got, {"raw":"f7b3b05bb7c492dddc4a26abd5cb4fb7","v2":"93d1ad2c21373db0662ad984ecdfee98"})

    def test_02_raw_and_v2_asof_resolvers_match_every_member(self):
        got = self.value("""
WITH members AS (SELECT id FROM public.sets),
raw_rows AS (SELECT m.id set_id,r.* FROM members m CROSS JOIN LATERAL public.get_pokemon_set_value_canonical_prices_as_of_raw_oracle(m.id,'2026-09-06') r),
v2_rows AS (SELECT m.id set_id,r.* FROM members m CROSS JOIN LATERAL public.get_pokemon_set_value_canonical_prices_as_of_v2_shadow(m.id,'2026-09-06') r),
ro AS (SELECT * FROM raw_rows EXCEPT ALL SELECT * FROM v2_rows),
vo AS (SELECT * FROM v2_rows EXCEPT ALL SELECT * FROM raw_rows)
SELECT jsonb_build_object('raw_rows',(SELECT count(*) FROM raw_rows),'v2_rows',(SELECT count(*) FROM v2_rows),'raw_only',(SELECT count(*) FROM ro),'v2_only',(SELECT count(*) FROM vo));
""")
        self.assertEqual(got,{"raw_rows":10,"v2_rows":10,"raw_only":0,"v2_only":0})

    def test_03_exact_root_contract_combines_subsets(self):
        got = self.value(f"""
SELECT jsonb_object_agg(root_set_name,jsonb_build_object('cards',n,'value',value))
FROM (
 SELECT root_set_name,count(*) n,sum(market_price) value
 FROM public.get_pokemon_market_root_set_card_prices_latest_v1(NULL)
 WHERE market_scope='standard' GROUP BY root_set_name
) x;
""")
        self.assertEqual(got["Evolving Skies"],{"cards":2,"value":30})
        self.assertEqual(got["Crown Zenith"],{"cards":4,"value":73})
        self.assertEqual(got["Celebrations"],{"cards":4,"value":117})

    def test_04_exact_preview_passes_three_roots_and_separates_member_root(self):
        rows = self.value("SELECT jsonb_agg(public.preview_price_storage_v2_scoped_values(x,'2026-09-06') ORDER BY x) FROM unnest(ARRAY['%s','%s','%s']::uuid[]) x;" % ROOTS)
        self.assertEqual([r["status"] for r in rows],["parity_passed"]*3)
        crown = next(r for r in rows if r["context"]["root_name"]=="Crown Zenith")
        values = crown["candidate_values"]
        root_standard = next(v for v in values if v["universe_scope"]=="root" and v["value_scope"]=="standard")
        parent_standard = next(v for v in values if v["universe_scope"]=="member" and v["set_id"]==SETS["Crown Zenith"] and v["value_scope"]=="standard")
        subset_standard = next(v for v in values if v["universe_scope"]=="member" and v["set_id"]==SETS["Galarian Gallery"] and v["value_scope"]=="standard")
        self.assertEqual((root_standard["priced_card_count"],root_standard["set_value"]),(4,73))
        self.assertEqual((parent_standard["priced_card_count"],parent_standard["set_value"]),(2,3))
        self.assertEqual((subset_standard["priced_card_count"],subset_standard["set_value"]),(2,70))

    def test_05_stage_and_separated_writers_use_real_preview(self):
        staged = self.value("SELECT public.stage_price_storage_v2_scoped_values(ARRAY['%s','%s','%s']::uuid[],'2026-09-06');" % ROOTS)
        self.assertTrue(all(r["status"]=="parity_passed" for r in staged["results"]))
        self.run("UPDATE public.price_storage_v2_scoped_release_gate SET enabled=true;")
        for item in staged["results"]:
            self.run(f"SELECT public.publish_price_storage_v2_member_run({item['run_id']},'{item['root_set_id']}','{DAY}');")
            self.run(f"SELECT public.publish_price_storage_v2_root_run({item['run_id']},'{item['root_set_id']}','{DAY}');")
        got = self.value(f"""
SELECT jsonb_build_object(
 'member_rows',(SELECT count(*) FROM public.pokemon_member_set_value_daily_history_v2),
 'root_rows',(SELECT count(*) FROM public.pokemon_root_set_value_daily_history_v2),
 'crown_member',(SELECT set_value FROM public.pokemon_member_set_value_daily_history_v2 WHERE set_id='{SETS['Crown Zenith']}' AND value_scope='standard'),
 'crown_root',(SELECT set_value FROM public.pokemon_root_set_value_daily_history_v2 WHERE set_id='{SETS['Crown Zenith']}' AND value_scope='standard'),
 'gallery_member',(SELECT set_value FROM public.pokemon_member_set_value_daily_history_v2 WHERE set_id='{SETS['Galarian Gallery']}' AND value_scope='standard'));
""")
        self.assertEqual(got,{"member_rows":15,"root_rows":9,"crown_member":3,"crown_root":73,"gallery_member":70})

    def test_06_exact_simulator_cutover_view_matches_legacy_raw_shadow(self):
        got = self.value("""
WITH legacy AS (
 SELECT id,current_near_mint_price,current_near_mint_price_captured_at,current_near_mint_price_source
 FROM public.simulation_input_cards_with_near_mint_price_legacy_shadow
), v2 AS (
 SELECT id,current_near_mint_price,current_near_mint_price_captured_at,current_near_mint_price_source
 FROM public.simulation_input_cards_with_near_mint_price
), lo AS (SELECT * FROM legacy EXCEPT ALL SELECT * FROM v2),
vo AS (SELECT * FROM v2 EXCEPT ALL SELECT * FROM legacy)
SELECT jsonb_build_object('legacy',(SELECT count(*) FROM legacy),'v2',(SELECT count(*) FROM v2),'legacy_only',(SELECT count(*) FROM lo),'v2_only',(SELECT count(*) FROM vo));
""")
        self.assertEqual(got,{"legacy":1,"v2":1,"legacy_only":0,"v2_only":0})

    def test_07_release_gate_default_was_fail_closed_before_test_enable(self):
        # Test 05 explicitly enabled it. The DDL itself is guarded by source inspection below.
        sql=(ROOT/"backend/db/proposals/price_storage_v2_scoped_publication.sql").read_text(encoding="utf-8")
        self.assertIn("VALUES(true,false)",sql)
        self.assertNotIn("CREATE OR REPLACE FUNCTION public.refresh_pokemon_market_public_rollout_daily_snapshots_v1",sql)
        self.assertNotIn("pokemon_set_value_daily_history(",sql)


if __name__ == "__main__":
    if not os.environ.get("PRICE_STORAGE_V2_TEST_CONTAINER"):
        raise SystemExit("isolated Docker PostgreSQL service required")
    unittest.main(verbosity=2)
