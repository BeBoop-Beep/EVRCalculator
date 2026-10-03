import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const clientSource = fs.readFileSync(
  new URL("./TreatmentPreferenceStudyClient.jsx", import.meta.url),
  "utf8",
);
const pageSource = fs.readFileSync(new URL("./page.js", import.meta.url), "utf8");

test("Treatment preference respondent surface stays blinded", () => {
  const source = clientSource + "\n" + pageSource;
  assert.doesNotMatch(source, /Special Illustration Rare/);
  assert.doesNotMatch(source, /Ultra Rare/);
  assert.doesNotMatch(source, /Double Rare/);
  assert.doesNotMatch(source, /treatment_a|treatment_b|left_treatment|right_treatment/i);
  assert.doesNotMatch(source, /aggregate results?[^a-z]/i);
  assert.match(source, /Which version would you rather own for the artwork\/presentation itself\?/);
  assert.match(source, /Ignore market value, pull rates, rankings/);
});

test("Treatment preference surface uses anonymous resumable browser-local sessions", () => {
  assert.match(clientSource, /window\.crypto\.randomUUID\(\)/);
  assert.match(clientSource, /window\.localStorage/);
  assert.match(clientSource, /sessionId/);
  assert.match(clientSource, /claimToken/);
  assert.match(clientSource, /answers: questions\.map/);
});

test("Treatment preference surface never requests aggregate study results", () => {
  assert.match(clientSource, /\/api\/research\/treatment-preference-v1\/block/);
  assert.match(clientSource, /\/api\/research\/treatment-preference-v1\/submit/);
  assert.doesNotMatch(clientSource, /results|leaderboard|score|rankings\/|summary endpoint/i);
});
