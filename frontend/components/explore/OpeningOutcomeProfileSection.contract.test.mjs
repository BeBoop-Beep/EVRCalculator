import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const component = fs.readFileSync(new URL("./SimulationFullReport.jsx", import.meta.url), "utf8");
const css = fs.readFileSync(new URL("./RipDecisionPage.module.css", import.meta.url), "utf8");

test("outcome breakdown follows the existing distribution and precedes EV representativeness", () => {
  assert.ok(component.indexOf("Outcome Breakdown") < component.indexOf("How Representative Is EV?"));
  assert.ok(component.includes("selectOpeningOutcomeProfileV1(openingOutcomeProfile, calculationRunId)"));
});
test("main copy uses gross returned value language and avoids profit claims", () => {
  const section = component.slice(component.indexOf("Outcome Breakdown"), component.indexOf("How Representative Is EV?"));
  assert.ok(section.includes("gross modeled card market value"));
  assert.ok(!section.toLowerCase().includes("profit"));
});
test("mobile profile grids are bounded at two columns", () => {
  assert.match(css, /\.outcomeProfileRows,\.outcomeProfileCallouts\s*\{\s*grid-template-columns:\s*repeat\(2,minmax\(0,1fr\)\)/);
});
