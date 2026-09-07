import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const card = fs.readFileSync(new URL("./EvRealizationCard.jsx", import.meta.url), "utf8");
const report = fs.readFileSync(new URL("./SimulationFullReport.jsx", import.meta.url), "utf8");

test("EV Realization has entitled, unavailable, and numberless locked states", () => {
  assert.match(card, /data-ev-realization-state/);
  assert.match(card, /available \? "available" : entitled \? "unavailable" : "locked"/);
  assert.match(card, /80% of modeled openers reach at least 80% of long-run EV/);
  assert.match(card, /data-ev-realization-timeline/);
  const locked = card.slice(card.indexOf("data-ev-realization-lock"));
  assert.doesNotMatch(locked, /horizon\.packCount|targetEvRatio|openerProbability/);
});

test("Set report uses its same-run selector and adds no data request", () => {
  assert.match(report, /selectEvRepresentativenessPublicV1/);
  assert.match(report, /horizon=\{evRep\?\.realizationHorizon \?\? null\}/);
  assert.match(report, /entitled=\{canViewAdvanced\}/);
  assert.doesNotMatch(card, /fetch\(|axios|useEffect/);
});
