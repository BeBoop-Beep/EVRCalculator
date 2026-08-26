import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const directory = path.dirname(fileURLToPath(import.meta.url));
const component = fs.readFileSync(
  path.join(directory, "SimulationFullReport.jsx"),
  "utf8",
);
const selector = fs.readFileSync(
  path.join(directory, "simulationFullReportSelector.mjs"),
  "utf8",
);
const css = fs.readFileSync(
  path.join(directory, "RipDecisionPage.module.css"),
  "utf8",
);

test("full report is one accessible disclosure collapsed by default", () => {
  assert.match(component, /useState\(false\)/);
  assert.match(component, /type="button"/);
  assert.match(component, /aria-expanded=\{open\}/);
  assert.match(component, /aria-controls=\{panelId\}/);
  assert.match(component, /onClick=\{\(\) => setOpen/);
  assert.ok(component.includes("{open ? ("));
  assert.ok(component.includes("<div id={panelId}"));
});

test("selector is an allowlist with no simulation or scoring machinery", () => {
  for (const forbidden of [
    "Math.random",
    "histogram",
    "distributionBins",
    "thresholdBins",
    "weight *",
    "publicScore",
    "absoluteScore",
  ])
    assert.equal(selector.includes(forbidden), false);
  for (const rawName of ["p95ThresholdValue", "randomSeed", "hiddenAnchors"])
    assert.equal(component.includes(rawName), false);
});

test("mobile report stacks without a horizontal table", () => {
  assert.match(
    css,
    /\.fullReportGroups \{ grid-template-columns: minmax\(0,1fr\); \}/,
  );
  assert.equal(component.includes("<table"), false);
  assert.equal(css.includes("overflow-x: auto"), false);
});

test("primary report explains one-pack outcomes and the conceptual EV gap without convergence research", () => {
  assert.match(component, /OpeningOutcomeProfileSection/);
  assert.match(
    component,
    /Why Is Expected Value Higher Than a Typical Opening\?/,
  );
  assert.match(component, /Typical Opening/);
  assert.match(component, /Expected Value/);
  assert.match(component, /data-ev-gap-comparison/);
  assert.match(component, /row\.value \/ scaleMax/);
  assert.match(component, /data-series=\{row\.key\}/);
  assert.equal(component.includes("evConceptCards"), false);
  assert.match(css, /i\[data-series="typical"\]/);
  assert.match(css, /i\[data-series="expected"\]/);
  assert.equal(component.includes("Reach 80% of EV Reliably"), false);
  assert.equal(component.includes("Converge Near EV"), false);
  assert.equal(component.includes("Chance to Reach at Least 80% of EV"), false);
  assert.equal(component.includes("EvRepresentativenessSection"), false);
});
