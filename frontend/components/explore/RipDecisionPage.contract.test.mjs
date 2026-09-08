import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";
import { buildRipDecisionModel } from "./ripDecisionModel.mjs";

const source = fs.readFileSync(new URL("./RipDecisionPage.jsx", import.meta.url), "utf8");
const css = fs.readFileSync(new URL("./RipDecisionPage.module.css", import.meta.url), "utf8");
const chase = { value: 0.00079, percent: 0.079, modelScore: 28.33, publicScore: 64.2,
  setRank: 21, setCohortSize: 22, cohortId: "cohort-fixture", status: "ready" };
const canonical = { overall: { publicScore: 91 }, financial: { publicScore: 82 },
  collector: { publicScore: 77 }, chaseAccessibility: chase };

test("approved hierarchy places Overall above three peer pillar cards", () => {
  const overall = source.indexOf("styles.overallScoreRow");
  const peers = source.indexOf("styles.pillarCardRow");
  const peerSource = source.slice(peers, source.indexOf("styles.compactScoreTakeaway", peers));
  assert.ok(overall >= 0 && overall < peers);
  assert.ok(peerSource.indexOf("metrics.financial") < peerSource.indexOf("model.chaseAccessibility"));
  assert.ok(peerSource.indexOf("model.chaseAccessibility") < peerSource.indexOf("metrics.collector"));
  assert.match(source, /styles\.pillarCardRow/);
  assert.match(css, /grid-template-columns:\s*repeat\(3/);
});

test("Financial, Chase, and Collector have separate breakdown destinations", () => {
  for (const id of ["set-detail-financial-rip", "set-detail-chase-accessibility", "set-detail-collector-appeal"])
    assert.match(source, new RegExp(`id="${id}"`));
  assert.match(source, /FinancialRipV3Breakdown/);
  assert.match(source, /CollectorAppealBreakdown/);
});

test("Chase uses only backend publicScore for headline and retains raw as detail", () => {
  assert.match(source, /chase\.publicScore/);
  assert.match(source, /displayAccessibility\.toFixed/);
  assert.doesNotMatch(source, /publicScore\s*\?\?\s*(?:modelScore|rawAccessibility|displayAccessibility)/);
});

test("decision model preserves distinct Chase fields and cohort identity", () => {
  const model = buildRipDecisionModel({ canonical });
  assert.equal(model.chaseAccessibility.rawAccessibility, 0.00079);
  assert.equal(model.chaseAccessibility.modelScore, 28.33);
  assert.equal(model.chaseAccessibility.publicScore, 64.2);
  assert.deepEqual([model.chaseAccessibility.rank, model.chaseAccessibility.cohortSize, model.chaseAccessibility.cohortId], [21, 22, "cohort-fixture"]);
});

test("missing Chase publicScore remains unavailable with no raw/model fallback", () => {
  const model = buildRipDecisionModel({ canonical: { ...canonical, chaseAccessibility: { ...chase, publicScore: null } } });
  assert.equal(model.chaseAccessibility.publicScore, null);
  assert.equal(model.chaseAccessibility.modelScore, 28.33);
  assert.equal(model.chaseAccessibility.rawAccessibility, 0.00079);
});

test("active presentation contains no Market-Based wrapper or scoring recipe", () => {
  assert.doesNotMatch(source, /<MarketBasedOpeningQualityBreakdown/);
  assert.doesNotMatch(source, /86%|4%|10%|0\.86|0\.04/);
});
