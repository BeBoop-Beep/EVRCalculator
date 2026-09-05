// Market-Based Opening Quality breakdown — contract tests (Phase 5/10).
//
// This component transitively imports FinancialRipV3Breakdown.jsx, which
// depends on the `@/hooks/useMediaQuery` Next path alias — the same reason
// `FinancialRipV3Breakdown.contract.test.mjs` asserts against the rendered
// JSX SOURCE rather than importing/rendering the component tree outside a
// Next build (that file's own header comment documents this). This test
// follows the identical, already-established pattern for this file family.

import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const readSource = (name) => fs.readFileSync(path.join(here, name), "utf8").replace(/\r\n/g, "\n");

const componentSource = readSource("MarketBasedOpeningQualityBreakdown.jsx");

test("A/C: renders the Market-Based label sourced from the shared selector, and states it is explanatory-only", () => {
  assert.match(componentSource, /MARKET_BASED_LABEL/);
  assert.match(componentSource, /Explanatory grouping only — not an independent third pillar and never persisted as its own score/);
});

test("D: FULL mode renders Chase Accessibility's primary metric separately from a labeled diagnostics panel", () => {
  assert.match(componentSource, /ChaseAccessibilityFullPanel/);
  assert.match(componentSource, /Diagnostics — not part of the Chase Accessibility score/);
  assert.match(componentSource, /Chase depth &amp;? ?concentration|Chase depth/i);
});

test("D: rank is never rendered as a real value unless the selector supplies one — no fabricated rank literal", () => {
  assert.doesNotMatch(componentSource, /Rank #\{?["'`]?\d/);
  assert.match(componentSource, /Cohort rank not yet available/);
  assert.match(componentSource, /chase\.rank !== null/);
});

test("E: Product Chase terminology never appears in this Chase Accessibility surface", () => {
  for (const forbidden of ["Chase Access at Budget", "O_budget", "Product Chase Intelligence"]) {
    assert.equal(componentSource.includes(forbidden), false, `forbidden Product Chase term "${forbidden}" found`);
  }
});

test("B/10-G: no weight-percentage disclosure and no frontend scoring arithmetic in this component's source", () => {
  for (const token of ["86%", "4%\"", "10%\"", "90%\"", "95.56", "4.44"]) {
    assert.equal(componentSource.includes(token), false, `forbidden weight token "${token}" found in component source`);
  }
  assert.equal(/0\.86\s*\*/.test(componentSource), false);
  assert.equal(/A_raw\s*\/\s*\(A_raw\s*\+/.test(componentSource), false);
  assert.equal(/100\s*\*\s*A(_raw)?\s*\/\s*\(A(_raw)?\s*\+\s*0?\.002\)/.test(componentSource), false);
});

test("no fabricated six-Chase-factor mirror: exactly one scored Chase metric plus documented real diagnostics", () => {
  assert.match(componentSource, /displayAccessibility/);
  assert.match(componentSource, /Value Concentration/);
  assert.match(componentSource, /Not yet published/);
  // No invented "Chase Factor 1..6" naming pattern.
  assert.doesNotMatch(componentSource, /Chase Factor \d/);
});

test("reuses FinancialRipV3Breakdown verbatim for the FULL Financial child rather than re-implementing it", () => {
  assert.match(componentSource, /import FinancialRipV3Breakdown from "\.\/FinancialRipV3Breakdown\.jsx"/);
  assert.match(componentSource, /<FinancialRipV3Breakdown canonical=\{canonical\}/);
});

test("unavailable Chase Accessibility path renders the backend status reason, never a hardcoded fallback number", () => {
  assert.doesNotMatch(componentSource, />0\.21%</);
  assert.match(componentSource, /statusReason \|\| "Chase Accessibility is not currently available for this set\."/);
});
