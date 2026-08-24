import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const component = fs.readFileSync(new URL("./SimulationFullReport.jsx", import.meta.url), "utf8");
const css = fs.readFileSync(new URL("./RipDecisionPage.module.css", import.meta.url), "utf8");

test("outcome interpretation precedes EV representativeness and keeps the V1 selector", () => {
  assert.ok(component.indexOf("What Happens When You Open a Pack?") < component.indexOf("How Closely Does EV Match Real Openings?"));
  assert.ok(component.includes("selectOpeningOutcomeProfileV1(openingOutcomeProfile, calculationRunId)"));
});
test("first glance uses out-of-100 language and avoids profit claims", () => {
  const section = component.slice(component.indexOf("What Happens When You Open a Pack?"), component.indexOf("How Closely Does EV Match Real Openings?"));
  assert.ok(section.includes("out of 100 modeled packs return less than half the pack price"));
  assert.ok(!section.toLowerCase().includes("profit"));
});
test("primary bar is exact probability mass with a labeled break-even boundary", () => {
  assert.ok(component.includes("flexGrow: r.probability"));
  assert.ok(component.includes("flexBasis: 0"));
  assert.ok(!component.includes("Math.max(r.probability"));
  assert.ok(!component.includes("minWidth"));
  assert.ok(component.includes(">PACK COST<"));
  assert.ok(component.includes("index === 1 ? <b>PACK COST</b>"));
  assert.ok(!component.includes("outcome.groups[0].probability + outcome.groups[1].probability"));
  assert.ok(component.includes('role="img"'));
  const barRule = css.match(/\.outcomeProfileBar\s*\{([^}]*)\}/)?.[1] || "";
  const segmentRule = css.match(/\.outcomeProfileBar span\s*\{([^}]*)\}/)?.[1] || "";
  assert.ok(!/\bgap\s*:/.test(barRule));
  assert.ok(!/min-width\s*:\s*[1-9]/.test(segmentRule));
});
test("exact buckets remain under native progressive disclosure", () => {
  assert.ok(component.includes("<details"));
  assert.ok(component.includes("View full outcome breakdown"));
  assert.ok(component.includes("outcome.details.map"));
  assert.match(css, /\.outcomeProfileRows,\.outcomeProfileCallouts\s*\{\s*grid-template-columns:\s*1fr/);
});
