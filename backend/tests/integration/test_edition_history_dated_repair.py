"""Runs only against the dedicated localhost edition_test database, never production."""
import os
from pathlib import Path
from datetime import date,timedelta
from uuid import uuid4
import pytest
import psycopg
from psycopg.conninfo import conninfo_to_dict

MIGRATION=Path(__file__).resolve().parents[3]/'supabase/migrations/20260927014000_add_dated_edition_history_refresh.sql'
SCHEMA='''
DROP SCHEMA public CASCADE; CREATE SCHEMA public;
DO $$ BEGIN IF NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='service_role') THEN CREATE ROLE service_role; END IF;
IF NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='anon') THEN CREATE ROLE anon; END IF;
IF NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN CREATE ROLE authenticated; END IF; END $$;
CREATE TABLE sets(id uuid PRIMARY KEY,parent_opening_set_id uuid,catalog_only boolean DEFAULT false,counts_toward_parent_set_value boolean DEFAULT false);
CREATE TABLE pokemon_edition_split_root_sets_v2(set_id uuid PRIMARY KEY,profile text);
CREATE TABLE pokemon_canonical_cards(id uuid PRIMARY KEY,set_id uuid,rarity text,canonical_review_status text,set_value_eligible boolean DEFAULT true);
CREATE TABLE pokemon_market_explorer_card_current_metadata(card_variant_id uuid PRIMARY KEY,canonical_card_id uuid,set_id uuid,edition text,printing_type text,special_type text,identity_basis text);
CREATE TABLE conditions(id uuid PRIMARY KEY,name text);
CREATE TABLE card_variant_price_events_v2(id bigserial PRIMARY KEY,card_variant_id uuid,condition_id uuid,source text,currency text,effective_date date,market_price numeric);
CREATE TABLE card_variant_price_observation_ranges_v2(card_variant_id uuid,condition_id uuid,source text,currency text,observed_from date,observed_through date);
CREATE TABLE card_variant_price_observations(id uuid PRIMARY KEY,card_variant_id uuid,condition_id uuid,source text,currency text,captured_at date,created_at timestamptz DEFAULT now(),market_price numeric);
CREATE TABLE pokemon_market_root_set_value_daily_history_v2_shadow(set_id uuid,market_scope text,market_date date,set_value numeric,expected_card_count integer,priced_card_count integer,coverage_pct numeric,certified_on_date boolean,source text,updated_at timestamptz,PRIMARY KEY(set_id,market_scope,market_date));
CREATE TABLE pokemon_market_date_quality(tcg text,market_date date,status text);
CREATE TABLE pokemon_scrape_batches(market_date date,status text,promoted_at timestamptz,expected_set_count integer,succeeded_set_count integer,failed_set_count integer,missing_set_count integer);
CREATE TABLE scrape_jobs(id bigserial PRIMARY KEY,set_id uuid,market_date date,status text,completed_at timestamptz,created_at timestamptz DEFAULT now());
CREATE TABLE price_storage_v2_shadow_queue(set_id uuid,market_date date,status text,source_completed_at timestamptz,completed_at timestamptz);
'''

@pytest.fixture
def db():
    dsn=os.environ.get('EDITION_TEST_DATABASE_URL')
    if not dsn:pytest.skip('disposable Postgres not configured')
    conf=conninfo_to_dict(dsn)
    assert conf.get('host') in ('127.0.0.1','localhost') and conf.get('dbname')=='edition_test'
    with psycopg.connect(dsn,autocommit=True) as c:
        c.execute(SCHEMA);c.execute(MIGRATION.read_text())
        yield c

def seed(c,profile='edition_split'):
    root,card,nm,first,unlimited=[uuid4() for _ in range(5)]
    day=date.today()-timedelta(days=2)
    c.execute('INSERT INTO sets(id) VALUES (%s)',(root,))
    c.execute('INSERT INTO pokemon_edition_split_root_sets_v2 VALUES(%s,%s)',(root,profile))
    c.execute("INSERT INTO pokemon_canonical_cards VALUES(%s,%s,'Common','verified',true)",(card,root))
    c.execute("INSERT INTO conditions VALUES(%s,'Near Mint')",(nm,))
    for variant,edition,price in [(first,'1st-edition',10),(unlimited,'unlimited',2)]:
        c.execute("INSERT INTO pokemon_market_explorer_card_current_metadata VALUES(%s,%s,%s,%s,'non-holo',NULL,'explicit_legacy_identity_link')",(variant,card,root,edition))
        for d,p in [(day-timedelta(days=1),price),(day+timedelta(days=1),price*100)]:
            c.execute("INSERT INTO card_variant_price_events_v2(card_variant_id,condition_id,source,currency,effective_date,market_price) VALUES(%s,%s,'TCGPlayer','USD',%s,%s)",(variant,nm,d,p))
            c.execute("INSERT INTO card_variant_price_observations(id,card_variant_id,condition_id,source,currency,captured_at,market_price) VALUES(%s,%s,%s,'TCGPlayer','USD',%s,%s)",(uuid4(),variant,nm,d,p))
        c.execute("INSERT INTO card_variant_price_observation_ranges_v2 VALUES(%s,%s,'TCGPlayer','USD',%s,%s)",(variant,nm,day-timedelta(days=1),day-timedelta(days=1)))
        c.execute("INSERT INTO card_variant_price_observation_ranges_v2 VALUES(%s,%s,'TCGPlayer','USD',%s,%s)",(variant,nm,day+timedelta(days=1),day+timedelta(days=1)))
    c.execute("INSERT INTO pokemon_market_date_quality VALUES('pokemon',%s,'READY')",(day,))
    c.execute("INSERT INTO pokemon_scrape_batches VALUES(%s,'complete',now(),1,1,0,0)",(day,))
    c.execute("INSERT INTO scrape_jobs(set_id,market_date,status,completed_at) VALUES(%s,%s,'completed',now()-interval '5 minutes')",(root,day))
    c.execute("INSERT INTO price_storage_v2_shadow_queue SELECT set_id,market_date,'complete',completed_at,now() FROM scrape_jobs")
    return root,day,first,unlimited

def refresh(c,r,d,force=False):
    return c.execute('SELECT refresh_pokemon_edition_history_day_v1(%s,%s,%s)',(r,d,force)).fetchone()[0]

def test_asof_excludes_future_prices_and_never_blends_editions(db):
    r,d,_,_=seed(db)
    result=refresh(db,r,d)
    assert result['raw_v2_equal'] and result['certified_scope_count']==2
    assert {x['market_scope']:x['set_value'] for x in result['scopes']}=={'first_edition':10,'unlimited':2}
    assert result['market_date']==d.isoformat()

def test_shadowless_without_variant_remains_uncertified(db):
    r,d,_,_=seed(db,'base_three_printings');result=refresh(db,r,d)
    s=next(x for x in result['scopes'] if x['market_scope']=='shadowless')
    assert s['priced_card_count']==0 and s['coverage_pct']==0 and not s['certified_on_date']
    assert result['scope_count']==3 and result['certified_scope_count']==2

def test_parity_mismatch_writes_nothing(db):
    r,d,f,_=seed(db)
    db.execute('UPDATE card_variant_price_events_v2 SET market_price=999 WHERE card_variant_id=%s AND effective_date<=%s',(f,d))
    with pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState,match='mismatch'):refresh(db,r,d)
    assert db.execute('SELECT count(*) FROM pokemon_market_root_set_value_daily_history_v2_shadow').fetchone()[0]==0
    assert db.execute('SELECT count(*) FROM pokemon_edition_history_refresh_state_v1').fetchone()[0]==0

def test_stale_projection_provenance_refuses(db):
    r,d,_,_=seed(db)
    db.execute("UPDATE price_storage_v2_shadow_queue SET source_completed_at=source_completed_at-interval '1 day'")
    with pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState,match='projections'):refresh(db,r,d)

def test_unapproved_date_refuses(db):
    r,d,_,_=seed(db);db.execute('DELETE FROM pokemon_market_date_quality')
    with pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState,match='approved'):refresh(db,r,d)

def test_future_date_refuses(db):
    r,d,_,_=seed(db)
    with pytest.raises(psycopg.errors.InvalidParameterValue):refresh(db,r,date.today()+timedelta(days=1))

def test_needs_review_keeps_uncertified(db):
    r,d,_,_=seed(db);db.execute("UPDATE pokemon_canonical_cards SET canonical_review_status='needs_review'")
    result=refresh(db,r,d)
    assert result['certified_scope_count']==0

def test_repeat_noop_and_tampered_history_repaired(db):
    r,d,_,_=seed(db)
    assert refresh(db,r,d)['status']=='complete'
    assert refresh(db,r,d)['status']=='noop'
    db.execute('UPDATE pokemon_market_root_set_value_daily_history_v2_shadow SET set_value=999')
    assert refresh(db,r,d)['status']=='complete'
    assert db.execute("SELECT set_value FROM pokemon_market_root_set_value_daily_history_v2_shadow WHERE market_scope='unlimited'").fetchone()[0]==2

def test_failed_rebuild_preserves_previous_values(db):
    r,d,f,_=seed(db);refresh(db,r,d)
    db.execute('UPDATE card_variant_price_events_v2 SET market_price=999 WHERE card_variant_id=%s AND effective_date<=%s',(f,d))
    with pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState):refresh(db,r,d,True)
    assert db.execute("SELECT set_value FROM pokemon_market_root_set_value_daily_history_v2_shadow WHERE market_scope='first_edition'").fetchone()[0]==10

def test_unknown_root_cannot_create_market(db):
    with pytest.raises(psycopg.errors.InvalidParameterValue):refresh(db,uuid4(),date.today()-timedelta(days=2))

def test_public_roles_cannot_execute_writer(db):
    for role in ('anon','authenticated'):
        assert not db.execute("SELECT has_function_privilege(%s,'public.refresh_pokemon_edition_history_day_v1(uuid,date,boolean)','EXECUTE')",(role,)).fetchone()[0]
    assert db.execute("SELECT has_function_privilege('service_role','public.refresh_pokemon_edition_history_day_v1(uuid,date,boolean)','EXECUTE')").fetchone()[0]
