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

// Phase 2-4: absolute / relative / rank presentation, both score families.

test("desktop default mode renders Overall RIP and Financial RIP columns", () => {
  const source = fs.readFileSync(componentPath, "utf8");
  assert.ok(source.includes("<span>Overall RIP</span>"), "desktop header must include an Overall RIP column");
  assert.ok(source.includes("<span>Financial RIP</span>"), "desktop header must include a Financial RIP column");
  assert.ok(
    source.includes('<ScoreCell target={target} modeId="overall" />'),
    "desktop overall column must render the Overall RIP score cell"
  );
  assert.ok(
    source.includes('<ScoreCell target={target} modeId="financial" />'),
    "desktop financial column must render the Financial RIP score cell"
  );
});

test("non-default modes render a single mode-scoped score cell", () => {
  const source = fs.readFileSync(componentPath, "utf8");
  assert.ok(
    source.includes("<ScoreCell target={target} modeId={selectedMode} />"),
    "non-overall modes must render one ScoreCell bound to the selected mode"
  );
});

test("ScoreCell reads authoritative absolute/relative/rank/cohort fields, never derives", () => {
  const source = fs.readFileSync(componentPath, "utf8");
  const cellStart = source.indexOf("function readModeScore");
  assert.ok(cellStart >= 0, "readModeScore helper must exist");
  const cellSource = source.slice(cellStart, source.indexOf("function ScoreCell", cellStart) + 1200);
  for (const getter of [
    "getAbsoluteScoreForMode",
    "getRelativeScoreForMode",
    "getRankForMode",
    "getRankedSetCountForMode",
  ]) {
    assert.ok(cellSource.includes(getter), `score reads must go through ${getter}`);
  }
});

test("null scores render an explicit Unavailable state, never zero", () => {
  const source = fs.readFileSync(componentPath, "utf8");
  assert.ok(source.includes('UNAVAILABLE_LABEL = "Unavailable"'), "an explicit Unavailable label must exist");
  // Both the desktop cell and the mobile block must branch on a null absolute.
  assert.ok(
    source.includes("if (absolute === null)"),
    "the desktop ScoreCell must guard a null absolute with the Unavailable state"
  );
  assert.ok(
    source.includes("absolute === null ? ("),
    "the mobile score block must guard a null absolute with the Unavailable state"
  );
});

test("mobile always renders both Overall and Financial score families", () => {
  const source = fs.readFileSync(componentPath, "utf8");
  assert.ok(
    source.includes('<MobileScoreBlock target={target} modeId="overall" label="Overall" />'),
    "mobile card must always show the Overall score block"
  );
  assert.ok(
    source.includes('<MobileScoreBlock target={target} modeId="financial" label="Financial" />'),
    "mobile card must always show the Financial score block (never hidden on mobile)"
  );
});

test("sort contract is rank -> relative -> absolute -> name", () => {
  const source = fs.readFileSync(componentPath, "utf8");
  const sortStart = source.indexOf("function sortTargetsByMode");
  const sortSource = source.slice(sortStart, sortStart + 1400);
  const rankIndex = sortSource.indexOf("compareRankAsc(getRankForMode");
  const relativeIndex = sortSource.indexOf("getRelativeScoreForMode");
  const absoluteIndex = sortSource.indexOf("getAbsoluteScoreForMode");
  const nameIndex = sortSource.indexOf("localeCompare");
  assert.ok(rankIndex >= 0, "sort must first compare rank ascending");
  assert.ok(relativeIndex > rankIndex, "relative comparison must follow rank");
  assert.ok(absoluteIndex > relativeIndex, "absolute comparison must follow relative");
  assert.ok(nameIndex > absoluteIndex, "name tie-break must be last");
});
