// Run with Node from the repo root; PGLITE_PACKAGE points to an external @electric-sql/pglite install
// (…/node_modules/@electric-sql/pglite/dist/index.js). Applies the REAL P3/P4C/P6/P5B migrations in order.
import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import assert from 'node:assert/strict';

const packagePath = process.env.PGLITE_PACKAGE;
if (!packagePath) throw new Error('PGLITE_PACKAGE is required');
const { PGlite } = await import(pathToFileURL(packagePath));
const db = await PGlite.create();
const root = process.cwd();
const sql = (name) => fs.readFileSync(path.join(root, 'backend/db/migrations', name), 'utf8');
const q = async (text, params) => (await db.query(text, params)).rows;
const denied = async (text) => {
  try { await db.exec(text); } catch (e) { return /permission denied|violates|EBAY_BROWSE_BUDGET_EXHAUSTED|invalid/.test(String(e.message)) ? String(e.message) : (() => { throw e; })(); }
  return null;
};
const priv = async (role, table, p) => (await q(`select has_table_privilege('${role}','public.${table}','${p}') v`))[0].v;

try {
  await db.exec(`CREATE ROLE anon; CREATE ROLE authenticated; CREATE ROLE service_role BYPASSRLS;
    GRANT USAGE ON SCHEMA public TO anon, authenticated, service_role;
    -- Supabase default privileges: new public tables are inherited by service_role (the P4C defect).
    ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO service_role;
    ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO anon, authenticated;
    CREATE TABLE public.pokemon_canonical_cards (id uuid primary key);
    CREATE TABLE public.card_variants (id uuid primary key);
    CREATE TABLE public.conditions (id uuid primary key);`);
  const card = '00000000-0000-0000-0000-0000000000c1', variant = '00000000-0000-0000-0000-0000000000a1',
    cond = '4f8d1181-670e-4aea-937c-4d98d2e531a6';
  await db.exec(`INSERT INTO public.pokemon_canonical_cards VALUES ('${card}'); INSERT INTO public.card_variants VALUES ('${variant}');
    INSERT INTO public.conditions VALUES ('${cond}');`);

  for (const file of ['20260919212129_ebay_pricing_evidence_v1.sql', '20260919212741_restrict_ebay_pricing_evidence_privileges.sql'])
    await db.exec(sql(file));
  const p4cFile = fs.readdirSync(path.join(root, 'backend/db/migrations')).find((f) => f.includes('ebay_active_ask'));
  await db.exec(sql(p4cFile));

  // BEFORE the P6 fix the inherited privileges are broad (the defect this bucket corrects).
  for (const p of ['update', 'delete', 'truncate']) assert.equal(await priv('service_role', 'ebay_active_ask_price_estimates_v1', p), true, `pre-fix ${p}`);

  for (const file of ['20260921000000_p6_pipeline_runs_and_browse_budget_ledger.sql',
    '20260921010000_p5b_multi_source_card_prices_shadow_v1.sql', '20260921020000_p6_restrict_ebay_estimate_privileges.sql'])
    await db.exec(sql(file));

  // ---- P4C estimate table: normal authority is exactly SELECT + INSERT.
  const est = 'ebay_active_ask_price_estimates_v1';
  assert.equal(await priv('service_role', est, 'select'), true);
  assert.equal(await priv('service_role', est, 'insert'), true);
  for (const p of ['update', 'delete', 'truncate', 'references', 'trigger']) assert.equal(await priv('service_role', est, p), false, p);
  for (const role of ['anon', 'authenticated']) for (const p of ['select', 'insert', 'update', 'delete']) assert.equal(await priv(role, est, p), false, `${role} ${p}`);
  assert.equal((await q(`select relrowsecurity r from pg_class where oid='public.${est}'::regclass`))[0].r, true);

  // ---- new tables: RLS on, no public roles, service_role privileges exactly as designed.
  const expected = {
    pokemon_multi_source_pricing_runs_v1: { select: true, insert: true, update: true, delete: false, truncate: false },
    ebay_browse_request_ledger_v1: { select: true, insert: false, update: false, delete: false, truncate: false },
    pokemon_multi_source_card_prices_v1: { select: true, insert: true, update: false, delete: false, truncate: false },
  };
  for (const [table, grants] of Object.entries(expected)) {
    assert.equal((await q(`select relrowsecurity r from pg_class where oid='public.${table}'::regclass`))[0].r, true, `${table} rls`);
    for (const [p, want] of Object.entries(grants)) assert.equal(await priv('service_role', table, p), want, `${table} service ${p}`);
    for (const role of ['anon', 'authenticated']) for (const p of ['select', 'insert', 'update', 'delete']) assert.equal(await priv(role, table, p), false, `${table} ${role} ${p}`);
  }

  // ---- budget ledger RPC: atomic, monotonic, exhaustion raises, direct mutation denied.
  const fn = (await q(`select prosecdef, proconfig from pg_proc where proname='reserve_ebay_browse_request_v1'`))[0];
  assert.equal(fn.prosecdef, true);
  assert.ok(fn.proconfig.some((c) => c.startsWith('search_path=')));
  assert.equal((await q(`select has_function_privilege('anon','public.reserve_ebay_browse_request_v1(date,integer)','execute') v`))[0].v, false);
  assert.equal((await q(`select has_function_privilege('authenticated','public.reserve_ebay_browse_request_v1(date,integer)','execute') v`))[0].v, false);
  assert.equal((await q(`select has_function_privilege('service_role','public.reserve_ebay_browse_request_v1(date,integer)','execute') v`))[0].v, true);
  await db.exec(`INSERT INTO public.ebay_browse_request_ledger_v1 (budget_day, requests_reserved, daily_limit) VALUES ('2026-09-20', 836, 1000);`);
  for (let i = 837; i <= 1000; i += 1) {
    const n = (await q(`select public.reserve_ebay_browse_request_v1('2026-09-20', 1000) n`))[0].n;
    assert.equal(n, i);
  }
  assert.match(await denied(`select public.reserve_ebay_browse_request_v1('2026-09-20', 1000)`), /EBAY_BROWSE_BUDGET_EXHAUSTED/);
  assert.equal((await q(`select requests_reserved n from public.ebay_browse_request_ledger_v1 where budget_day='2026-09-20'`))[0].n, 1000);
  // a lower caller limit is honoured; a limit above 1000 is rejected
  assert.equal((await q(`select public.reserve_ebay_browse_request_v1('2026-09-21', 3) n`))[0].n, 1);
  await db.exec(`select public.reserve_ebay_browse_request_v1('2026-09-21', 3); select public.reserve_ebay_browse_request_v1('2026-09-21', 3);`);
  assert.match(await denied(`select public.reserve_ebay_browse_request_v1('2026-09-21', 3)`), /EBAY_BROWSE_BUDGET_EXHAUSTED/);
  assert.match(await denied(`select public.reserve_ebay_browse_request_v1('2026-09-22', 1001)`), /invalid/);
  await db.exec(`SET ROLE service_role`);
  assert.match(await denied(`update public.ebay_browse_request_ledger_v1 set requests_reserved = 0`), /permission denied/);
  assert.match(await denied(`insert into public.ebay_browse_request_ledger_v1 values ('2026-10-01', 0, 1000, now())`), /permission denied/);
  assert.match(await denied(`delete from public.ebay_active_ask_price_estimates_v1`), /permission denied/);
  assert.match(await denied(`truncate public.ebay_active_ask_price_estimates_v1`), /permission denied/);
  await db.exec(`RESET ROLE; SET ROLE anon`);
  assert.match(await denied(`select * from public.pokemon_multi_source_card_prices_v1`), /permission denied/);
  await db.exec(`RESET ROLE`);

  // ---- pipeline run identity: one run per market date and policy; COMPLETE requires the terminal stage.
  const run = '11111111-1111-1111-1111-111111111111';
  await db.exec(`INSERT INTO public.pokemon_multi_source_pricing_runs_v1 (run_id, market_date, policy_version, pipeline_version, status, stage, request_cap)
    VALUES ('${run}', '2026-09-20', 'pokemon_multi_source_card_price_v1', 'p6_v1', 'RUNNING', 'INIT', 1000)`);
  assert.match(await denied(`INSERT INTO public.pokemon_multi_source_pricing_runs_v1 (market_date, policy_version, pipeline_version, status, stage, request_cap)
    VALUES ('2026-09-20', 'pokemon_multi_source_card_price_v1', 'p6_v1', 'RUNNING', 'INIT', 1000)`), /duplicate|unique/);
  assert.match(await denied(`UPDATE public.pokemon_multi_source_pricing_runs_v1 SET status='COMPLETE' WHERE run_id='${run}'`), /violates/);
  assert.match(await denied(`INSERT INTO public.pokemon_multi_source_pricing_runs_v1 (market_date, policy_version, pipeline_version, status, stage, request_cap)
    VALUES ('2026-09-21', 'pokemon_multi_source_card_price_v1', 'p6_v1', 'RUNNING', 'INIT', 1001)`), /violates/);
  assert.match(await denied(`INSERT INTO public.pokemon_multi_source_pricing_runs_v1 (market_date, policy_version, pipeline_version, status, stage, request_cap)
    VALUES ('2026-09-21', 'some_other_policy', 'p6_v1', 'RUNNING', 'INIT', 1000)`), /violates/);

  // ---- shadow table: contract checks, FK to the run, estimate linkage, no-blend rules.
  const fp = (c) => `repeat('${c}',64)`;
  const insertRow = (day, vals) => `INSERT INTO public.pokemon_multi_source_card_prices_v1
    (canonical_card_id, card_variant_id, condition_id, market_date, pipeline_run_id, ebay_estimate_id, policy_version, selected_price, selected_price_source,
     decision_state, decision_reason, tcgplayer_price, tcgplayer_freshness_state, ebay_price, ebay_depth_state, source_agreement_state, input_fingerprint, decision_fingerprint)
    VALUES ('${card}','${variant}','${cond}','${day}','${run}', ${vals.est ?? 'null'}, 'pokemon_multi_source_card_price_v1', ${vals.sel}, ${vals.src},
     '${vals.state}', 'x', ${vals.tcg}, '${vals.fresh}', ${vals.ebay}, ${vals.depth}, '${vals.agree}', ${fp('a')}, ${fp('b')})`;
  const estimate = '22222222-2222-2222-2222-222222222222';
  await db.exec(`INSERT INTO public.ebay_pricing_runs_v1 (run_id, market_date, status, selector_version, selector_fingerprint, collector_version, query_strategy_version,
      target_count, planned_request_count, started_at, artifact_manifest_path, artifact_run_id, run_fingerprint)
    VALUES ('33333333-3333-3333-3333-333333333333','2026-09-20','COMPLETE','s',${fp('a')},'c','q',1,7,now(),'m','r',${fp('a')});
    INSERT INTO public.ebay_active_ask_price_estimates_v1 (id, pricing_run_id, canonical_card_id, card_variant_id, condition_id, market_date, estimator_version, eligibility_policy_version,
      eligible_listing_count, distinct_seller_count, landed_ask_min, landed_ask_max, selected_ask_1, selected_ask_2, selected_ask_3, estimated_price, depth_state,
      input_evidence_fingerprint, estimator_fingerprint, contributing_evidence, source_artifact_fingerprint)
    VALUES ('${estimate}','33333333-3333-3333-3333-333333333333','${card}','${variant}','${cond}','2026-09-20','ebay_active_ask_lower3_seller_median_v1','e',5,5,4,9,4,5,6,5,'SUFFICIENT',
      ${fp('a')},${fp('a')},'[1,2,3,4,5]'::jsonb,${fp('a')});`);
  await db.exec(insertRow('2026-09-20', { sel: '5.00', src: "'TCGPLAYER'", state: 'TCGPLAYER_PRIMARY_EBAY_CORROBORATED', tcg: '5.00', fresh: 'FRESH', ebay: '5.00', depth: "'SUFFICIENT'", agree: 'AGREE', est: `'${estimate}'` }));
  // blend, THIN fallback, unlinked eBay price and a wrong-provider price must all be rejected
  assert.match(await denied(insertRow('2026-09-21', { sel: '5.50', src: "'TCGPLAYER'", state: 'TCGPLAYER_PRIMARY_EBAY_CORROBORATED', tcg: '5.00', fresh: 'FRESH', ebay: '6.00', depth: "'SUFFICIENT'", agree: 'AGREE', est: `'${estimate}'` })), /violates/);
  assert.match(await denied(insertRow('2026-09-22', { sel: '6.00', src: "'EBAY_ACTIVE_ASK'", state: 'EBAY_ACTIVE_ASK_FALLBACK', tcg: 'null', fresh: 'MISSING', ebay: '6.00', depth: "'THIN'", agree: 'SINGLE_SOURCE_ONLY', est: `'${estimate}'` })), /violates/);
  assert.match(await denied(insertRow('2026-09-23', { sel: '5.00', src: "'TCGPLAYER'", state: 'TCGPLAYER_PRIMARY_EBAY_CORROBORATED', tcg: '5.00', fresh: 'FRESH', ebay: '5.00', depth: "'SUFFICIENT'", agree: 'AGREE' })), /violates/);
  assert.match(await denied(insertRow('2026-09-24', { sel: '5.00', src: "'EBAY_ACTIVE_ASK'", state: 'EBAY_ACTIVE_ASK_FALLBACK', tcg: 'null', fresh: 'MISSING', ebay: '6.00', depth: "'SUFFICIENT'", agree: 'SINGLE_SOURCE_ONLY', est: `'${estimate}'` })), /violates/);
  assert.match(await denied(insertRow('2026-09-20', { sel: '5.00', src: "'TCGPLAYER'", state: 'TCGPLAYER_PRIMARY_EBAY_CORROBORATED', tcg: '5.00', fresh: 'FRESH', ebay: '5.00', depth: "'SUFFICIENT'", agree: 'AGREE', est: `'${estimate}'` })), /duplicate|unique/);
  // legitimate fallback and unpriced rows
  await db.exec(insertRow('2026-09-25', { sel: '5.00', src: "'EBAY_ACTIVE_ASK'", state: 'EBAY_ACTIVE_ASK_FALLBACK', tcg: 'null', fresh: 'MISSING', ebay: '5.00', depth: "'SUFFICIENT'", agree: 'SINGLE_SOURCE_ONLY', est: `'${estimate}'` }));
  await db.exec(insertRow('2026-09-26', { sel: 'null', src: 'null', state: 'UNPRICED', tcg: 'null', fresh: 'MISSING', ebay: 'null', depth: "'THIN'", agree: 'SINGLE_SOURCE_ONLY' }));

  // ---- P6 must not touch generic price storage or canonical pricing objects.
  const forbidden = ['card_variant_price_observations', 'card_variant_price_events_v2', 'card_variant_price_current_v2', 'pokemon_canonical_card_market_prices_latest'];
  for (const file of ['20260921000000_p6_pipeline_runs_and_browse_budget_ledger.sql', '20260921010000_p5b_multi_source_card_prices_shadow_v1.sql', '20260921020000_p6_restrict_ebay_estimate_privileges.sql'])
    for (const name of forbidden) assert.equal(sql(file).replace(/--.*$/gm, '').includes(name), false, `${file} mentions ${name}`);
  console.log('P6 disposable PostgreSQL integration: passed');
} finally {
  await db.close();
}
