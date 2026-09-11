const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const source = fs.readFileSync(path.join(__dirname, "ExploreTableClient.jsx"), "utf8");
const projection = fs.readFileSync(path.join(__dirname, "../../lib/explore/rankingsClientProjection.mjs"), "utf8");

test("Set Rankings renders RIP Score plus three peer metric fields", () => {
  for (const label of ["RIP Score", "Financial RIP", "Chase Accessibility", "Collector Appeal"])
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

test("ChaseAccessibilityCell, ScoreCell, and MobileScoreBlock lock before checking for missing data when not entitled", () => {
  // Task 4: once canViewProductRipIntelligence can genuinely be false (Task 1
  // fixed the JSX-shorthand bug that always forced it true), these cells must
  // distinguish "not entitled" from "entitled but genuinely no data". The
  // entitlement check has to run BEFORE the null-check so a locked viewer never
  // sees "Unavailable" (which reads as a data problem, not a paywall).
  const cellNames = ["ChaseAccessibilityCell", "ScoreCell", "MobileScoreBlock"];
  for (const name of cellNames) {
    const fnMatch = new RegExp(`function ${name}\\(([^)]*)\\)\\s*\\{([\\s\\S]*?)\\n\\}`).exec(source);
    assert.ok(fnMatch, `expected to find function ${name} in ExploreTableClient.jsx`);
    const [, params, body] = fnMatch;
    assert.match(params, /entitled/, `${name} must accept an entitled prop`);
    const entitledCheckIndex = body.search(/if\s*\(!entitled\)/);
    assert.notEqual(entitledCheckIndex, -1, `${name} must branch on !entitled`);
    const unavailableCheckIndex = body.search(/=== null/);
    if (unavailableCheckIndex !== -1) {
      assert.ok(
        entitledCheckIndex < unavailableCheckIndex,
        `${name} must check entitlement before its missing-value/Unavailable branch`
      );
    }
  }
});

test("locked cells render PremiumMetricLock, and call sites thread canViewProductRipIntelligence in as entitled", () => {
  assert.match(source, /import \{ PremiumMetricLock \} from "\.\/RankedProductTablePrimitives\.jsx";/);
  assert.match(source, /<PremiumMetricLock \/>/);
  // Desktop cells
  assert.match(source, /<ScoreCell target=\{target\} modeId="financial" entitled=\{canViewProductRipIntelligence\} \/>/);
  assert.match(source, /<ChaseAccessibilityCell target=\{target\} entitled=\{canViewProductRipIntelligence\} \/>/);
  assert.match(source, /<ScoreCell target=\{target\} modeId=\{COLLECTOR_APPEAL_COLUMN\} entitled=\{canViewProductRipIntelligence\} \/>/);
  // Mobile cells
  assert.match(source, /<MobileScoreBlock target=\{target\} modeId="financial" label="Financial RIP" entitled=\{canViewProductRipIntelligence\} \/>/);
  assert.match(source, /<ChaseAccessibilityCell target=\{target\} compact entitled=\{canViewProductRipIntelligence\} \/>/);
  assert.match(source, /<MobileScoreBlock target=\{target\} modeId=\{COLLECTOR_APPEAL_COLUMN\} label="Collector Appeal" entitled=\{canViewProductRipIntelligence\} \/>/);
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
