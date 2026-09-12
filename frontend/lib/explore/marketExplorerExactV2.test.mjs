import test from "node:test";
import assert from "node:assert/strict";
import { normalizeQuerySpec, buildQueryKey, MARKET_EXPLORER_EXPLICIT_QUERY_CONTRACT_VERSION_V2 } from "./marketExplorerQuery.mjs";

test("qualified exact V2 is mixed, canonical, deduped, and order independent", () => {
  const a = normalizeQuerySpec({ membershipMode: "explicit", instruments: [{ asset: "sealed", instrumentId: "b" }, { asset: "cards", instrumentId: "a" }, { asset: "cards", instrumentId: "a" }] });
  const b = normalizeQuerySpec({ membershipMode: "explicit", instruments: [{ asset: "cards", instrumentId: "a" }, { asset: "sealed", instrumentId: "b" }] });
  assert.equal(a.contractVersion, MARKET_EXPLORER_EXPLICIT_QUERY_CONTRACT_VERSION_V2);
  assert.equal(a.asset, "mixed");
  assert.deepEqual(a.instruments, [{ asset: "cards", instrumentId: "a" }, { asset: "sealed", instrumentId: "b" }]);
  assert.equal(buildQueryKey(a), buildQueryKey(b));
});

test("asset qualification keeps identical raw ids distinct and drops Builder axes", () => {
  const spec = normalizeQuerySpec({ membershipMode: "explicit", instruments: [{ asset: "cards", instrumentId: "same" }, { asset: "sealed", instrumentId: "same" }], eraIds: ["era"], setIds: ["set"], mode: "chase", topN: 10 });
  assert.equal(spec.instruments.length, 2);
  assert.deepEqual(spec.eraIds, []); assert.deepEqual(spec.setIds, []);
  assert.equal(spec.mode, "all"); assert.equal(spec.topN, null);
});

test("qualified exact V2 enforces 1 through 25", () => {
  assert.throws(() => normalizeQuerySpec({ membershipMode: "explicit", instruments: [] }), RangeError);
  assert.equal(normalizeQuerySpec({ membershipMode: "explicit", instruments: Array.from({ length: 25 }, (_, i) => ({ asset: "cards", instrumentId: String(i) })) }).instruments.length, 25);
  assert.throws(() => normalizeQuerySpec({ membershipMode: "explicit", instruments: Array.from({ length: 26 }, (_, i) => ({ asset: "cards", instrumentId: String(i) })) }), RangeError);
});
