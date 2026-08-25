import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";

const read = (path) => fs.readFileSync(new URL(path, import.meta.url), "utf8");
const button = read("./ReturnToTopButton.jsx");
const market = read("../explore/SetMarketExplorer.jsx");
const setPage = read("../explore/RipStatisticsPageClient.jsx");

test("one shared return-to-top primitive owns the canonical visual", () => {
  assert.match(market, /import ReturnToTopButton from "@\/components\/ui\/ReturnToTopButton"/);
  assert.match(setPage, /import ReturnToTopButton from "@\/components\/ui\/ReturnToTopButton"/);
  assert.equal((button.match(/M10 4\.25/g) || []).length, 1);
  assert.doesNotMatch(market, /M10 4\.25/);
  assert.doesNotMatch(setPage, /M10 4\.25/);
});

test("standard mobile placement is viewport-centered above the safe-area-aware bottom nav", () => {
  assert.match(button, /left-1\/2/);
  assert.match(button, /-translate-x-1\/2/);
  assert.match(button, /5\.25rem\+env\(safe-area-inset-bottom\)\+0\.75rem/);
  assert.doesNotMatch(button, /right-4/);
  assert.match(button, /aria-label=\{ariaLabel\}/);
  assert.match(market, /ariaLabel="Return to top of Set Market"/);
});
