// Run with Node; PGLITE_PACKAGE points to an external @electric-sql/pglite install.
import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';

const packagePath = process.env.PGLITE_PACKAGE;
if (!packagePath) throw new Error('PGLITE_PACKAGE is required');
const { PGlite } = await import(pathToFileURL(packagePath));
const db = await PGlite.create();
const root = process.cwd();
try {
  const schema=JSON.parse(fs.readFileSync(path.join(root,'backend/tests/integration/p5a_fixture_schema.json'),'utf8'));
  const types={uuid:'uuid',text:'text',date:'date',timestamptz:'timestamptz',numeric:'numeric',bool:'boolean',int2:'smallint',int4:'integer',int8:'bigint',jsonb:'jsonb',_text:'text[]',_int4:'integer[]'};
  await db.exec('CREATE ROLE anon; CREATE ROLE authenticated; CREATE ROLE service_role;');
  for (const [table,columns] of Object.entries(schema.tables)) {
    await db.exec(`CREATE TABLE public.${table} (${columns.map(([name,type])=>`${name} ${types[type]}`).join(',')})`);
  }
  await db.exec(`ALTER TABLE public.card_market_top_hits_by_edition_latest ALTER COLUMN id SET DEFAULT gen_random_uuid();
    ALTER TABLE public.card_variant_market_metrics_latest ALTER COLUMN id SET DEFAULT gen_random_uuid();
    ALTER TABLE public.pokemon_set_value_daily_history ALTER COLUMN id SET DEFAULT gen_random_uuid();
    ALTER TABLE public.pokemon_set_value_daily_history ADD UNIQUE (set_id,snapshot_date,value_scope);`);
  await db.exec(`CREATE VIEW public.sealed_product_market_usd_latest AS
      SELECT NULL::uuid AS sealed_product_id,NULL::timestamptz AS captured_at WHERE false;
    CREATE VIEW public.graded_card_market_latest AS
      SELECT NULL::uuid AS graded_card_variant_id,NULL::timestamptz AS captured_at WHERE false;`);
  await db.exec(`ALTER TABLE public.card_variant_price_current_v2 ADD PRIMARY KEY (card_variant_id,condition_id,source,currency);
    CREATE INDEX p5a_current_lookup ON public.card_variant_price_current_v2 (card_variant_id,condition_id,source,currency,last_observed_date DESC);
    INSERT INTO public.conditions(id,name,abbreviation) VALUES ('4f8d1181-670e-4aea-937c-4d98d2e531a6','Near Mint','NM');
    INSERT INTO public.sets(id,name) VALUES ('00000000-0000-0000-0000-000000000002','Fixture Set');
    INSERT INTO public.cards(id,set_id,name,rarity,card_number,pokemon_tcg_api_id) VALUES
      ('00000000-0000-0000-0000-000000000003','00000000-0000-0000-0000-000000000002','Fixture Card','Rare','1','fixture-1');
    INSERT INTO public.card_variants(id,card_id,printing_type,pokemon_tcg_api_id) VALUES
      ('00000000-0000-0000-0000-000000000004','00000000-0000-0000-0000-000000000003','holo','fixture-1');
    INSERT INTO public.pokemon_canonical_cards(id,set_id,pokemon_tcg_api_card_id,name,rarity,number,printed_number,catalog_role) VALUES
      ('00000000-0000-0000-0000-000000000005','00000000-0000-0000-0000-000000000002','fixture-1','Fixture Card','Rare','1','1','market');
    INSERT INTO public.card_variant_price_current_v2(card_variant_id,condition_id,source,currency,market_price,high_price,low_price,last_observed_date,last_observation_created_at,last_observation_id) VALUES
      ('00000000-0000-0000-0000-000000000004','4f8d1181-670e-4aea-937c-4d98d2e531a6','TCGPlayer','USD',100,110,90,'2026-09-18','2026-09-18T12:00:00Z','00000000-0000-0000-0000-000000000006');`);
  await db.exec(`
    UPDATE public.sets SET name='Base',catalog_only=false WHERE id='00000000-0000-0000-0000-000000000002';
    UPDATE public.pokemon_canonical_cards SET set_value_eligible=true WHERE id='00000000-0000-0000-0000-000000000005';
    INSERT INTO public.pokemon_market_explorer_card_current_metadata(card_variant_id,canonical_card_id,set_id,edition,printing_type,identity_basis)
      VALUES ('00000000-0000-0000-0000-000000000004','00000000-0000-0000-0000-000000000005','00000000-0000-0000-0000-000000000002','1st-edition','holo','parent_pokemon_tcg_api_id');
    INSERT INTO public.simulation_input_cards(id,calculation_run_id,card_id,card_variant_id,condition_id,price_used)
      VALUES ('00000000-0000-0000-0000-000000000008','00000000-0000-0000-0000-000000000009','00000000-0000-0000-0000-000000000003','00000000-0000-0000-0000-000000000004','4f8d1181-670e-4aea-937c-4d98d2e531a6',100);
    INSERT INTO public.card_variant_price_events_v2(id,card_variant_id,condition_id,source,currency,effective_date,event_type,market_price)
      VALUES (1,'00000000-0000-0000-0000-000000000004','4f8d1181-670e-4aea-937c-4d98d2e531a6','TCGPlayer','USD','2026-09-18','SET',100);
    INSERT INTO public.card_variant_price_observation_ranges_v2(id,card_variant_id,condition_id,source,currency,observed_from,observed_through)
      VALUES (1,'00000000-0000-0000-0000-000000000004','4f8d1181-670e-4aea-937c-4d98d2e531a6','TCGPlayer','USD','2026-09-18','2026-09-19');
    INSERT INTO public.card_variant_price_observations(id,card_variant_id,condition_id,source,currency,market_price,captured_at)
      VALUES ('00000000-0000-0000-0000-000000000010','00000000-0000-0000-0000-000000000004','4f8d1181-670e-4aea-937c-4d98d2e531a6','TCGPlayer','USD',100,'2026-09-18');
    INSERT INTO public.user_card_holdings(id,card_variant_id,condition_id,quantity)
      VALUES ('00000000-0000-0000-0000-000000000012','00000000-0000-0000-0000-000000000004','4f8d1181-670e-4aea-937c-4d98d2e531a6',1);
  `);
  const productionBaseline=JSON.parse(fs.readFileSync(path.join(root,'backend/artifacts/pricing/p5a_pre_migration_canonical_baseline.json'),'utf8')).rows;
  const extraSets=new Set();
  for (const row of productionBaseline) {
    if (!extraSets.has(row.set_id)) {
      extraSets.add(row.set_id);
      await db.query(`INSERT INTO public.sets(id,name) VALUES ($1,'Captured cohort set')`,[row.set_id]);
    }
    const apiId=`p5a-${row.canonical_card_id}`;
    await db.query(`INSERT INTO public.pokemon_canonical_cards(id,set_id,pokemon_tcg_api_card_id,name,rarity,number,printed_number,catalog_role)
      VALUES ($1,$2,$3,'Captured cohort card','Rare','1','1','market')`,[row.canonical_card_id,row.set_id,apiId]);
    if (row.card_variant_id && row.market_price) {
      await db.query(`INSERT INTO public.cards(id,set_id,name,rarity,card_number,pokemon_tcg_api_id)
        VALUES ($1,$2,'Captured cohort card','Rare','1',$3)`,[row.canonical_card_id,row.set_id,apiId]);
      await db.query(`INSERT INTO public.card_variants(id,card_id,printing_type,pokemon_tcg_api_id)
        VALUES ($1,$2,'holo',$3)`,[row.card_variant_id,row.canonical_card_id,apiId]);
      await db.query(`INSERT INTO public.card_variant_price_current_v2(card_variant_id,condition_id,source,currency,market_price,last_observed_date,last_observation_created_at,last_observation_id)
        VALUES ($1,$2,'TCGPlayer','USD',$3,$4,'2026-09-19T12:00:00Z',$5)`,
        [row.card_variant_id,row.condition_id,row.market_price,row.captured_at,row.canonical_card_id]);
    }
  }
  await db.exec(`CREATE FUNCTION public.get_pokemon_cards_daily_constituents_v2_hybrid_shadow(uuid[],date,date,uuid[])
    RETURNS TABLE(canonical_card_id uuid,set_id uuid,market_date date,market_price numeric,card_variant_id uuid,source text,captured_at date)
    LANGUAGE sql STABLE AS $$ SELECT NULL::uuid,NULL::uuid,NULL::date,NULL::numeric,NULL::uuid,NULL::text,NULL::date WHERE false $$;`);
  await db.exec(fs.readFileSync(path.join(root,'supabase/migrations/20260906041325_add_price_observed_history_v2_rpc.sql'),'utf8'));
  const migration = fs.readdirSync(path.join(root,'supabase/migrations'))
    .filter(name=>/^2026092014000[0-6]_p5a_source_lock_.*\.sql$/.test(name))
    .sort()
    .map(name=>fs.readFileSync(path.join(root,'supabase/migrations',name),'utf8'))
    .join('\n');
  const beforeFix = migration
    .replaceAll(/-- P5A_ZERO_DIFF_START[\s\S]*?-- P5A_ZERO_DIFF_END/g, '')
    .replaceAll(/\s+AND current_row\.source = 'TCGPlayer'(?:::text)?/g, '')
    .replaceAll(/\s+AND o\.source = 'TCGPlayer'/gi, '')
    .replaceAll(/\s+and r\.source='TCGPlayer'/gi, '')
    .replaceAll(/\s+and price\.source='TCGPlayer'/gi, '')
    .replaceAll(/\s+AND e\.source='TCGPlayer'/gi, '')
    .replaceAll(/\s+and h\.source = 'TCGPlayer'/gi, '');
  await db.exec(beforeFix);
  await db.exec(`CREATE FUNCTION public.is_pokemon_market_instrument_catalog_role(text)
    RETURNS boolean LANGUAGE sql IMMUTABLE AS $$ SELECT $1='market' $$;`);
  await db.exec(fs.readFileSync(path.join(root,'supabase/migrations/20260917194000_filter_canonical_price_resolver_market_roles.sql'),'utf8'));
  async function capturedCohort() {
    const rows=[];
    for (const row of productionBaseline) {
      const result=await db.query(`SELECT canonical_card_id,card_variant_id,condition_id,market_price,source,captured_at,price_selection_reason
        FROM public.get_pokemon_canonical_card_market_prices_latest_for_set_v2_shadow($1)
        WHERE canonical_card_id=$2`,[row.set_id,row.canonical_card_id]);
      rows.push({canonical_card_id:row.canonical_card_id,result:result.rows});
    }
    return rows;
  }
  const cohortBefore=await capturedCohort();
  const latestBefore=(await db.query(`SELECT variant_id,condition_id,market_price,source,captured_at
    FROM public.card_market_usd_latest_by_condition ORDER BY variant_id,condition_id`)).rows;
  const preCanonical = (await db.query(`SELECT * FROM public.get_pokemon_canonical_card_market_prices_latest_for_set_v2_shadow('00000000-0000-0000-0000-000000000002')`)).rows;
  const preView = (await db.query(`SELECT * FROM public.card_market_usd_latest_by_condition WHERE variant_id='00000000-0000-0000-0000-000000000004'`)).rows;
  await db.exec(migration);
  const cohortAfter=await capturedCohort();
  const latestAfter=(await db.query(`SELECT variant_id,condition_id,market_price,source,captured_at
    FROM public.card_market_usd_latest_by_condition ORDER BY variant_id,condition_id`)).rows;
  assert.deepEqual(cohortAfter,cohortBefore);
  assert.deepEqual(latestAfter,latestBefore);
  const guardHash=(await db.query(`SELECT md5(pg_get_functiondef('public.get_pokemon_cards_daily_constituents_v2_shadow(uuid[],date,date,uuid[])'::regprocedure)) AS hash`)).rows[0].hash;
  assert.equal(guardHash,'756f4d28ea3710f59bb23f254ecd3580');
  const postCanonical = (await db.query(`SELECT * FROM public.get_pokemon_canonical_card_market_prices_latest_for_set_v2_shadow('00000000-0000-0000-0000-000000000002')`)).rows;
  const postView = (await db.query(`SELECT * FROM public.card_market_usd_latest_by_condition WHERE variant_id='00000000-0000-0000-0000-000000000004'`)).rows;
  assert.deepEqual(postCanonical,preCanonical);
  assert.deepEqual(postView,preView);
  const plan=JSON.stringify((await db.query(`EXPLAIN (FORMAT JSON) SELECT * FROM public.card_market_usd_latest_by_condition WHERE variant_id='00000000-0000-0000-0000-000000000004'`)).rows);
  assert.match(plan,/card_variant_price_current_v2/);
  assert.doesNotMatch(plan,/card_variant_price_observations/);
  async function check(expectedPrice, expectedSource, expectedCount = 1) {
    const canonical = (await db.query(`SELECT market_price,source FROM public.get_pokemon_canonical_card_market_prices_latest_for_set_v2_shadow('00000000-0000-0000-0000-000000000002')`)).rows;
    const latest = (await db.query(`SELECT market_price,source FROM public.card_market_usd_latest_by_condition WHERE variant_id='00000000-0000-0000-0000-000000000004'`)).rows;
    assert.equal(canonical.length, expectedCount);
    assert.equal(latest.length, expectedCount);
    if (expectedCount) {
      assert.equal(Number(canonical[0].market_price), expectedPrice);
      assert.equal(canonical[0].source, expectedSource);
      assert.equal(Number(latest[0].market_price), expectedPrice);
      assert.equal(latest[0].source, expectedSource);
    }
    const legacy = (await db.query(`SELECT market_price,source FROM public.card_market_usd_latest WHERE variant_id='00000000-0000-0000-0000-000000000004'`)).rows;
    const sim = (await db.query(`SELECT current_near_mint_price AS market_price,current_near_mint_price_source AS source FROM public.simulation_input_cards_with_near_mint_price WHERE card_variant_id='00000000-0000-0000-0000-000000000004'`)).rows;
    const rootRows = (await db.query(`SELECT market_price,source FROM public.get_pokemon_market_root_set_card_prices_latest_v1_v2_shadow('00000000-0000-0000-0000-000000000002') WHERE market_scope='first_edition'`)).rows;
    const asOf = (await db.query(`SELECT market_price,source FROM public.get_pokemon_set_value_canonical_prices_as_of_v2_shadow('00000000-0000-0000-0000-000000000002','2026-09-19')`)).rows;
    if (expectedCount) {
      for (const [label,rows] of [['card_market',legacy],['simulation',sim],['root',rootRows],['as_of',asOf]]) {
        assert.equal(rows.length,1,label);
        assert.equal(Number(rows[0].market_price),expectedPrice,label);
        assert.equal(rows[0].source,expectedSource,label);
      }
    } else {
      assert.equal(legacy.length,0);
      assert.equal(sim[0].market_price,null);
      assert.equal(rootRows[0].market_price,null);
      assert.equal(asOf.length,0);
    }
  }
  await check(100,'TCGPlayer');
  const freshnessWithTcg=(await db.query(`SELECT public.get_nightly_snapshot_pricing_freshness('2026-09-19',25) AS result`)).rows[0].result;
  assert.equal(freshnessWithTcg.fresh_asset_counts.cards,1);
  const mutations = [140,20,1000];
  for (const price of mutations) {
    await db.query(`INSERT INTO public.card_variant_price_current_v2(card_variant_id,condition_id,source,currency,market_price,high_price,low_price,last_observed_date,last_observation_created_at,last_observation_id) VALUES
      ('00000000-0000-0000-0000-000000000004','4f8d1181-670e-4aea-937c-4d98d2e531a6','eBayActiveAsk','USD',$1,150,10,'2026-09-19','2026-09-19T12:00:00Z','00000000-0000-0000-0000-000000000007')
      ON CONFLICT (card_variant_id,condition_id,source,currency) DO UPDATE SET market_price=EXCLUDED.market_price`,[price]);
    await check(100,'TCGPlayer');
    const sources=(await db.query(`SELECT source,market_price FROM public.card_variant_price_current_v2 WHERE card_variant_id='00000000-0000-0000-0000-000000000004' ORDER BY source`)).rows;
    assert.equal(sources.length,2);
    assert.equal(Number(sources.find(x=>x.source==='eBayActiveAsk').market_price),price);
  }
  await db.exec(`INSERT INTO public.card_variant_price_events_v2(id,card_variant_id,condition_id,source,currency,effective_date,event_type,market_price)
    VALUES (2,'00000000-0000-0000-0000-000000000004','4f8d1181-670e-4aea-937c-4d98d2e531a6','eBayActiveAsk','USD','2026-09-19','SET',140);
    INSERT INTO public.card_variant_price_observation_ranges_v2(id,card_variant_id,condition_id,source,currency,observed_from,observed_through)
    VALUES (2,'00000000-0000-0000-0000-000000000004','4f8d1181-670e-4aea-937c-4d98d2e531a6','eBayActiveAsk','USD','2026-09-19','2026-09-19');
    INSERT INTO public.card_variant_price_observations(id,card_variant_id,condition_id,source,currency,market_price,captured_at)
    VALUES ('00000000-0000-0000-0000-000000000011','00000000-0000-0000-0000-000000000004','4f8d1181-670e-4aea-937c-4d98d2e531a6','eBayActiveAsk','USD',140,'2026-09-19');`);
  await check(100,'TCGPlayer');
  const historicalQueries=[
    `SELECT market_price,source FROM public.get_pokemon_cards_daily_constituents_v2_shadow(ARRAY['00000000-0000-0000-0000-000000000002'::uuid],'2026-09-19','2026-09-19',NULL::uuid[])`,
    `SELECT market_price,source FROM public.get_pokemon_cards_daily_constituents_resolved_universe(ARRAY['00000000-0000-0000-0000-000000000002'::uuid],'2026-09-19','2026-09-19',NULL::uuid[])`,
  ];
  for (const sql of historicalQueries) {
    const rows=(await db.query(sql)).rows;
    assert.equal(rows.length,1);
    assert.equal(Number(rows[0].market_price),100);
    assert.equal(rows[0].source,'TCGPlayer');
  }
  for (const [source,price] of [['TCGPlayer',100],['eBayActiveAsk',140]]) {
    const rows=(await db.query(`SELECT market_price,source FROM public.get_card_variant_price_observed_history_v2(
      '00000000-0000-0000-0000-000000000004','4f8d1181-670e-4aea-937c-4d98d2e531a6',
      '2026-09-19','2026-09-19',$1,'USD')`,[source])).rows;
    assert.equal(rows.length,1);
    assert.equal(Number(rows[0].market_price),price);
    assert.equal(rows[0].source,source);
  }
  await db.query(`SELECT public.refresh_card_market_top_hits_by_edition_latest()`);
  const editionHit=(await db.query(`SELECT market_price,source FROM public.card_market_top_hits_by_edition_latest
    WHERE card_variant_id='00000000-0000-0000-0000-000000000004'`)).rows;
  assert.equal(editionHit.length,1,'editionHit');
  assert.equal(Number(editionHit[0].market_price),100);
  assert.equal(editionHit[0].source,'TCGPlayer');
  await db.query(`SELECT public.refresh_card_variant_market_metrics_latest()`);
  const metrics=(await db.query(`SELECT current_market_price FROM public.card_variant_market_metrics_latest
    WHERE card_variant_id='00000000-0000-0000-0000-000000000004'`)).rows;
  assert.equal(metrics.length,1,'metrics');
  assert.equal(Number(metrics[0].current_market_price),100);
  await db.query(`SELECT public.refresh_pokemon_set_value_daily_history('00000000-0000-0000-0000-000000000002','2026-09-19','2026-09-19')`);
  const setValue=(await db.query(`SELECT set_value FROM public.pokemon_set_value_daily_history
    WHERE set_id='00000000-0000-0000-0000-000000000002' AND snapshot_date='2026-09-19' AND value_scope='standard'`)).rows;
  assert.equal(setValue.length,1);
  assert.equal(Number(setValue[0].set_value),100);
  await db.exec(beforeFix);
  const contaminated = (await db.query(`SELECT market_price,source FROM public.get_pokemon_canonical_card_market_prices_latest_for_set_v2_shadow('00000000-0000-0000-0000-000000000002')`)).rows;
  assert.equal(contaminated[0].source,'eBayActiveAsk');
  for (const sql of [
    `SELECT source FROM public.card_market_usd_latest_by_condition WHERE variant_id='00000000-0000-0000-0000-000000000004'`,
    `SELECT source FROM public.card_market_usd_latest WHERE variant_id='00000000-0000-0000-0000-000000000004'`,
    `SELECT current_near_mint_price_source AS source FROM public.simulation_input_cards_with_near_mint_price`,
    `SELECT source FROM public.get_pokemon_market_root_set_card_prices_latest_v1_v2_shadow('00000000-0000-0000-0000-000000000002') WHERE market_scope='first_edition'`,
    `SELECT source FROM public.get_pokemon_set_value_canonical_prices_as_of_v2_shadow('00000000-0000-0000-0000-000000000002','2026-09-19')`,
  ]) assert.equal((await db.query(sql)).rows[0].source,'eBayActiveAsk');
  for (const sql of historicalQueries) assert.equal((await db.query(sql)).rows[0].source,'eBayActiveAsk');
  await db.query(`SELECT public.refresh_card_market_top_hits_by_edition_latest()`);
  assert.equal((await db.query(`SELECT source FROM public.card_market_top_hits_by_edition_latest WHERE card_variant_id='00000000-0000-0000-0000-000000000004'`)).rows[0].source,'eBayActiveAsk');
  await db.query(`SELECT public.refresh_card_variant_market_metrics_latest()`);
  assert.equal(Number((await db.query(`SELECT current_market_price FROM public.card_variant_market_metrics_latest WHERE card_variant_id='00000000-0000-0000-0000-000000000004'`)).rows[0].current_market_price),140);
  await db.query(`SELECT public.refresh_pokemon_set_value_daily_history('00000000-0000-0000-0000-000000000002','2026-09-19','2026-09-19')`);
  assert.equal(Number((await db.query(`SELECT set_value FROM public.pokemon_set_value_daily_history WHERE set_id='00000000-0000-0000-0000-000000000002' AND snapshot_date='2026-09-19' AND value_scope='standard'`)).rows[0].set_value),140);
  await db.exec(migration);
  await db.query(`SELECT public.refresh_card_market_top_hits_by_edition_latest()`);
  assert.equal((await db.query(`SELECT source FROM public.card_market_top_hits_by_edition_latest WHERE card_variant_id='00000000-0000-0000-0000-000000000004'`)).rows[0].source,'TCGPlayer');
  await db.query(`SELECT public.refresh_card_variant_market_metrics_latest()`);
  assert.equal(Number((await db.query(`SELECT current_market_price FROM public.card_variant_market_metrics_latest WHERE card_variant_id='00000000-0000-0000-0000-000000000004'`)).rows[0].current_market_price),100);
  await db.query(`SELECT public.refresh_pokemon_set_value_daily_history('00000000-0000-0000-0000-000000000002','2026-09-19','2026-09-19')`);
  assert.equal(Number((await db.query(`SELECT set_value FROM public.pokemon_set_value_daily_history WHERE set_id='00000000-0000-0000-0000-000000000002' AND snapshot_date='2026-09-19' AND value_scope='standard'`)).rows[0].set_value),100);
  await db.exec(`UPDATE public.card_variant_price_current_v2 SET last_observed_date='2026-09-18',last_observation_created_at='2026-09-18T13:00:00Z' WHERE source='eBayActiveAsk'`);
  await check(100,'TCGPlayer');
  await db.exec(`DELETE FROM public.card_variant_price_current_v2 WHERE source='TCGPlayer'`);
  const noCurrent=(await db.query(`SELECT * FROM public.get_pokemon_canonical_card_market_prices_latest_for_set_v2_shadow('00000000-0000-0000-0000-000000000002')`)).rows;
  assert.equal(noCurrent.length,0);
  await db.exec(`DELETE FROM public.card_variant_price_current_v2 WHERE source='eBayActiveAsk'`);
  assert.equal((await db.query(`SELECT * FROM public.card_market_usd_latest_by_condition WHERE variant_id='00000000-0000-0000-0000-000000000004'`)).rows.length,0);
  await db.exec(`DELETE FROM public.card_variant_price_events_v2 WHERE source='TCGPlayer';
    DELETE FROM public.card_variant_price_observation_ranges_v2 WHERE source='TCGPlayer'`);
  assert.equal((await db.query(`SELECT * FROM public.get_pokemon_set_value_canonical_prices_as_of_v2_shadow('00000000-0000-0000-0000-000000000002','2026-09-19')`)).rows.length,0);
  const freshnessEbayOnly=(await db.query(`SELECT public.get_nightly_snapshot_pricing_freshness('2026-09-19',25) AS result`)).rows[0].result;
  assert.equal(freshnessEbayOnly.fresh_asset_counts.cards,0);
  const hash=value=>createHash('sha256').update(JSON.stringify(value)).digest('hex');
  console.log(JSON.stringify({engine:'PGlite PostgreSQL WASM',mutation_cases:7,
    zero_diff_canonical_cards:productionBaseline.length,
    canonical_before_sha256:hash(cohortBefore),canonical_after_sha256:hash(cohortAfter),
    latest_view_before_sha256:hash(latestBefore),latest_view_after_sha256:hash(latestAfter),
    latest_view_rows:latestBefore.length,passed:true}));
} catch (error) {
  console.error(error.message);
  process.exitCode=1;
} finally { await db.close(); }
