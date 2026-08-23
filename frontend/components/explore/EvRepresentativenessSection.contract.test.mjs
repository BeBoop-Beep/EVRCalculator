import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";

const report = fs.readFileSync(new URL("./SimulationFullReport.jsx", import.meta.url), "utf8");
const page = fs.readFileSync(new URL("./RipDecisionPage.jsx", import.meta.url), "utf8");
const styles = fs.readFileSync(new URL("./RipDecisionPage.module.css", import.meta.url), "utf8");

test("EV representativeness appears inside the existing full report before technical groups", () => {
  assert.ok(page.includes("<SimulationFullReport"));
  assert.ok(report.indexOf("How Representative Is EV?") < report.indexOf("report.groups.map"));
  assert.ok(report.includes("EV Realization by Opening Size"));
  assert.ok(report.includes("not recommendations to open that many packs"));
});

test("section retains same-run selector and accessible table/info affordance", () => {
  assert.ok(report.includes("selectEvRepresentativenessPublicV1(evRepresentativeness, calculationRunId)"));
  assert.ok(report.includes('role="table"'));
  assert.ok(report.includes("<InfoPopover"));
});

test("responsive layout prevents four-card overflow on mobile", () => {
  assert.ok(styles.includes(".evRepMetrics { display: grid; min-width: 0;"));
  assert.ok(styles.includes(".evRepMetrics { grid-template-columns: repeat(2,minmax(0,1fr)); }"));
});
