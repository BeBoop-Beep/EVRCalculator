import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const source = fs.readFileSync(new URL("./route.js", import.meta.url), "utf8");

test("slim card-detail proxy forwards only card identity and optional variant", () => {
  assert.match(source, /\/cards\/\$\{encodeURIComponent\(cardId\)\}/);
  assert.match(source, /variant_id/);
  assert.match(source, /cache: "no-store"/);
  assert.doesNotMatch(source, /chase-economics|\/cards\/page|\/cards`/);
});
