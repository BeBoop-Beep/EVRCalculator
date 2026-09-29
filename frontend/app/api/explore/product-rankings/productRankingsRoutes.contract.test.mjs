import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

for (const view of ["scores", "economics"]) {
  test(`${view} proxy preserves caller identity and private no-store semantics`, () => {
    const source = fs.readFileSync(new URL(`./${view}/route.js`, import.meta.url), "utf8");
    for (const token of ['request.headers.get("authorization")', 'request.headers.get("cookie")', 'cache: "no-store"', '"Cache-Control": "private, no-store"', 'Vary: "Cookie, Authorization"', "status: response.status"]) assert.ok(source.includes(token), token);
    assert.ok(source.includes(`/explore/product-rankings/${view}`));
    assert.doesNotMatch(source, /index_plan|require.*Plan|entitlement/i);
  });
}
