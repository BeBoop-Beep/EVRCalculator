import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";

const report = fs.readFileSync(new URL("./SimulationFullReport.jsx", import.meta.url), "utf8");
const page = fs.readFileSync(new URL("./RipDecisionPage.jsx", import.meta.url), "utf8");
const styles = fs.readFileSync(new URL("./RipDecisionPage.module.css", import.meta.url), "utf8");

test("EV representativeness appears inside the existing full report before technical groups", () => {
  assert.ok(page.includes("<SimulationFullReport"));
  assert.ok(report.indexOf("How Closely Does EV Match Real Openings?") < report.indexOf("report.groups.map"));
  assert.ok(report.includes("Typical pack (P50)"));
  assert.ok(report.includes("Long-run EV"));
  assert.ok(report.includes("not opening recommendations"));
});

test("section retains same-run selector and accessible table/info affordance", () => {
  assert.ok(report.includes("selectEvRepresentativenessPublicV1(evRepresentativeness, calculationRunId)"));
  assert.ok(report.includes('role="table"'));
  assert.ok(report.includes("<InfoPopover"));
});

test("shared comparison scale and milestone progression remain responsive", () => {
  assert.ok(report.includes("value / scale * 100"));
  assert.ok(report.includes("36 packs"));
  assert.ok(report.includes("Not confirmed"));
  assert.ok(report.includes("Explore other pack counts"));
  assert.ok(report.includes("80% of modeled openers average at least 80% of EV."));
  assert.ok(report.includes("80% of modeled openers finish within ±20% of EV."));
  assert.ok(styles.includes(".evMilestones { grid-template-columns: 1fr; }"));
});
