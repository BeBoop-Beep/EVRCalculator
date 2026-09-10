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
