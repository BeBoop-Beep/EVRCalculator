import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
// Run from repo root: PGLITE_PACKAGE=<path to @electric-sql/pglite/dist/index.js> node backend/tests/integration/explorer_constituent_authority/run.mjs
const { PGlite } = await import(pathToFileURL(process.env.PGLITE_PACKAGE));
const HERE = path.dirname(new URL(import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1'));
const WT = process.cwd();
const read = (p) => fs.readFileSync(p, 'utf8').replace(/\r\n/g, '\n');
const mig = (n) => read(`${WT}/backend/db/migrations/${n}`);
const MIG = '20260924000000_prepared_constituent_authority_v1.sql';
const out = [];
const log = (k, v) => { out.push([k, v]); console.log(`## ${k}\n${typeof v === 'string' ? v : JSON.stringify(v, null, 1)}`); };
const db = await PGlite.create();
const q = async (sql, params) => (await db.query(sql, params)).rows;
const T = async (label, fn) => { const t = performance.now(); try { const r = await fn(); return { r, ms: +(performance.now() - t).toFixed(1) }; } catch (e) { return { err: String(e.message).slice(0, 400), ms: +(performance.now() - t).toFixed(1), label }; } };

log('pg_version', (await q('select version()'))[0].version);
await db.exec(read(HERE + '/fixture_pre.sql'));
await db.exec('set check_function_bodies=off');
await db.exec("create function public.refresh_pokemon_market_explorer_prepared_directory_v1() returns jsonb language sql as $$ select null::jsonb $$");
await db.exec(mig('20260911200732_market_explorer_phase5_prepared_directory_serving_contract.sql'));
// Seed the legacy first generation (what prod had before retention migration).
await db.exec(`insert into public.pokemon_market_explorer_prepared_directory_v1
 (market_key,market_type,label,asset,prepared_series_key,comparison_as_of,source_as_of,history_available,history_point_count,source_kind,generation_id,generated_at)
 values ('set:legacy','set','Legacy','cards','k',date '2026-09-19',date '2026-09-19',true,1,'public_set_snapshot','99999999-0000-0000-0000-000000000000',timestamptz '2026-09-20 00:00+00');
 insert into public.pokemon_market_explorer_prepared_history_v1 values ('set:legacy',date '2026-09-19',100,null,0,'99999999-0000-0000-0000-000000000000');`);
await db.exec(mig('20260920000523_retain_market_explorer_prepared_generations.sql').split(String.fromCharCode(10)).slice(0,247).join(String.fromCharCode(10))); // DDL + switch/rollback/cleanup fns; trailing DO blocks textually rewrite the prod refresh + readers, which the fixtures replace
await db.exec(read(HERE + '/v2_prod.sql'));
await db.exec(read(HERE + '/fixture_post.sql'));
await db.exec(read(HERE + '/fixture_data.sql'));
await db.exec("set check_function_bodies=on");
log('pre_state', {
  migrations_replayed: ['20260911200732', '20260920000523', 'fixture: v2 (prod verbatim), wrapper+if_current (prod verbatim), refresh stub, resolver stub, query cache + snapshot tables'],
  serving: await q('select generation_id from public.pokemon_market_explorer_prepared_serving_v1'),
  has_totals_table_before: (await q("select to_regclass('public.pokemon_market_explorer_prepared_constituent_totals_v1') r"))[0].r,
});

// ---- Phase 1: execute the migration ----
const sql = mig(MIG);
const run = await T('migration', () => db.exec(sql));
log('migration_execute', run.err ? { ERROR: run.err } : { ok: true, ms: run.ms });
if (run.err) process.exit(2);
// second run = idempotency (CREATE IF NOT EXISTS / OR REPLACE)
const run2 = await T('migration_rerun', () => db.exec(sql));
log('migration_rerun_idempotent', run2.err ? { ERROR: run2.err } : { ok: true, ms: run2.ms });

log('objects', {
  tables: await q("select relname, relrowsecurity rls from pg_class where relname like 'pokemon_market_explorer_prepared_constituent%'"),
  functions: await q("select proname, pg_get_function_identity_arguments(oid) args, prosecdef, proconfig from pg_proc where proname in ('get_pokemon_market_explorer_prepared_constituents_v3','stage_pokemon_market_explorer_prepared_constituents_v1','run_market_explorer_guarded_publisher_v1','get_pokemon_market_explorer_prepared_constituents_v2') order by 1"),
  indexes: await q("select indexname from pg_indexes where tablename like 'pokemon_market_explorer_prepared_constituent%' order by 1"),
  constraints: await q("select conrelid::regclass::text t, conname, contype from pg_constraint where conrelid::regclass::text like '%prepared_constituent%' order by 1,2"),
  wrapper_acl: await q("select proacl::text, proowner::regrole::text from pg_proc where proname='run_market_explorer_guarded_publisher_v1'"),
  stage_acl: await q("select proacl::text from pg_proc where proname='stage_pokemon_market_explorer_prepared_constituents_v1'"),
  v3_acl: await q("select proacl::text from pg_proc where proname='get_pokemon_market_explorer_prepared_constituents_v3'"),
  table_privs: await q("select grantee, table_name, string_agg(privilege_type,',' order by privilege_type) p from information_schema.role_table_grants where table_name like 'pokemon_market_explorer_prepared_constituent%' and grantee in ('anon','authenticated','service_role','PUBLIC') group by 1,2 order by 2,1"),
});

// ---- Phase 2: publish through the wrapper ----
const pub = await T('publish', () => q("select public.run_market_explorer_guarded_publisher_v1(date '2026-09-22') r"));
log('publish_first', pub.err ? { ERROR: pub.err } : { ms: pub.ms, result: pub.r[0].r });
const G = (await q('select generation_id from public.pokemon_market_explorer_prepared_serving_v1'))[0].generation_id;
log('serving_after_publish', G);
log('staged_totals', await q(`select market_key, asset, source_kind, total_count, availability, availability_reason, source_as_of from public.pokemon_market_explorer_prepared_constituent_totals_v1 where generation_id=$1 order by market_key`, [G]));
log('integrity', {
  rank_gaps: await q(`select t.market_key from public.pokemon_market_explorer_prepared_constituent_totals_v1 t left join (select market_key,count(*) n,min(rank) mn,max(rank) mx,count(distinct instrument_id) di from public.pokemon_market_explorer_prepared_constituents_v1 where generation_id=$1 group by 1) c using(market_key) where t.generation_id=$1 and t.availability='available' and (c.n<>t.total_count or c.mn<>1 or c.mx<>t.total_count or c.di<>c.n)`, [G]),
  null_price_or_date: await q(`select market_key,count(*) from public.pokemon_market_explorer_prepared_constituents_v1 where generation_id=$1 and (market_price is null or price_as_of is null) group by 1`, [G]),
  rows_total: await q(`select count(*) from public.pokemon_market_explorer_prepared_constituents_v1 where generation_id=$1`, [G]),
});

// ---- Membership: staged set roster vs independently derived canonical membership ----
for (const [name, root] of [['Team Rocket', '50000000-0000-0000-0000-000000000001'], ['Modern Root(child subset)', '50000000-0000-0000-0000-000000000002'], ['Big Set', '50000000-0000-0000-0000-000000000003']]) {
  const r = await q(`with staged as (select instrument_id from public.pokemon_market_explorer_prepared_constituents_v1 where generation_id=$1 and market_key='set:'||$2::text),
   canon as (select card_variant_id::text instrument_id from public.fx_roster where root_set_id=$2::uuid and counts_toward_parent_set_value)
   select (select count(*) from staged) staged_n,(select count(*) from canon) canon_n,(select count(*) from (select * from staged except select * from canon) x) staged_minus_canon,(select count(*) from (select * from canon except select * from staged) y) canon_minus_staged`, [G, root]);
  log('membership_' + name, r[0]);
}
log('membership_excluded_noncounting_child', await q(`select count(*) staged_from_noncounting from public.pokemon_market_explorer_prepared_constituents_v1 c where generation_id=$1 and market_key='set:50000000-0000-0000-0000-000000000002' and item->>'setId'='50000000-0000-0000-0000-0000000000c3'`, [G]));
log('membership_child_included', await q(`select item->>'setId' set_id, count(*) from public.pokemon_market_explorer_prepared_constituents_v1 where generation_id=$1 and market_key='set:50000000-0000-0000-0000-000000000002' group by 1 order by 1`, [G]));
log('physical_variants_tr', await q(`select count(*) rows, count(distinct item->>'canonicalCardId') canonical_cards from public.pokemon_market_explorer_prepared_constituents_v1 where generation_id=$1 and market_key='set:50000000-0000-0000-0000-000000000001'`, [G]));

// ---- v3 reader direct tests ----
const R = async (k, g, a, l) => (await q('select public.get_pokemon_market_explorer_prepared_constituents_v3($1,$2,$3,$4) r', [k, g, a, l]))[0].r;
const brief = (r) => ({ av: r.availability, code: r.code, total: r.totalCount, n: r.returnedCount, next: r.nextCursor, gen: r.generationId === G, ranks: r.rows ? [r.rows[0]?.rank, r.rows[r.rows.length - 1]?.rank] : undefined, reason: r.availabilityReason });
const BIG = 'set:50000000-0000-0000-0000-000000000003';
const p1 = await R(BIG, G, 0, 100), p2 = await R(BIG, G, p1.nextCursor, 100), p3 = await R(BIG, G, p2.nextCursor, 100);
log('reader_big_pages', [brief(p1), brief(p2), brief(p3)]);
const all = [...p1.rows, ...p2.rows, ...p3.rows];
log('reader_big_stability', { rows: all.length, dupRank: all.length - new Set(all.map((x) => x.rank)).size, dupId: all.length - new Set(all.map((x) => x.instrumentId)).size, contiguous: all.every((x, i) => x.rank === i + 1), totalConstant: [p1, p2, p3].every((p) => p.totalCount === 250), boundaryOK: p1.rows.at(-1).rank + 1 === p2.rows[0].rank });
log('reader_limit1', brief(await R(BIG, G, 0, 1)));
log('reader_after_boundary', [brief(await R(BIG, G, 249, 100)), brief(await R(BIG, G, 250, 100)), brief(await R(BIG, G, 251, 100))]);
log('reader_invalid', { limit0: brief(await R(BIG, G, 0, 0)), limit101: brief(await R(BIG, G, 0, 101)), neg: brief(await R(BIG, G, -1, 10)), unknown: brief(await R('set:nope', G, 0, 10)), badGen: brief(await R(BIG, 'aaaaaaaa-0000-0000-0000-00000000000a', 0, 10)), emptyKey: brief(await R('', G, 0, 10)) });
for (const k of ['set:50000000-0000-0000-0000-000000000001', 'set:50000000-0000-0000-0000-000000000002', 'era:ex', 'rarity:rareUltra', 'curated:obtainable', 'sealed-format:boosterBox', 'sealed-format:eliteTrainerBox', 'sealed-format:packs']) {
  const a = await R(k, G, 0, 100); log('reader_' + k, brief(a));
}
const pk1 = await R('sealed-format:packs', G, 0, 100), pk2 = await R('sealed-format:packs', G, pk1.nextCursor, 100);
log('reader_packs_page2', { p1: brief(pk1), p2: brief(pk2), dupId: new Set([...pk1.rows, ...pk2.rows].map((x) => x.sealedProductId)).size, rows: pk1.rows.length + pk2.rows.length, bytes_p2: JSON.stringify(pk2).length });
const ex1 = await R('era:ex', G, 0, 100), ex2 = await R('era:ex', G, ex1.nextCursor, 100);
log('reader_era_page2', { p1: brief(ex1), p2: brief(ex2) });

// ---- Old problems gone: page 1/2 work + resolver-call counts + payload ----
// Mutate the mutable upstreams AFTER staging: if v3 still serves complete pages it read only the compact tables.
await db.exec("create temp table fx_backup as select * from public.fx_roster");
await db.exec("delete from public.fx_roster where root_set_id='50000000-0000-0000-0000-000000000003'");
const v3set = await T('v3 set p1', () => R(BIG, G, 0, 100)); const v3set2 = await T('v3 set p2', () => R(BIG, G, 100, 100));
const v2set = await T('v2 set p1', () => q('select public.get_pokemon_market_explorer_prepared_constituents_v2($1,$2,0,100) r', [BIG, G])); const v2set2 = await T('v2 set p2', () => q('select public.get_pokemon_market_explorer_prepared_constituents_v2($1,$2,100,100) r', [BIG, G]));
log('set_paging_recompute_proof_upstream_roster_deleted', { v3_p1: { n: v3set.r.returnedCount, total: v3set.r.totalCount, ms: v3set.ms }, v3_p2: { n: v3set2.r.returnedCount, ms: v3set2.ms }, v2_p1_total_after_upstream_delete: v2set.r[0].r.totalCount, v2_p2_n: v2set2.r[0].r.returnedCount });
await db.exec("insert into public.fx_roster select * from fx_backup where root_set_id='50000000-0000-0000-0000-000000000003'");
await db.exec("create temp table snap_backup as select payload_json from public.pokemon_explore_set_value_snapshot_latest");
await db.exec("update public.pokemon_explore_set_value_snapshot_latest set payload_json='{}'::jsonb");
const sv3 = await R('sealed-format:packs', G, 100, 100);
log('sealed_paging_proof_payload_emptied', { v3_p2_n: sv3.returnedCount, total: sv3.totalCount });
await db.exec("update public.pokemon_explore_set_value_snapshot_latest set payload_json=(select payload_json from snap_backup)");
const bytes = (await q("select pg_column_size(payload_json) stored, length(payload_json::text) chars from public.pokemon_explore_set_value_snapshot_latest"))[0];
const s3 = await T('v3 packs p2', () => R('sealed-format:packs', G, 100, 100)); const s2 = await T('v2 packs p2', () => q('select public.get_pokemon_market_explorer_prepared_constituents_v2($1,$2,100,100) r', ['sealed-format:packs', G]));
log('sealed_page2_v3_vs_v2', { payload: bytes, v3_ms: s3.ms, v2_ms: s2.ms, v2_note: 'v2 sealed extracts from the payload_json above on every page; v3 reads compact table only' });
// relation used by v3 (static): function body references only compact tables
log('v3_body_relations', (await q("select regexp_matches(prosrc, 'public\\.[a-z_0-9]+', 'g') m from pg_proc where proname='get_pokemon_market_explorer_prepared_constituents_v3'")).map((r) => r.m[0]).filter((v, i, a) => a.indexOf(v) === i));
log('explain_v3_page', (await q(`explain (analyze, buffers off, timing off, costs off) select rank,item from public.pokemon_market_explorer_prepared_constituents_v1 where generation_id=$1 and market_key=$2 and rank>100 order by rank limit 100`, [G, BIG])).map((r) => r['QUERY PLAN']));

// ---- Generation mismatch after a new publication ----
const oldG = G;
await db.exec("update public.pokemon_explore_set_value_snapshot_latest set updated_at=clock_timestamp()+interval '1 hour'");
await db.exec("update public.pokemon_market_explorer_query_cache set last_built_at=clock_timestamp()+interval '1 hour'");
const pub2 = await T('publish2', () => q("select public.run_market_explorer_guarded_publisher_v1(date '2026-09-22') r"));
log('publish_second', pub2.err ? { ERROR: pub2.err } : { ms: pub2.ms, status: pub2.r[0].r.status, constituents: pub2.r[0].r.constituents });
const G2 = (await q('select generation_id from public.pokemon_market_explorer_prepared_serving_v1'))[0].generation_id;
log('generation_changed', G2 !== oldG);
log('old_gen_paging_after_new_publish', brief(await R(BIG, oldG, 0, 100)));
log('old_gen_rows_retained', (await q('select count(*) from public.pokemon_market_explorer_prepared_constituents_v1 where generation_id=$1', [oldG]))[0]);
// already_current path (no-op) + self-heal when serving generation lacks staged rows
await db.exec("update public.pokemon_explore_set_value_snapshot_latest set updated_at=timestamptz '2026-09-22 02:00+00'");
await db.exec("update public.pokemon_market_explorer_query_cache set last_built_at=timestamptz '2026-09-22 01:00+00'");
const pub3 = await T('publish3', () => q("select public.run_market_explorer_guarded_publisher_v1(date '2026-09-22') r"));
log('publish_already_current', pub3.err ? { ERROR: pub3.err } : pub3.r[0].r);
await db.exec(`delete from public.pokemon_market_explorer_prepared_constituent_totals_v1 where generation_id='${G2}'`);
const pub4 = await T('publish4', () => q("select public.run_market_explorer_guarded_publisher_v1(date '2026-09-22') r"));
log('publish_already_current_selfheal', pub4.err ? { ERROR: pub4.err } : { status: pub4.r[0].r.status, staged: pub4.r[0].r.constituents });
// v2 fallback for an unstaged generation
await db.exec(`delete from public.pokemon_market_explorer_prepared_constituent_totals_v1 where generation_id='${G2}'`);
log('v3_fallback_to_v2_when_unstaged', brief(await R('sealed-format:boosterBox', G2, 0, 100)));
await db.exec(`select public.stage_pokemon_market_explorer_prepared_constituents_v1('${G2}')`);

// ---- Atomicity: staging failure must roll back promotion ----
await db.exec("update public.pokemon_explore_set_value_snapshot_latest set updated_at=clock_timestamp()+interval '2 hour'");
await db.exec("update public.pokemon_market_explorer_query_cache set last_built_at=clock_timestamp()+interval '2 hour'");
await db.exec("update public.pokemon_market_explorer_query_cache set constituent_count=121 where query_fingerprint='fp_era_ex'");
const servingBefore = (await q('select generation_id from public.pokemon_market_explorer_prepared_serving_v1'))[0].generation_id;
const gensBefore = (await q('select count(*)::int c from public.pokemon_market_explorer_prepared_generations_v1'))[0].c;
const bad = await T('publish_bad', () => q("select public.run_market_explorer_guarded_publisher_v1(date '2026-09-22') r"));
const servingAfter = (await q('select generation_id from public.pokemon_market_explorer_prepared_serving_v1'))[0].generation_id;
const gensAfter = (await q('select count(*)::int c from public.pokemon_market_explorer_prepared_generations_v1'))[0].c;
log('atomicity_staging_failure', { error: bad.err, servingUnchanged: servingBefore === servingAfter, generationRowsBefore: gensBefore, generationRowsAfter: gensAfter, note: 'wrapper is one statement/transaction: candidate rows are rolled back with the failed staging' });
await db.exec("update public.pokemon_market_explorer_query_cache set constituent_count=120 where query_fingerprint='fp_era_ex'");

// ---- Privileges: anon/authenticated cannot write or read; service_role can ----
const priv = async (role, stmt) => { await db.exec(`set role ${role}`); try { await db.exec(stmt); return 'ALLOWED'; } catch (e) { return 'DENIED: ' + String(e.message).slice(0, 60); } finally { await db.exec('reset role'); } };
const ins = `insert into public.pokemon_market_explorer_prepared_constituents_v1 values ('${G2}','zz',1,'x','cards',1,date '2026-09-22','{}')`;
log('privileges', {
  anon_insert: await priv('anon', ins), authenticated_insert: await priv('authenticated', ins),
  anon_select: await priv('anon', 'select 1 from public.pokemon_market_explorer_prepared_constituents_v1 limit 1'),
  anon_v3: await priv('anon', `select public.get_pokemon_market_explorer_prepared_constituents_v3('x','${G2}',0,1)`),
  authenticated_stage: await priv('authenticated', `select public.stage_pokemon_market_explorer_prepared_constituents_v1('${G2}')`),
  service_role_select: await priv('service_role', 'select 1 from public.pokemon_market_explorer_prepared_constituents_v1 limit 1'),
  service_role_v3: await priv('service_role', `select public.get_pokemon_market_explorer_prepared_constituents_v3('x','${G2}',0,1)`),
  publisher_wrapper: await priv('market_explorer_publisher', "select public.run_market_explorer_guarded_publisher_v1(date '2026-09-22')"),
});

