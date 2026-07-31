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

test("null primary scores render an explicit Unavailable state, never zero", () => {
  const source = fs.readFileSync(componentPath, "utf8");
  assert.ok(source.includes('UNAVAILABLE_LABEL = "Unavailable"'), "an explicit Unavailable label must exist");
  // Both the desktop cell and the mobile block must branch on a null PRIMARY
  // value (the relative public score, or the absolute for ratio/legacy modes) —
  // never silently promoting the model score when the relative one is missing.
  assert.ok(
    source.includes("if (primaryText === null)"),
    "the desktop ScoreCell must guard a null primary value with the Unavailable state"
  );
  assert.ok(
    source.includes("primaryText === null ? ("),
    "the mobile score block must guard a null primary value with the Unavailable state"
  );
});

test("relative is the prominent value, with the rank as its only supporting line", () => {
  const source = fs.readFileSync(componentPath, "utf8");
  const cellStart = source.indexOf("function ScoreCell");
  const cellSource = source.slice(cellStart, source.indexOf("function MobileScoreBlock", cellStart));
  // Primary text prefers the relative score, falling back to absolute only for
  // modes with no relative field (ratio-only / legacy-relative modes).
  assert.ok(
    cellSource.includes("hasRelative") && cellSource.includes("formatRelative(relative)"),
    "ScoreCell must derive its prominent value from the relative score when present"
  );
  // The prominent span must render primaryText (relative-first), not the raw absolute.
  assert.ok(
    /font-semibold text-\[var\(--text-primary\)\]">\{primaryText\}</.test(cellSource),
    "the prominent span must render the relative-first primaryText"
  );
  assert.ok(cellSource.includes("{rankText}"), "the supporting line must be the rank");
});

test("mobile preserves the relative-primary hierarchy", () => {
  const source = fs.readFileSync(componentPath, "utf8");
  const start = source.indexOf("function MobileScoreBlock");
  const mobileSource = source.slice(start, source.indexOf("function sortTargetsByMode", start));
  assert.ok(
    /font-semibold text-\[var\(--text-primary\)\]">\{primaryText\}</.test(mobileSource),
    "mobile prominent span must render the relative-first primaryText"
  );
  assert.ok(mobileSource.includes("{rankText}"), "mobile must keep the rank as the supporting value");
});

// The internal "model score" (the raw pre-standardization formula output) is
// no longer shown to readers: next to a standardized 0-100 score it read as a
// second, contradictory number. The absolute is still READ from the backend,
// because ratio-only and legacy-relative modes have no relative field and use
// it as their single displayed score.
test("the internal model score is never displayed", () => {
  const source = fs.readFileSync(componentPath, "utf8");
  assert.ok(!/\bModel \{/.test(source), "no cell may render a 'Model' value");
  assert.ok(!source.includes("`Model ${"), "no cell may compose a 'Model' string");
  assert.ok(
    !source.includes("Model scores are the underlying formula outputs"),
    "the tooltip must not explain a number that is no longer shown"
  );
  assert.ok(
    source.includes("getAbsoluteScoreForMode"),
    "the absolute must still be read as the fallback primary for modes without a relative score"
  );
});

test("a tooltip explains what the displayed score means", () => {
  const source = fs.readFileSync(componentPath, "utf8");
  assert.ok(
    source.includes("RELATIVE_SCORE_TOOLTIP") && source.includes("standardize each set against the current eligible cohort"),
    "a tooltip must explain that the displayed score standardizes each set against the cohort"
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

// Explore refinement Phase 2 — presentation only. Every assertion below is
// about markup/semantics; none of them touch how a score is produced.

test("desktop renders semantic table markup with an accessible caption", () => {
  const source = fs.readFileSync(componentPath, "utf8");
  assert.ok(source.includes("<table className={styles.table}>"), "desktop must render a real <table>");
  assert.ok(source.includes('<caption className="sr-only">'), "the table must carry an accessible caption");
  assert.ok(source.includes('<th scope="col"'), "column headers must be scoped <th> elements");
  assert.ok(source.includes("<tbody>") && source.includes("<thead"), "table must use thead/tbody sections");
});

test("the column the active ranking mode orders by announces its sort state", () => {
  const source = fs.readFileSync(componentPath, "utf8");
  assert.ok(source.includes('aria-sort="descending"'), "the ordered column must expose aria-sort");
  // Sorting is still driven exclusively by the ranking-mode menu; no per-column
  // sort handler may be introduced, because that would bypass the canonical
  // rank -> relative -> absolute -> name contract.
  assert.ok(!/<th[^>]*onClick/.test(source), "column headers must not introduce their own sort handlers");
});

test("each row keeps exactly one real link, stretched over the row", () => {
  const source = fs.readFileSync(componentPath, "utf8");
  assert.ok(source.includes("className={styles.rowLink}"), "the row link must use the stretched-link treatment");
  const bodyStart = source.indexOf("<tbody>");
  const bodyEnd = source.indexOf("</tbody>");
  const bodySource = source.slice(bodyStart, bodyEnd);
  const linkCount = (bodySource.match(/<Link\b/g) || []).length;
  assert.equal(linkCount, 1, "a table row must contain a single Link, not one per cell");
  assert.ok(bodySource.includes("href={buildRipLink(target)}"), "row navigation target must be unchanged");
});

test("rank is a scannable column driven by the canonical mode rank", () => {
  const source = fs.readFileSync(componentPath, "utf8");
  assert.ok(
    source.includes("getRankForMode(target, selectedMode) ?? index + 1"),
    "the rank marker must read the canonical mode rank, falling back to render order only for display"
  );
  assert.ok(source.includes("LEAD_RANK_LIMIT"), "top-of-ladder emphasis must be bounded by an explicit limit");
});

test("compact rank displays drop the repeated cohort size", () => {
  const source = fs.readFileSync(componentPath, "utf8");
  assert.ok(
    source.includes("withCohort = true"),
    "formatRankText must expose a withCohort option so cells can omit the repeated 'of N'"
  );
  assert.ok(
    source.includes("formatRankText(rank, cohort, { withCohort: false })"),
    "the desktop score cell must render a bare #rank"
  );
  assert.ok(
    source.includes("formatRankText(rank, cohort, { compact: true, withCohort: false })"),
    "the mobile score block must render a bare #rank"
  );
});

test("Explore visual treatment stays in an Explore-scoped CSS module", () => {
  const source = fs.readFileSync(componentPath, "utf8");
  assert.ok(source.includes('import styles from "./explore.module.css"'), "surface styling must come from the scoped module");
  const cssPath = path.resolve(__dirname, "explore.module.css");
  assert.ok(fs.existsSync(cssPath), "the Explore CSS module must exist");
  const css = fs.readFileSync(cssPath, "utf8");
  // Guard against this phase leaking into global design tokens the parallel
  // navigation work also touches.
  assert.ok(!css.includes(":root"), "the Explore module must not redefine global tokens");
  assert.ok(css.includes("prefers-reduced-motion"), "reduced motion must be respected");
});

// The alternate ranking lenses are planned to sit behind a paid tier, so the
// picker is hidden — NOT deleted. The modes, the sorting, and the mode-scoped
// columns must all still be present and wired so the flag alone brings it back.
test("the ranking-mode picker is hidden behind a flag, not removed", () => {
  const source = fs.readFileSync(componentPath, "utf8");
  assert.ok(
    source.includes("const RANKING_MODE_PICKER_ENABLED = false;"),
    "the picker must be gated by an explicit, flippable flag"
  );
  assert.ok(
    source.includes("{RANKING_MODE_PICKER_ENABLED ? ("),
    "the dropdown trigger must render only when the flag is on"
  );
  assert.ok(
    source.includes("{RANKING_MODE_PICKER_ENABLED && dropdownOpen && ("),
    "the dropdown menu must not be reachable while the flag is off"
  );
  // Everything the picker drives must survive untouched.
  assert.ok(source.includes("EXPLORE_RANKING_MODES"), "the mode config must still be imported and mapped");
  assert.ok(source.includes("setSelectedMode(modeId)"), "mode selection must still be wired for when the flag returns");
  assert.ok(source.includes("sortTargetsByMode(targets, selectedMode)"), "mode-driven sorting must be untouched");
});

test("mobile keeps identity, both score families, tier and the headline financial signal", () => {
  const source = fs.readFileSync(componentPath, "utf8");
  const start = source.indexOf("{/* Mobile rows");
  const mobileSource = source.slice(start);
  assert.ok(mobileSource.includes("className={styles.mobileRow}"), "mobile must use the purpose-built compact row");
  assert.ok(mobileSource.includes('variant="compact"'), "mobile must use the compact set identity");
  assert.ok(mobileSource.includes("<RankBadge rank={tier}"), "mobile must keep the tier badge");
  assert.ok(mobileSource.includes("formatLossCurrency(averageLoss)"), "mobile must keep the average-loss signal");
});

test("Best Sets heading is stronger below desktop and resets at desk width", () => {
  const source = fs.readFileSync(componentPath, "utf8");
  assert.ok(
    source.includes("text-[18px] font-semibold leading-[1.25] text-[var(--text-primary)] desk:text-[15px] desk:leading-normal"),
    "mobile/tablet heading typography must be stronger and revert at desktop"
  );
  assert.ok(
    source.includes("px-3 py-3 desk:py-2.5 sm:px-4"),
    "the module header row should have extra vertical breathing room below desktop"
  );
});

test("mobile preview shows ten rows before the compact More control expands the rest", () => {
  const source = fs.readFileSync(componentPath, "utf8");
  assert.ok(source.includes("MOBILE_PREVIEW_LIMIT = 10"), "the preview limit must be explicit");
  assert.ok(source.includes("visibleMobileTargets"), "the rendered mobile slice must be derived separately");
  assert.ok(source.includes("hiddenMobileCount"), "the remaining rows must be counted for the More control");
  assert.ok(source.includes('showAllMobileRows ? "Show less" : "More"'), "the preview toggle must expand and collapse");
  assert.ok(source.includes("sortedTargets.length <= MOBILE_PREVIEW_LIMIT"), "rows under the limit stay fully visible");
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
