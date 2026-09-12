import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const read = (name) => fs.readFileSync(new URL(name, import.meta.url), "utf8");
const hub = read("./CardRankingsHub.jsx");
const collector = read("./CardCollectorAppealRankings.jsx");
const chase = read("./CardChaseEfficiencyRankings.jsx");

test("Cards exposes two separately entitled and conditionally mounted lenses", () => {
  assert.match(hub, /Collector Appeal/);
  assert.match(hub, /Chase Efficiency/);
  assert.match(hub, /lens === "collector"/);
  assert.match(hub, /lens === "chase"/);
  assert.match(hub, /canViewCollectorAppeal/);
  assert.match(hub, /canViewChaseEfficiency/);
});

test("only mounted paid card lens owns its debounced cached request", () => {
  assert.match(collector, /setTimeout/);
  assert.match(collector, /canonicalCardQueryKey\(params, "collector"\)/);
  assert.match(collector, /card-collector-appeal/);
  assert.match(chase, /canonicalCardQueryKey\(params\)/);
  assert.match(chase, /card-chase-efficiency/);
});

test("card tables render fixed image geometry and preserve semantic emphasis", () => {
  for (const source of [collector, chase]) {
    assert.match(source, /h-14 w-10/);
    assert.match(source, /imageSmallUrl/);
  }
  assert.match(chase, /font-bold text-\[var\(--text-primary\)\]/);
  assert.match(chase, /font-semibold text-\[var\(--accent\)\]/);
  assert.match(collector, /Treatment/);
  assert.doesNotMatch(collector, /treatmentScore/);
});
