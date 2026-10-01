import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const lazy = fs.readFileSync(new URL("./RankingsLazyClient.jsx", import.meta.url), "utf8");
const products = fs.readFileSync(new URL("./RankingsProductLensClient.jsx", import.meta.url), "utf8");

test("the legacy all-lenses Product client remains retired", () => {
  assert.doesNotMatch(lazy, /import\("\.\/ProductFamilyRankingsClient"\)/);
  assert.match(lazy, /import\("\.\/RankingsProductLensClient"\)/);
  assert.match(products, /readProductRankings\(view, \{ sessionCache, force, params \}\)/);
  assert.match(products, /page_size: PAGE_SIZE/);
});
