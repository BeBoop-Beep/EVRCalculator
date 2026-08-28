import assert from "node:assert/strict";
import test from "node:test";
import { createRouteDirectoryLkg } from "./pokemonSetRouteDirectoryLkg.mjs";

const payload = (id = "a") => ({ targets: [{ target_id: id, canonical_key: id }, { target_id: `${id}2`, canonical_key: `${id}2` }], default_target: { target_id: id, canonical_key: id }, meta: { source: "rpc", readAt: "original" } });

test("canonical LKG preserves order, identity and default while marking fallback stale", () => {
  const lkg = createRouteDirectoryLkg(); const original = payload();
  assert.equal(lkg.remember(150, original), true);
  original.targets.reverse();
  const fallback = lkg.fallback(150, "now");
  assert.deepEqual(fallback.targets.map((x) => x.target_id), ["a", "a2"]);
  assert.equal(fallback.default_target.target_id, "a");
  assert.deepEqual(fallback.meta, { source: "rpc", readAt: "original", stale: true, fallback: true, fallbackReason: "route_directory_transport_failure", fallbackAt: "now" });
  fallback.targets.length = 0;
  assert.equal(lkg.fallback(150).targets.length, 2);
});

test("malformed responses are rejected and cache is bounded to four limits", () => {
  const lkg = createRouteDirectoryLkg();
  assert.equal(lkg.remember(1, { targets: [] }), false);
  for (let limit = 1; limit <= 5; limit += 1) lkg.remember(limit, payload(String(limit)));
  assert.equal(lkg.entries.size, 4);
  assert.equal(lkg.fallback(1), null);
  assert.equal(lkg.fallback(5).default_target.target_id, "5");
});
