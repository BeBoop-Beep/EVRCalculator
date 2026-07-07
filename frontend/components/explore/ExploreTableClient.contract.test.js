const fs = require("fs");
const path = require("path");
const test = require("node:test");
const assert = require("node:assert/strict");

const componentPath = path.resolve(__dirname, "ExploreTableClient.jsx");

// Phase 5.5 (Gate 3): the empty-targets branch previously always rendered
// "Ranking snapshots are still loading...", even when the targets fetch had
// actually failed (backend down/errored) rather than the rankings snapshot
// genuinely being empty. Callers now pass a loadError prop so the two states
// are visually distinct — this is a rendering/prop-plumbing fix only, no
// ranking order or scoring logic touched.

test("ExploreTableClient accepts a loadError prop defaulting to false", () => {
  const source = fs.readFileSync(componentPath, "utf8");

  assert.ok(
    source.includes("export default function ExploreTableClient({ targets = [], loadError = false }) {"),
    "component signature must accept loadError alongside targets"
  );
});

test("ExploreTableClient renders a distinct error message when loadError is true, separate from the genuine-empty message", () => {
  const source = fs.readFileSync(componentPath, "utf8");

  const emptyBranchStart = source.indexOf("sortedTargets.length > 0 ? (");
  assert.ok(emptyBranchStart >= 0, "must branch on sortedTargets.length");

  const errorBranchIndex = source.indexOf(") : loadError ? (", emptyBranchStart);
  const genuineEmptyIndex = source.indexOf(") : (", errorBranchIndex);

  assert.ok(errorBranchIndex > emptyBranchStart, "must have a distinct loadError branch before the generic empty branch");
  assert.ok(genuineEmptyIndex > errorBranchIndex, "generic empty-state branch must come after the loadError branch");

  const errorBranchSource = source.slice(errorBranchIndex, genuineEmptyIndex);
  assert.ok(
    errorBranchSource.includes("temporarily unavailable"),
    "loadError branch must show a distinct 'temporarily unavailable' message, not the generic loading copy"
  );
  assert.ok(errorBranchSource.includes('role="alert"'), "error state should be announced via role=alert");

  const genuineEmptySource = source.slice(genuineEmptyIndex);
  assert.ok(
    genuineEmptySource.includes("Ranking snapshots are still loading"),
    "genuine-empty branch must keep the original loading copy"
  );
});
