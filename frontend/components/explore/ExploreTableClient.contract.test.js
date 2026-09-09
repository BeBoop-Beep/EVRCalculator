const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const source = fs.readFileSync(path.join(__dirname, "ExploreTableClient.jsx"), "utf8");
const projection = fs.readFileSync(path.join(__dirname, "../../lib/explore/rankingsClientProjection.mjs"), "utf8");

test("Set Rankings renders Overall plus three peer metric fields", () => {
  for (const label of ["Overall RIP", "Financial RIP", "Chase Accessibility", "Collector Appeal"])
    assert.match(source, new RegExp(label));
});

test("Set Rankings consumes Chase public score and set standing", () => {
  assert.match(source, /block\.publicScore/);
  assert.match(source, /block\?\.setRank/);
  assert.match(source, /block\?\.setCohortSize/);
  assert.doesNotMatch(source, /publicScore\s*\?\?\s*(?:modelScore|value|percent)/);
});

test("client projection allowlists the complete Chase delivery contract", () => {
  for (const field of ["value", "modelScore", "publicScore", "setRank", "setCohortSize", "cohortId"])
    assert.match(projection, new RegExp(`"${field}"`));
});

test("rankings remain semantic, sortable, linked, and responsive", () => {
  assert.match(source, /<table/);
  assert.match(source, /<caption/);
  assert.match(source, /aria-sort/);
  assert.match(source, /buildTcgSetHrefFromTarget/);
  assert.match(source, /styles\.mobile/);
});

test("rankings sorting is local and missing Chase is never coerced to zero", () => {
  assert.doesNotMatch(source, /fetch\(/);
  assert.match(source, /publicScore === null/);
});

test("legacy Market-Based spanning group is absent", () => {
  assert.doesNotMatch(source, />\s*Market-Based\s*</);
});

test("setRipV1's client leaf list carries chaseAccessibility through to the table", () => {
  // Task 3 regression: setRipV1.chaseAccessibility was dropped at the SQL lens
  // boundary (20260906055315_add_v12_v11_to_rankings_sets_lens_rpc.sql), which
  // made ExploreTableClient's ChaseAccessibilityCell (reading
  // `target.setRipV1.chaseAccessibility` verbatim) render "Unavailable" for
  // every set. The client-side allowlist in rankingsClientProjection.mjs must
  // also carry it, or a SQL-level fix alone would still ship an empty table.
  const setRipLeavesMatch = /setRipV1:\s*\[([^\]]+)\]/.exec(projection);
  assert.ok(setRipLeavesMatch, "expected a setRipV1 leaf list in rankingsClientProjection.mjs");
  assert.match(setRipLeavesMatch[1], /"chaseAccessibility"/);
});
