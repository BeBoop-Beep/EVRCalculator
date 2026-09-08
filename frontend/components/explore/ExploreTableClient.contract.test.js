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
