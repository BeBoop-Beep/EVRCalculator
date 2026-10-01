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

test("Cards has one async boundary and statically owns both conditionally mounted implementations", () => {
  assert.doesNotMatch(hub, /next\/dynamic|dynamic\(/);
  assert.match(hub, /import CardCollectorAppealRankings/);
  assert.match(hub, /import CardChaseEfficiencyRankings/);
  assert.match(hub, /lens === "collector"/);
  assert.match(hub, /lens === "chase"/);
});

test("only mounted paid card lens owns its debounced cached request", () => {
  assert.match(collector, /setTimeout/);
  assert.match(collector, /canonicalCardQueryKey\(params, `collector:\$\{lens\}`\)/);
  assert.match(collector, /fetchCollectorRows/);
  assert.match(chase, /canonicalCardQueryKey\(params\)/);
  assert.match(chase, /card-chase-efficiency/);
});

test("card tables render fixed image geometry and preserve semantic emphasis", () => {
  for (const source of [collector, chase]) {
    assert.match(source, /h-(14|16) w-(10|11)/);
    assert.match(source, /imageSmallUrl/);
  }
  assert.match(chase, /font-bold text-\[var\(--text-primary\)\]/);
  assert.match(chase, /font-semibold text-\[var\(--accent\)\]/);
  assert.match(collector, /Collector Appeal/);
  assert.doesNotMatch(collector, /treatmentScore/);
});

test("cold footers tell the truth before a payload exists", () => {
  assert.match(collector, /Loading card rankings/);
  assert.match(chase, /Loading card rankings/);
  assert.match(collector, /result\.payload \?/);
  assert.match(chase, /result\.payload \?/);
});
