import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

// Source-string structural checks for the Products table layout cleanup
// (Rankings -> Products). Mirrors the pattern used by
// ThreePillarLayout.contract.test.mjs / pokemonSetRouteFailureSemantics
// contract tests: these assert on the JSX/CSS text itself, not on rendered
// DOM, because this repo does not run a component test harness for this
// file.

const read = (url) => fs.readFileSync(new URL(url, import.meta.url), "utf8");
const jsx = read("./RankingsProductLensClient.jsx");
const css = read("./explore.module.css");

test("desktop table declares an explicit colgroup width contract, not per-cell hacks", () => {
  assert.match(jsx, /<colgroup>/);
  for (const col of [
    "colRank", "colProduct", "colOverall", "colTier", "colFinancial",
    "colChase", "colCollector", "colPrice", "colUnits", "colCommitted",
    "colEv", "colRecover", "colFormat",
  ]) {
    assert.ok(jsx.includes(`styles.${col}`), `expected <col className={styles.${col}} /> in RankingsProductLensClient.jsx`);
    assert.match(css, new RegExp(`\\.${col}\\s*[,{]`));
  }
  // Rank stays narrow, Product/Set gets one of the largest allocations.
  const rankWidth = /\.colRank\s*{\s*width:\s*([\d.]+)rem/.exec(css)?.[1];
  const productWidth = /\.colProduct\s*{\s*width:\s*([\d.]+)rem/.exec(css)?.[1];
  assert.ok(rankWidth && productWidth, "colRank/colProduct widths must be declared in rem");
  assert.ok(Number(productWidth) > Number(rankWidth) * 4, "Product/Set column must be materially wider than Rank");
});

test("Units and Committed are separate desktop <th> columns, not embedded in Product/Set identity", () => {
  assert.match(jsx, /<th scope="col">Units<\/th>/);
  assert.match(jsx, /<th scope="col">Committed<\/th>/);
});

test("desktop Product/Set identity cell does not render Strategy (quantity/committed)", () => {
  const desktopSection = jsx.slice(jsx.indexOf('className="hidden overflow-x-auto md:block"'), jsx.indexOf('className="space-y-2 p-3 md:hidden"'));
  assert.doesNotMatch(desktopSection, /<Strategy/);
});

test("desktop Units/Committed cells read row.quantity and row.actualCommittedCapital, updating with the selected budget", () => {
  assert.match(jsx, /const quantity = numeric\(row\?\.quantity\)/);
  assert.match(jsx, /const committed = numeric\(row\?\.actualCommittedCapital\)/);
});

test("mobile card layout still surfaces quantity/committed via Strategy", () => {
  const mobileSection = jsx.slice(jsx.indexOf('className="space-y-2 p-3 md:hidden"'));
  assert.match(mobileSection, /<Strategy/);
});

test("Format Strength wraps instead of clipping and no longer uses a fixed min-w-[10rem] cap", () => {
  assert.doesNotMatch(jsx, /min-w-\[10rem\]/);
  assert.match(jsx, /whitespace-normal break-words/);
});

test("desktop table fits the viewport via colgroup-driven fixed layout rather than horizontal overflow", () => {
  // Tasks 8/9 intentionally replaced the earlier `width: max-content` /
  // horizontal-scroll approach: the table now uses `width: 100%` with
  // `table-layout: fixed` so column widths (from colgroup <col> widths) are
  // proportionally scaled to fit the viewport instead of overflowing it.
  assert.match(jsx, /styles\.table\}\s*\$\{styles\.productsTable\}/);
  assert.match(css, /\.productsTable\s*{[^}]*width:\s*100%/);
  assert.match(css, /\.productsTable\s*{[^}]*table-layout:\s*fixed/);
  assert.doesNotMatch(css, /\.productsTable\s*{[^}]*width:\s*max-content/);
});
