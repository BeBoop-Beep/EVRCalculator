import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const blockSource = fs.readFileSync(new URL("./block/route.js", import.meta.url), "utf8");
const submitSource = fs.readFileSync(new URL("./submit/route.js", import.meta.url), "utf8");

test("Treatment preference proxies are no-store and thin", () => {
  for (const source of [blockSource, submitSource]) {
    assert.match(source, /"Cache-Control": "private, no-store"/);
    assert.match(source, /cache: "no-store"/);
    assert.doesNotMatch(source, /SUPABASE_SERVICE_ROLE_KEY|NEXT_PUBLIC_SUPABASE/);
    assert.doesNotMatch(source, /Special Illustration Rare|Ultra Rare|Double Rare/);
  }
  assert.match(blockSource, /research\/treatment-preference-v1\/block/);
  assert.match(submitSource, /research\/treatment-preference-v1\/submit/);
});
