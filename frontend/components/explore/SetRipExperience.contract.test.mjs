import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";

const page = fs.readFileSync(new URL("./RipDecisionPage.jsx", import.meta.url), "utf8");
const ev = fs.readFileSync(new URL("./simulation-evidence/EvRepresentativenessSection.jsx", import.meta.url), "utf8");
const chart = fs.readFileSync(new URL("./RipDistributionChart.jsx", import.meta.url), "utf8");

test("set RIP page follows the five-section consumer flow", () => {
  const sections = ["opening-snapshot", "compare-products", "chase-summary", "simulation-evidence", "deep-dive"];
  const positions = sections.map((section) => page.indexOf(`data-rip-section=\"${section}\"`));
  assert.ok(positions.every((position) => position >= 0));
  assert.deepEqual([...positions].sort((a, b) => a - b), positions);
  assert.equal(page.includes('data-rip-section="why-it-ranks"'), false);
  assert.equal(page.includes("What Makes Up ${setName"), false);
});

test("Basic facts remain public while recommendation and advanced research are gated", () => {
  assert.ok(page.includes("Pack Price"));
  assert.ok(page.includes("Typical Opening"));
  assert.ok(page.includes("Expected Value"));
  assert.ok(page.includes("Chance to Recover Cost"));
  assert.ok(page.includes("canViewProductRipIntelligence ? <article data-rip-section=\"hero-recommendation\""));
  assert.ok(page.includes('data-index-plus-teaser="best-way-to-open"'));
  assert.ok(page.includes("canViewAdvanced={canViewProductRipIntelligence}"));
});

test("EV probability, reliability and convergence terminology is unambiguous", () => {
  assert.ok(ev.includes("Chance to Reach at Least 80% of EV"));
  assert.ok(ev.includes("of modeled 36-pack runs average at least 80% of long-run EV"));
  assert.ok(ev.includes("Reach 80% of EV Reliably"));
  assert.ok(ev.includes("Converge Near EV"));
  assert.ok(chart.includes("Chance of Returning At Least This Much"));
});

