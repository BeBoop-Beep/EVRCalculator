import test from "node:test";
import assert from "node:assert/strict";
import {
  appendConstituentPage,
  buildConstituentPageRequest,
  CONSTITUENT_PAGE_MAX_LIMIT,
  parseConstituentPageResponse,
} from "./marketExplorerConstituentPaging.mjs";

test("the page request carries the spec verbatim plus bounded limit/afterRank", () => {
  const spec = { asset: "cards", mode: "all", eraIds: [], setIds: [] };
  const request = buildConstituentPageRequest(spec, { limit: 40, afterRank: 100 });
  assert.equal(request.asset, "cards");
  assert.equal(request.limit, 40);
  assert.equal(request.afterRank, 100);
});

test("limit is clamped to the backend's hard cap, never sent over it", () => {
  const request = buildConstituentPageRequest({ asset: "cards" }, { limit: 5000 });
  assert.equal(request.limit, CONSTITUENT_PAGE_MAX_LIMIT);
});

test("a non-positive or missing afterRank normalizes to 0, the roster's start", () => {
  assert.equal(buildConstituentPageRequest({ asset: "cards" }, { afterRank: -5 }).afterRank, 0);
  assert.equal(buildConstituentPageRequest({ asset: "cards" }, {}).afterRank, 0);
});

test("a response is unwrapped from its snake_case envelope into the frontend's shape", () => {
  const parsed = parseConstituentPageResponse({
    items: [{ rank: 1 }, { rank: 2 }],
    next_cursor: 2,
    total_constituent_count: 33955,
    as_of: "2026-09-03",
  });
  assert.deepEqual(parsed, {
    rows: [{ rank: 1 }, { rank: 2 }],
    nextCursor: 2,
    totalCount: 33955,
    asOf: "2026-09-03",
  });
});

test("next_cursor null means the roster is exhausted, never inferred from row count", () => {
  const parsed = parseConstituentPageResponse({
    items: [{ rank: 1 }], next_cursor: null, total_constituent_count: 1, as_of: "2026-09-03",
  });
  assert.equal(parsed.nextCursor, null);
});

test("appendConstituentPage adds new rows and de-duplicates by rank", () => {
  const existing = [{ rank: 1 }, { rank: 2 }];
  const page = { rows: [{ rank: 2 }, { rank: 3 }], nextCursor: null, totalCount: 3, asOf: null };
  const merged = appendConstituentPage(existing, page);
  assert.deepEqual(merged.map((row) => row.rank), [1, 2, 3]);
});

test("a missing items array never throws — it parses to an empty page", () => {
  const parsed = parseConstituentPageResponse({});
  assert.deepEqual(parsed.rows, []);
  assert.equal(parsed.totalCount, 0);
  assert.equal(parsed.nextCursor, null);
});
