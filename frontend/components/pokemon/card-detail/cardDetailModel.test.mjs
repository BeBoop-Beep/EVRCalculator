import assert from "node:assert/strict";
import test from "node:test";
import { cumulativePullProbability, milestoneXPosition, packsAtPlotX, packsForMilestone, probabilityMilestones, validPullProbability } from "./cardDetailModel.mjs";

test("cumulative probability and milestone packs use the canonical independent-pack equations", () => {
  const p = 1 / 21;
  assert.ok(Math.abs(cumulativePullProbability(p, 29) - (1 - Math.pow(20 / 21, 29))) < 1e-12);
  assert.deepEqual(probabilityMilestones(p).map(({ packs }) => packs), [15, 29, 48, 62]);
  assert.equal(packsForMilestone(p, .75), 29);
});

test("published backend milestones remain authoritative", () => {
  assert.equal(probabilityMilestones(.1, { packsFor50PercentChance: 8 })[0].packs, 8);
});

test("milestone positions are proportional to real pack counts", () => {
  assert.equal(milestoneXPosition(15, 62), 54 + 15 / 62 * 626);
  assert.ok(milestoneXPosition(29, 62) - milestoneXPosition(15, 62) < milestoneXPosition(62, 62) - milestoneXPosition(29, 62));
});

test("plot pointer coordinates invert the same SVG scale at bounds, milestones, and midpoint", () => {
  const max = 4591;
  assert.equal(packsAtPlotX(54, max), 0);
  assert.equal(packsAtPlotX(680, max), max);
  assert.equal(packsAtPlotX(367, max), Math.round(max / 2));
  for (const packs of [1063, 2125, 3529, 4591]) {
    assert.ok(Math.abs(packsAtPlotX(milestoneXPosition(packs, max), max) - packs) <= 1);
  }
});

test("invalid, zero, null, and impossible inputs never emit fake numbers", () => {
  for (const value of [null, undefined, 0, -1, Number.NaN, Number.POSITIVE_INFINITY, 1.1]) assert.equal(validPullProbability(value), null);
  assert.equal(cumulativePullProbability(0, 10), null);
  assert.equal(packsForMilestone(.1, 1), null);
  assert.equal(milestoneXPosition(Number.NaN, 10), null);
});

test("certain pulls handle zero packs and the first eligible pack", () => {
  assert.equal(cumulativePullProbability(1, 0), 0);
  assert.equal(cumulativePullProbability(1, 1), 1);
  assert.equal(packsForMilestone(1, .95), 1);
});
