import assert from "node:assert/strict";
import test from "node:test";
import { createRankingsSessionCache } from "./rankingsSessionCache.mjs";
import { peekFinancialHistory, planCohortPrefetch, prewarmFinancialHistory, readFinancialHistoryCached } from "./financialHistoryCache.mjs";
import { defaultFinancialHistoryRequest } from "../../components/explore/financialRipHistoryModel.mjs";

const ids = (n, type = "set") => Array.from({ length: n }, (_, i) => ({ entity_type: type, entity_id: `${type[0]}${String(i + 1).padStart(2, "0")}` }));
const DAYS = ["2026-09-28", "2026-09-29", "2026-09-30"];

function fakeFetch() {
  const calls = [];
  const impl = async (_url, init) => {
    const body = JSON.parse(init.body);
    calls.push(body);
    const rows = [];
    for (const entity of body.entities) for (const day of DAYS) {
      if (day < body.start_date || day > body.end_date) continue;
      rows.push({ entityId: entity.entity_id, entityType: entity.entity_type, marketDate: day, absoluteFinancialRipScore: 5 + Number(entity.entity_id.slice(1)) / 10, overallFinancialRipReference: 5.5, publicationId: "pub-1" });
    }
    return { ok: true, json: async () => ({ contractVersion: "v1", rows, hasMore: false, historyAvailableFrom: "2026-08-22", historyAvailableThrough: "2026-09-30" }) };
  };
  return { impl, calls };
}
const win = { startDate: "2026-09-01", endDate: "2026-09-30" };

test("identical default requests dedupe through the session cache (in flight and completed)", async () => {
  const cache = createRankingsSessionCache("user-a:2026-09-30");
  const { impl, calls } = fakeFetch();
  const [a, b] = await Promise.all([
    readFinancialHistoryCached(ids(3), { sessionCache: cache, ...win, fetchImpl: impl }),
    readFinancialHistoryCached(ids(3), { sessionCache: cache, ...win, fetchImpl: impl }),
  ]);
  assert.equal(calls.length, 1);
  assert.equal(a, b);
  await readFinancialHistoryCached(ids(3).reverse(), { sessionCache: cache, ...win, fetchImpl: impl });
  assert.equal(calls.length, 1, "entity order is normalised");
});

test("parent prewarm and the chart mount produce exactly ONE request", async () => {
  const cache = createRankingsSessionCache("user-a:2026-09-30");
  const { impl, calls } = fakeFetch();
  const cohort = { eras: [{ eraId: "e1", eraName: "Era", sets: ids(22).map((s) => ({ setId: s.entity_id, setName: s.entity_id })) }] };
  const plan = defaultFinancialHistoryRequest({ financialCohort: cohort, marketDate: "2026-09-30" });
  assert.equal(plan.entities.length, 3);
  assert.equal(plan.cohortEntities.length, 22);
  const warm = prewarmFinancialHistory(plan, { sessionCache: cache, entitled: true, authStatus: "resolved", fetchImpl: impl });
  // chart mounts while the prewarm is still in flight, using the same plan-derived key
  const mount = readFinancialHistoryCached(plan.entities, { sessionCache: cache, startDate: plan.startDate, endDate: plan.endDate, fetchImpl: impl });
  const [w, m] = await Promise.all([warm, mount]);
  assert.equal(calls.length, 1);
  assert.equal(w, m);
  assert.equal(peekFinancialHistory(plan.entities, { sessionCache: cache, startDate: plan.startDate, endDate: plan.endDate }), w);
});

test("prewarm is entitlement- and auth-gated: anonymous/base/unresolved viewers make no request", async () => {
  const cache = createRankingsSessionCache("anonymous:2026-09-30");
  const { impl, calls } = fakeFetch();
  const plan = { entities: ids(3), cohortEntities: ids(22), ...win };
  assert.equal(await prewarmFinancialHistory(plan, { sessionCache: cache, entitled: false, authStatus: "resolved", fetchImpl: impl }), null);
  assert.equal(await prewarmFinancialHistory(plan, { sessionCache: cache, entitled: true, authStatus: "resolving", fetchImpl: impl }), null);
  assert.equal(await prewarmFinancialHistory(null, { sessionCache: cache, entitled: true, authStatus: "resolved", fetchImpl: impl }), null);
  assert.equal(await prewarmFinancialHistory(plan, { sessionCache: null, entitled: true, authStatus: "resolved", fetchImpl: impl }), null);
  assert.equal(calls.length, 0);
});

test("the 22-Set idle prefetch is entitlement-gated, save-data-aware, bounded and one request", async () => {
  const plan = { entities: ids(3), cohortEntities: ids(22), ...win };
  assert.equal(planCohortPrefetch(plan, { entitled: false }), null);
  assert.equal(planCohortPrefetch(plan, { entitled: true, saveData: true }), null);
  assert.equal(planCohortPrefetch({ ...plan, cohortEntities: ids(23) }, { entitled: true }), null, "never beyond the 22-entity API ceiling");
  assert.equal(planCohortPrefetch({ ...plan, cohortEntities: ids(3) }, { entitled: true }), null, "nothing to add");
  const ok = planCohortPrefetch(plan, { entitled: true });
  assert.equal(ok.entities.length, 22);
  assert.deepEqual([ok.startDate, ok.endDate], [win.startDate, win.endDate]);
  const cache = createRankingsSessionCache("user-a:2026-09-30");
  const { impl, calls } = fakeFetch();
  await readFinancialHistoryCached(ok.entities, { sessionCache: cache, ...win, fetchImpl: impl });
  assert.equal(calls.length, 1);
  assert.equal(calls[0].entities.length, 22);
});

test("a cached 22-Set superset serves any selected subset locally, with identical rows and Overall", async () => {
  const cache = createRankingsSessionCache("user-a:2026-09-30");
  const { impl, calls } = fakeFetch();
  const full = await readFinancialHistoryCached(ids(22), { sessionCache: cache, ...win, fetchImpl: impl });
  const subset = [ids(22)[4], ids(22)[9], ids(22)[15]];
  const local = await readFinancialHistoryCached(subset, { sessionCache: cache, ...win, fetchImpl: impl });
  assert.equal(calls.length, 1, "no refetch when the selection narrows");
  assert.deepEqual([...new Set(local.rows.map((r) => r.entityId))].sort(), subset.map((e) => e.entity_id).sort());
  const original = full.rows.filter((r) => subset.some((e) => e.entity_id === r.entityId));
  assert.deepEqual(local.rows, original, "rows are the exact cached rows - nothing fabricated or recomputed");
  assert.ok(local.rows.every((r) => r.overallFinancialRipReference === 5.5));
  assert.equal(local.historyAvailableFrom, full.historyAvailableFrom);
  // an entity outside the cached superset takes the normal bounded fetch
  const outside = await readFinancialHistoryCached([...subset, { entity_type: "set", entity_id: "s99" }], { sessionCache: cache, ...win, fetchImpl: impl });
  assert.equal(calls.length, 2);
  assert.ok(outside.rows.some((r) => r.entityId === "s99"));
});

test("a cached range can never satisfy another range", async () => {
  const cache = createRankingsSessionCache("user-a:2026-09-30");
  const { impl, calls } = fakeFetch();
  await readFinancialHistoryCached(ids(22), { sessionCache: cache, ...win, fetchImpl: impl });
  const other = { startDate: "2026-07-01", endDate: "2026-09-30" };
  assert.equal(peekFinancialHistory(ids(3), { sessionCache: cache, ...other }), undefined);
  await readFinancialHistoryCached(ids(3), { sessionCache: cache, ...other, fetchImpl: impl });
  assert.equal(calls.length, 2);
  // warm return to a loaded range is a cache hit
  await readFinancialHistoryCached(ids(3), { sessionCache: cache, ...other, fetchImpl: impl });
  await readFinancialHistoryCached(ids(3), { sessionCache: cache, ...win, fetchImpl: impl });
  assert.equal(calls.length, 2);
});

test("a Set cache can never satisfy Era mode (and Eras are never built from Sets)", async () => {
  const cache = createRankingsSessionCache("user-a:2026-09-30");
  const { impl, calls } = fakeFetch();
  await readFinancialHistoryCached(ids(22), { sessionCache: cache, ...win, fetchImpl: impl });
  const eras = ids(2, "era");
  assert.equal(peekFinancialHistory(eras, { sessionCache: cache, ...win }), undefined);
  const result = await readFinancialHistoryCached(eras, { sessionCache: cache, ...win, fetchImpl: impl });
  assert.equal(calls.length, 2);
  assert.deepEqual(calls[1].entities.map((e) => e.entity_type), ["era", "era"]);
  assert.ok(result.rows.every((r) => r.entityType === "era"));
  await assert.rejects(() => readFinancialHistoryCached([...ids(1), ...ids(1, "era")], { sessionCache: cache, ...win, fetchImpl: impl }), /single type/);
});

test("a different access/publication identity never reuses paid history", async () => {
  const { impl, calls } = fakeFetch();
  const userA = createRankingsSessionCache("user-a:2026-09-30");
  const userB = createRankingsSessionCache("user-b:2026-09-30");
  const nextPublication = createRankingsSessionCache("user-a:2026-10-01");
  const anonymous = createRankingsSessionCache("anonymous:2026-09-30");
  await readFinancialHistoryCached(ids(22), { sessionCache: userA, ...win, fetchImpl: impl });
  for (const other of [userB, nextPublication, anonymous]) assert.equal(peekFinancialHistory(ids(3), { sessionCache: other, ...win }), undefined);
  await readFinancialHistoryCached(ids(3), { sessionCache: userB, ...win, fetchImpl: impl });
  assert.equal(calls.length, 2);
});

test("an older range response lands in its own entry and cannot overwrite the newest range", async () => {
  const cache = createRankingsSessionCache("user-a:2026-09-30");
  const slow = [];
  const impl = (_url, init) => new Promise((resolve) => {
    const body = JSON.parse(init.body);
    slow.push(() => resolve({ ok: true, json: async () => ({ rows: [{ entityId: "s01", marketDate: body.end_date, tag: body.start_date, absoluteFinancialRipScore: 5, overallFinancialRipReference: 5 }], hasMore: false }) }));
  });
  const r30 = readFinancialHistoryCached(ids(1), { sessionCache: cache, startDate: "2026-09-01", endDate: "2026-09-30", fetchImpl: impl });
  const r3m = readFinancialHistoryCached(ids(1), { sessionCache: cache, startDate: "2026-07-01", endDate: "2026-09-30", fetchImpl: impl });
  await new Promise((resolve) => setTimeout(resolve, 5));
  slow[1](); const newest = await r3m;      // newest range resolves first
  slow[0](); const older = await r30;        // stale one resolves later
  assert.equal(newest.rows[0].tag, "2026-07-01");
  assert.equal(older.rows[0].tag, "2026-09-01");
  assert.equal(peekFinancialHistory(ids(1), { sessionCache: cache, startDate: "2026-07-01", endDate: "2026-09-30" }).rows[0].tag, "2026-07-01");
});

test("a failed read is not cached and does not retry in a loop", async () => {
  const cache = createRankingsSessionCache("user-a:2026-09-30");
  let attempts = 0;
  const impl = async () => { attempts += 1; return { ok: false, status: 500, json: async () => ({ message: "boom" }) }; };
  await assert.rejects(() => readFinancialHistoryCached(ids(1), { sessionCache: cache, ...win, fetchImpl: impl }));
  assert.equal(attempts, 1);
  assert.equal(peekFinancialHistory(ids(1), { sessionCache: cache, ...win }), undefined);
});
