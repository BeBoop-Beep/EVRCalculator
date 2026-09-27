// Run from the repo root with PGLITE_PACKAGE set. Applies the REAL migrations in order, including the V2 budget ledger.
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
const q = async (text) => (await db.query(text)).rows;
const failure = async (text) => {
  try { await db.exec(text); } catch (e) { return String(e.message); }
  return null;
};
const priv = async (role, table, p) => (await q(`select has_table_privilege('${role}','public.${table}','${p}') v`))[0].v;
const K = 'PRODUCTION:aaaaaaaaaaaaaaaa';
const reserve = (bucket, key = K) => q(`select public.reserve_ebay_api_request_v2('${key}','Browse','${bucket}') n`).then((r) => r[0].n);
const WS = new Date(Date.now() - 2 * 3600e3).toISOString(), WE = new Date(Date.now() + 22 * 3600e3).toISOString(); // one fixed provider window
const register = (bucket, limit = 5000, key = K, start = `'${WS}'::timestamptz`, reset = `'${WE}'::timestamptz`) =>
  q(`select public.register_ebay_api_budget_window_v2('${key}','Browse','${bucket}',${start},${reset},${limit}) r`).then((r) => r[0].r);

try {
  await db.exec(`CREATE ROLE anon; CREATE ROLE authenticated; CREATE ROLE service_role BYPASSRLS;
    GRANT USAGE ON SCHEMA public TO anon, authenticated, service_role;
    ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO service_role;
    ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO anon, authenticated;
    CREATE TABLE public.pokemon_canonical_cards (id uuid primary key);
    CREATE TABLE public.card_variants (id uuid primary key);
    CREATE TABLE public.conditions (id uuid primary key);`);
  const p4c = fs.readdirSync(path.join(root, 'backend/db/migrations')).find((f) => f.includes('ebay_active_ask'));
  for (const f of ['20260919212129_ebay_pricing_evidence_v1.sql', '20260919212741_restrict_ebay_pricing_evidence_privileges.sql', p4c,
    '20260921000000_p6_pipeline_runs_and_browse_budget_ledger.sql', '20260921010000_p5b_multi_source_card_prices_shadow_v1.sql',
    '20260921020000_p6_restrict_ebay_estimate_privileges.sql', '20260921100000_ebay_api_request_budget_v2.sql']) await db.exec(sql(f));

  // ---- schema, RLS, grants, function hardening
  const t = 'ebay_api_request_budget_v2';
  assert.equal((await q(`select relrowsecurity r from pg_class where oid='public.${t}'::regclass`))[0].r, true);
  assert.equal(await priv('service_role', t, 'select'), true);
  for (const p of ['insert', 'update', 'delete', 'truncate']) assert.equal(await priv('service_role', t, p), false, `service ${p}`);
  for (const role of ['anon', 'authenticated']) for (const p of ['select', 'insert', 'update', 'delete']) assert.equal(await priv(role, t, p), false);
  for (const fn of ['register_ebay_api_budget_window_v2', 'reserve_ebay_api_request_v2']) {
    const r = (await q(`select prosecdef, proconfig, pg_get_function_arguments(oid) args from pg_proc where proname='${fn}'`))[0];
    assert.equal(r.prosecdef, true); assert.ok(r.proconfig.some((c) => c.startsWith('search_path=')));
    assert.ok(!/reserve|usable/i.test(r.args), 'callers cannot pass a reserve or usable limit');
    for (const role of ['anon', 'authenticated']) assert.equal((await q(`select has_function_privilege('${role}','${fn}'::regproc,'execute') v`))[0].v, false);
    assert.equal((await q(`select has_function_privilege('service_role','${fn}'::regproc,'execute') v`))[0].v, true);
  }

  // ---- reserve is computed in the database: 500 of 5000 -> usable 4500; provider limit above 5000 is capped
  await register('BUY_BROWSE_STANDARD');
  let row = (await q(`select provider_limit, safety_reserve, usable_limit from public.${t} where resource_bucket='BUY_BROWSE_STANDARD'`))[0];
  assert.deepEqual(row, { provider_limit: 5000, safety_reserve: 500, usable_limit: 4500 });
  await register('BUY_BROWSE_BULK_ITEMS', 99999);
  row = (await q(`select provider_limit, usable_limit from public.${t} where resource_bucket='BUY_BROWSE_BULK_ITEMS'`))[0];
  assert.deepEqual(row, { provider_limit: 5000, usable_limit: 4500 });

  // ---- accounting inside the provider window; pools are independent and never borrow from each other
  assert.equal(await reserve('BUY_BROWSE_STANDARD'), 1);
  for (let i = 2; i <= 4500; i += 1) await reserve('BUY_BROWSE_STANDARD');
  assert.match(await failure(`select public.reserve_ebay_api_request_v2('${K}','Browse','BUY_BROWSE_STANDARD')`), /EBAY_BUDGET_EXHAUSTED/);
  assert.equal(await reserve('BUY_BROWSE_BULK_ITEMS'), 1, 'bulk pool untouched by standard exhaustion');
  const counts = Object.fromEntries((await q(`select resource_bucket, requests_reserved from public.${t}`)).map((r) => [r.resource_bucket, r.requests_reserved]));
  assert.deepEqual(counts, { BUY_BROWSE_STANDARD: 4500, BUY_BROWSE_BULK_ITEMS: 1 });

  // ---- provider analytics lag: re-registering never reconciles the count downward; a lowered provider limit lowers usable
  assert.equal(await register('BUY_BROWSE_STANDARD'), 4500);
  await register('BUY_BROWSE_STANDARD', 2000);
  row = (await q(`select provider_limit, usable_limit, requests_reserved from public.${t} where resource_bucket='BUY_BROWSE_STANDARD'`))[0];
  assert.deepEqual(row, { provider_limit: 2000, usable_limit: 1800, requests_reserved: 4500 });
  assert.match(await failure(`select public.reserve_ebay_api_request_v2('${K}','Browse','BUY_BROWSE_STANDARD')`), /EBAY_BUDGET_EXHAUSTED/);

  // ---- unknown identity fails closed; a different keyset has its own budget
  assert.match(await failure(`select public.reserve_ebay_api_request_v2('OTHER:bbbbbbbbbbbbbbbb','Browse','BUY_BROWSE_STANDARD')`), /EBAY_BUDGET_WINDOW_UNKNOWN/);

  // ---- degraded mode: window ended, last verification < 36h -> next window derived contiguously; then stale -> closed
  const K2 = 'PRODUCTION:cccccccccccccccc';
  await register('BUY_BROWSE_STANDARD', 5000, K2, "now() - interval '30 hours'", "now() - interval '6 hours'");
  assert.equal(await reserve('BUY_BROWSE_STANDARD', K2), 1);
  const derived = (await q(`select provider_usage_state s, provider_window_start <= now() as covers, provider_window_end > now() as future, (provider_window_end - provider_window_start) = interval '24 hours' as len
    from public.${t} where provider_keyset_identity='${K2}' and provider_usage_state='DERIVED_FROM_LAST_VERIFIED'`))[0];
  assert.deepEqual(derived, { s: 'DERIVED_FROM_LAST_VERIFIED', covers: true, future: true, len: true });
  await db.exec(`update public.${t} set verified_at = now() - interval '37 hours' where provider_keyset_identity='${K2}'`);
  assert.match(await failure(`select public.reserve_ebay_api_request_v2('${K2}','Browse','BUY_BROWSE_STANDARD')`), /EBAY_BUDGET_VERIFICATION_STALE/);

  // ---- V1 ledger preserved and still working; only the two hard-coded 1000 checks were relaxed
  await db.exec(`insert into public.ebay_browse_request_ledger_v1 values ('2026-09-21', 5, 1000, now())`);
  assert.equal((await q(`select public.reserve_ebay_browse_request_v1('2026-09-21', 1000) n`))[0].n, 6);
  const run = (cap) => `insert into public.pokemon_multi_source_pricing_runs_v1 (market_date, policy_version, pipeline_version, status, stage, request_cap)
    values ('2026-09-2${cap === 4500 ? 1 : 2}', 'pokemon_multi_source_card_price_v1', 'multi_source_daily_pipeline_p6_v2', 'RUNNING', 'INIT', ${cap})`;
  await db.exec(run(4500));
  assert.match(await failure(run(5001)), /violates/);

  const forbidden = ['card_variant_price_observations', 'card_variant_price_events_v2', 'card_variant_price_current_v2', 'pokemon_canonical_card_market_prices_latest'];
  const text = sql('20260921100000_ebay_api_request_budget_v2.sql').replace(/--.*$/gm, '');
  for (const name of forbidden) assert.equal(text.includes(name), false, name);
  console.log('P6.6 quota V2 disposable PostgreSQL integration: passed');
} finally {
  await db.close();
}
