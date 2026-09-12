// Rankings Product Lens Client — CSS width contract.
//
// The All Products table must not exceed the viewport width. `.productsTable`
// pairs with `width: 100%` and `table-layout: fixed` so column widths are
// strictly controlled by <col> width rules, not content size (preventing
// horizontal overflow past 1440px).

import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";

const cssPath = join(import.meta.dirname, "explore.module.css");
const css = readFileSync(cssPath, "utf8");

test("productsTable no longer forces width past 100%", () => {
  const match = css.match(/\.productsTable\s*\{([^}]*)\}/);
  assert.ok(match, "productsTable rule not found in CSS");
  const productsTableRule = match[1];
  assert.doesNotMatch(productsTableRule, /width:\s*max-content/, "productsTable should not have width: max-content");
});

test("productsTable uses table-layout: fixed to respect column widths", () => {
  const match = css.match(/\.productsTable\s*\{([^}]*)\}/);
  assert.ok(match, "productsTable rule not found in CSS");
  const productsTableRule = match[1];
  assert.match(productsTableRule, /table-layout:\s*fixed/, "productsTable should have table-layout: fixed");
});

test("productsTable width is 100%", () => {
  const match = css.match(/\.productsTable\s*\{([^}]*)\}/);
  assert.ok(match, "productsTable rule not found in CSS");
  const productsTableRule = match[1];
  const widthLine = productsTableRule.split(';').find(line => line.trim().startsWith('width:'));
  assert.ok(widthLine, "productsTable should have a width property");
  assert.match(widthLine, /width:\s*100%/, "width should be 100%");
});

// The All Products identity/format columns were deliberately oversized
// (22rem / 15rem), producing much lower density than the family-specific
// product ranking view (RipDecisionPage.jsx, `.productIdentityCell`,
// min-width: 13rem) which reuses the same `RankedProductIdentity`
// component. Narrow both columns to match that measured density.
test("colProduct width matches family view density (not the oversized 22rem)", () => {
  const match = css.match(/\.colProduct\s*\{([^}]*)\}/);
  assert.ok(match, "colProduct rule not found in CSS");
  const colProductRule = match[1];
  assert.doesNotMatch(colProductRule, /22rem/, "colProduct should no longer be 22rem");
  assert.match(colProductRule, /13rem/, "colProduct should match the family view's measured 13rem identity width");
});

test("colFormat width is narrowed from the oversized 15rem", () => {
  const match = css.match(/\.colFormat\s*\{([^}]*)\}/);
  assert.ok(match, "colFormat rule not found in CSS");
  const colFormatRule = match[1];
  assert.doesNotMatch(colFormatRule, /15rem/, "colFormat should no longer be 15rem");
  assert.match(colFormatRule, /10rem/, "colFormat should be narrowed to a conservative 10rem pending Task 11 visual check");
});

// Task 10: Units + Committed consolidation into a single "Opening Plan"
// column was scoped to run ONLY if the All Products table still overflowed
// 1440px after Tasks 8-9 narrowed .colProduct/.colFormat. A live Playwright
// measurement at a 1440x900 viewport (chromium, `/Explore` route, Products
// tab) on 2026-09-10 found the rendered `.productsTable` at 1374px wide with
// zero horizontal overflow (`document.body.scrollWidth` === 1440 ===
// `clientWidth`), because `.productsTable { width: 100%; table-layout: fixed }`
// proportionally scales every <col> to fit its container regardless of the
// summed rem values. So the consolidation was not implemented — .colUnits
// and .colCommitted remain separate columns. This test pins that decision
// so a future change doesn't silently reintroduce the merge (or drop these
// columns) without re-measuring.
test("colUnits and colCommitted remain separate (Opening Plan consolidation not needed — table already fits at 1440px)", () => {
  const unitsMatch = css.match(/\.colUnits\s*\{([^}]*)\}/);
  const committedMatch = css.match(/\.colChase,\s*\n\.colCommitted,\s*\n\.colRecover\s*\{([^}]*)\}/);
  assert.ok(unitsMatch, "colUnits rule should still exist (not consolidated into colOpeningPlan)");
  assert.match(unitsMatch[1], /4rem/, "colUnits should remain 4rem");
  assert.ok(committedMatch, "colCommitted should still be grouped with colChase/colRecover at 7rem (not consolidated)");
  assert.doesNotMatch(css, /\.colOpeningPlan/, "colOpeningPlan should not exist — measured width already fits 1440px");
});
