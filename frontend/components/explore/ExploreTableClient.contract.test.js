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
  assert.ok(source.includes('label="Overall RIP"'), "desktop header must include an Overall RIP column");
  assert.ok(source.includes('label="Financial RIP"'), "desktop header must include a Financial RIP column");
  assert.ok(
    source.includes('<ScoreCell target={target} modeId="overall" />'),
    "desktop overall column must render the Overall RIP score cell"
  );
  assert.ok(
    source.includes('<ScoreCell target={target} modeId="financial" />'),
    "desktop financial column must render the Financial RIP score cell"
  );
});

/* ------------------------------------ Rankings completeness: seven metrics --- */

// The table must SURFACE all seven quantitative metrics. What each one reads is
// asserted behaviourally in rankingsSort.test.mjs against the real module; what
// can only be checked here is that each one actually reaches the markup.

test("the desktop table surfaces all seven required metrics", () => {
  const source = fs.readFileSync(componentPath, "utf8");
  for (const label of [
    "Overall RIP",
    "Financial RIP",
    "Collector Appeal",
    "EV",
    "Average Loss",
    "Market Pack Price",
    "Chance to Beat Cost",
  ]) {
    assert.ok(source.includes(`label="${label}"`), `${label} must be a column heading`);
  }

  // …and that each has a value cell, not just a heading.
  assert.ok(source.includes('<ScoreCell target={target} modeId="collectorAppeal" />'), "Collector Appeal cell");
  assert.ok(source.includes("formatCurrency(target?.mean_value)"), "EV cell reads the published mean_value");
  assert.ok(source.includes("formatLossCurrency(averageLoss)"), "Average Loss cell");
  // Average Loss must come from the shared reader (the simulation's published
  // conditional loss), never from an inline EV-based expression.
  assert.ok(source.includes("readAverageLoss(target)"), "Average Loss must use the shared reader");
  const code = source
    .split(/\r?\n/)
    .filter((line) => !/^\s*(\/\/|\*|\/\*)/.test(line))
    .join("\n");
  assert.ok(
    !/pack_cost\s*\)?\s*-\s*.*mean_value/.test(code) && !code.includes("estimateAverageLoss"),
    "the retired unconditional pack_cost - mean_value expression must not return"
  );
  assert.ok(source.includes("formatCurrency(target?.pack_cost)"), "Market Pack Price cell");
  assert.ok(source.includes("formatPercent(target?.prob_profit, true)"), "Chance to Beat Cost cell");
});

test("mobile surfaces the same seven metrics", () => {
  const source = fs.readFileSync(componentPath, "utf8");
  const mobileSource = source.slice(source.indexOf("{/* Mobile rows"));
  assert.ok(mobileSource.includes('modeId="overall" label="Overall"'));
  assert.ok(mobileSource.includes('modeId="financial" label="Financial"'));
  assert.ok(mobileSource.includes('modeId="collectorAppeal" label="Appeal"'));
  assert.ok(mobileSource.includes(">EV</div>"), "mobile must show EV");
  assert.ok(mobileSource.includes("formatLossCurrency(averageLoss)"), "mobile must show Average Loss");
  assert.ok(mobileSource.includes("formatCurrency(target?.pack_cost)"), "mobile must show Market Price");
  assert.ok(mobileSource.includes("formatPercent(target?.prob_profit, true)"), "mobile must show Chance to Beat Cost");
  // The extra metrics must wrap inside the card rather than widen the row, so
  // the page cannot gain a horizontal scrollbar on a phone.
  assert.ok(mobileSource.includes("grid grid-cols-4"), "mobile metrics must wrap in a fixed grid, not a wider flex row");
});

test("Collector Appeal reads the canonical public contract, never a frontend substitute", () => {
  const source = fs.readFileSync(componentPath, "utf8");
  assert.ok(
    source.includes("readCollectorAppealBlock"),
    "Collector Appeal must be read through the canonical reader"
  );
  const code = source
    .split(/\r?\n/)
    .filter((line) => !/^\s*(\/\/|\*|\/\*)/.test(line))
    .join("\n");
  // The retired CA7-era flat columns live on the same target row.
  assert.ok(!code.includes("collector_appeal_score"), "the retired flat CA7 score must not be read");
  assert.ok(!code.includes("collector_appeal_rank"), "the retired flat CA7 rank must not be read");
  // No weight, no coefficient, no recomputation.
  assert.ok(!/0\.4\s*\*/.test(code) && !/weights\s*\[/.test(code), "no Collector Appeal arithmetic may live here");
});

/* ------------------------------------------- Rankings completeness: sorting --- */

test("sorting is client-side over the already-loaded targets, with no fetch", () => {
  const source = fs.readFileSync(componentPath, "utf8");
  assert.ok(
    source.includes("sortRankingsRows(canonicalTargets, sort)"),
    "the rendered rows must be a sort of the in-memory canonical array"
  );
  assert.ok(
    source.includes("useMemo(() => sortRankingsRows(canonicalTargets, sort), [canonicalTargets, sort])"),
    "the sorted rows must be memoized on the data and the sort state alone"
  );
  // Nothing in this component may reach the network or the router when a header
  // is clicked. A header click sets local state and nothing else.
  for (const forbidden of ["fetch(", "useRouter", "router.", "revalidate", "useSWR", "axios"]) {
    assert.ok(!source.includes(forbidden), `a sort must not trigger ${forbidden}`);
  }
});

test("the default sort state is the canonical Overall RIP order", () => {
  const source = fs.readFileSync(componentPath, "utf8");
  assert.ok(
    source.includes("useState(RANKINGS_DEFAULT_SORT)"),
    "initial sort must be the module's declared default (Overall RIP descending)"
  );
  assert.ok(
    source.includes("sortTargetsByMode(targets, selectedMode)"),
    "the canonical ordering pass must still run first and feed the sort"
  );
});

test("every quantitative header is a keyboard-operable sort control that announces its state", () => {
  const source = fs.readFileSync(componentPath, "utf8");
  const headerStart = source.indexOf("function SortableHeader");
  assert.ok(headerStart >= 0, "a shared sortable-header component must exist");
  const headerSource = source.slice(headerStart, source.indexOf("export default function", headerStart));

  assert.ok(headerSource.includes('scope="col"'), "it must stay a scoped column header");
  assert.ok(headerSource.includes("aria-sort={ariaSort}"), "the active column must expose aria-sort");
  assert.ok(headerSource.includes('type="button"'), "the click target must be a real button, so Enter/Space work");
  assert.ok(headerSource.includes("onClick={() => onSort(columnId)}"), "the header itself is the click target");
  assert.ok(headerSource.includes("aria-label="), "the control must state what it sorts and in which direction");

  // Both directions need an indicator, not just descending.
  const cssPath = path.resolve(__dirname, "explore.module.css");
  const css = fs.readFileSync(cssPath, "utf8");
  assert.ok(css.includes('.head th[aria-sort="descending"]::after'), "descending caret");
  assert.ok(css.includes('.head th[aria-sort="ascending"]::after'), "ascending caret");
  assert.ok(css.includes(".sortButton:focus-visible"), "the header control must show a visible focus ring");
});

test("mobile keeps a tappable sort control even though it has no header row", () => {
  const source = fs.readFileSync(componentPath, "utf8");
  assert.ok(source.includes('className="relative md:hidden" ref={sortMenuContainerRef}'), "mobile sort control exists");
  assert.ok(source.includes("setSortMenuOpen"), "it opens the existing menu pattern");
  assert.ok(source.includes("min-h-11"), "its targets must stay tappable");
  assert.ok(
    source.includes("onClick={() => handleSort(column.id)}"),
    "mobile options must go through the same nextSortState rule as a header click"
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
    "getScoreForMode",
    "getScoreKind",
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
    source.includes("if (value === null) {"),
    "the desktop ScoreCell must guard a null primary value with the Unavailable state"
  );
  assert.ok(
    source.includes("{value === null ? ("),
    "the mobile score block must guard a null primary value with the Unavailable state"
  );
});

test("the one declared score is the prominent value, with the rank as its only supporting line", () => {
  const source = fs.readFileSync(componentPath, "utf8");
  const cellStart = source.indexOf("function ScoreCell");
  const cellSource = source.slice(cellStart, source.indexOf("function MobileScoreBlock", cellStart));
  // One field per column, formatted by its declared kind — never a choice
  // between two differently-scaled candidates.
  assert.ok(
    cellSource.includes("formatModeScore(value, kind)"),
    "ScoreCell must render the mode's one score formatted by its declared kind"
  );
  assert.ok(cellSource.includes("{rankText}"), "the supporting line must be the rank");
});

test("mobile preserves the same one-field-by-kind hierarchy", () => {
  const source = fs.readFileSync(componentPath, "utf8");
  const start = source.indexOf("function MobileScoreBlock");
  const mobileSource = source.slice(start, source.indexOf("function sortTargetsByMode", start));
  assert.ok(
    mobileSource.includes("formatModeScore(value, kind)"),
    "mobile prominent span must render the same declared-kind value"
  );
  assert.ok(mobileSource.includes("{rankText}"), "mobile must keep the rank as the supporting value");
});

// The internal "model score" (the raw pre-standardization formula output) is
// no longer shown to readers: next to a standardized 0-100 score it read as a
// second, contradictory number.
test("the internal model score is never displayed", () => {
  const source = fs.readFileSync(componentPath, "utf8");
  assert.ok(!/\bModel \{/.test(source), "no cell may render a 'Model' value");
  assert.ok(!source.includes("`Model ${"), "no cell may compose a 'Model' string");
  assert.ok(
    !source.includes("Model scores are the underlying formula outputs"),
    "the tooltip must not explain a number that is no longer shown"
  );
  // Collector Appeal comes back from the canonical reader carrying BOTH the
  // public relative score and the internal fixed-anchor modelScore. Only the
  // public one may be rendered — this is exactly the ambiguity that once made
  // one set show two different Collector Appeal numbers on one page.
  assert.ok(!source.includes("modelScore"), "the fixed-anchor model score must not reach this table");
  assert.ok(source.includes("block.publicScore"), "Collector Appeal must render the public relative score");
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

test("the column the table is ordered by announces its sort state", () => {
  const source = fs.readFileSync(componentPath, "utf8");
  assert.ok(source.includes("aria-sort={ariaSort}"), "the ordered column must expose aria-sort");
  // Per-column sorting is now supported, but it must never reach into the
  // canonical ordering: the sort state is a separate value applied AFTER
  // sortTargetsByMode, so the canonical contract is untouched by a click.
  assert.ok(
    source.indexOf("sortTargetsByMode(targets, selectedMode)") <
      source.indexOf("sortRankingsRows(canonicalTargets, sort)"),
    "the canonical ordering must be computed first and then permuted, not replaced"
  );
  assert.ok(!/<th[^>]*onClick/.test(source), "the handler belongs to the header's button, not the <th> itself");
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

test("desktop and mobile ranking rows route to the canonical set RIP tab", () => {
  const source = fs.readFileSync(componentPath, "utf8");
  assert.ok(source.includes('buildTcgSetHrefFromTarget(target, { tab: "overview" })'));
  assert.equal((source.match(/href=\{buildRipLink\(target\)\}/g) || []).length, 2);
  assert.ok(!source.includes('tab: "insights", section: "rip-score"'));
});

test("rank is a scannable column driven by the canonical mode rank", () => {
  const source = fs.readFileSync(componentPath, "utf8");
  assert.ok(
    source.includes("getRankForMode(target, selectedMode) ?? (canonicalIndexByTarget.get(target) ?? index) + 1"),
    "the rank marker must read the canonical mode rank, falling back to canonical position only for display"
  );
  assert.ok(source.includes("LEAD_RANK_LIMIT"), "top-of-ladder emphasis must be bounded by an explicit limit");
});

test("Best Sets reads the authoritative one-day RIP history contract", () => {
  const source = fs.readFileSync(componentPath, "utf8");
  assert.ok(source.includes("previousOverallRipRank1d"));
  assert.ok(source.includes("overallRipRankComparisonStatus1d"));
  assert.ok(source.includes("previousFinancialRipRank1d"));
  assert.ok(!source.includes("ripRankComparisonStatus7d"));
  assert.ok(!source.includes("formatRankMovement(null, modeRank"));
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

test("the desktop table header uses a readable translucent glass band", () => {
  const cssPath = path.resolve(__dirname, "explore.module.css");
  const css = fs.readFileSync(cssPath, "utf8");
  const headerBlock = css.slice(css.indexOf(".head th {"), css.indexOf(".head th[aria-sort]"));
  assert.ok(headerBlock.includes("rgba(24, 38, 60, 0.62)"));
  assert.ok(headerBlock.includes("rgba(8, 17, 31, 0.48)"));
  assert.ok(headerBlock.includes("backdrop-filter: blur(var(--set-glass-blur-dense))"));
  assert.ok(!headerBlock.includes("0.98"), "the header must not return to its former near-opaque fill");
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

test("mobile preview shows five rows before the disclosure control expands the rest", () => {
  const source = fs.readFileSync(componentPath, "utf8");
  assert.ok(source.includes("MOBILE_PREVIEW_LIMIT = 5"), "the preview limit must be explicit");
  assert.ok(source.includes("visibleMobileTargets"), "the rendered mobile slice must be derived separately");
  assert.ok(source.includes("hiddenMobileCount"), "the remaining rows must be counted for the More control");
  assert.ok(source.includes('showAllMobileRows ? "Show less" : `Show ${hiddenMobileCount} more`'), "the preview toggle must be remainder-aware");
  assert.ok(source.includes("sortedTargets.length <= MOBILE_PREVIEW_LIMIT"), "rows under the limit stay fully visible");
});

// The CANONICAL ordering contract — the input to column sorting, unchanged by
// it. Column sorting is a presentation permutation applied on top; its own
// contract (descending first, nulls last, canonical tie-break) is asserted
// behaviourally in rankingsSort.test.mjs.
test("canonical sort contract is rank -> the mode's one score -> name", () => {
  const source = fs.readFileSync(componentPath, "utf8");
  const sortStart = source.indexOf("function sortTargetsByMode");
  const sortSource = source.slice(sortStart, sortStart + 1400);
  const rankIndex = sortSource.indexOf("compareRankAsc(getRankForMode");
  const scoreIndex = sortSource.indexOf("compareScoreDesc(");
  const nameIndex = sortSource.indexOf("localeCompare");
  assert.ok(rankIndex >= 0, "sort must first compare rank ascending");
  assert.ok(scoreIndex > rankIndex, "the mode's one score must follow rank");
  assert.ok(nameIndex > scoreIndex, "name tie-break must be last");
});

test("the canonical rank column is unaffected by the presentation sort", () => {
  const source = fs.readFileSync(componentPath, "utf8");
  // The "#" cell keeps reading the backend rank. Its only fallback is the row's
  // position in the CANONICAL array — never its position in the current sort,
  // which would turn a presentation choice into a fabricated rank.
  assert.equal(
    (source.match(/getRankForMode\(target, selectedMode\) \?\? \(canonicalIndexByTarget\.get\(target\) \?\? index\) \+ 1/g) || []).length,
    2,
    "both desktop and mobile rank fallbacks must come from the canonical order"
  );
  assert.ok(!source.includes("getRankForMode(target, selectedMode) ?? index + 1"), "no render-order rank fallback");
});

/* ------------------------------------------- no interpretation-engine leak --- */

// The rendered absence of the verdict badge is asserted behaviourally in
// SetIdentity.test.jsx, which renders the component that used to draw it. What
// can only be checked here is the other half of the contract: that this table
// no longer READS the retired engine's fields at all, so no future edit can
// re-plumb them into a cell. A source check is the right instrument for
// "this module does not reference these fields"; it is not standing in for a
// behaviour that could have been rendered.

test("the leaderboard reads no interpretation-engine field", () => {
  const source = fs.readFileSync(componentPath, "utf8");

  for (const field of [
    "leaderboard_label",
    "canonical_recommendation_header",
    "recommendation_severity",
    "interpretationLabel",
    "interpretationSummary",
    "decisionLabel",
  ]) {
    // Comments documenting the removal are allowed; code that reads the field
    // is not. Strip comment lines before matching.
    const code = source
      .split(/\r?\n/)
      .filter((line) => !/^\s*(\/\/|\*|\/\*)/.test(line))
      .join("\n");
    assert.ok(
      !code.includes(field),
      `${field} is retired interpretation-engine output and must not be read here`
    );
  }
});

test("identity, tier, rank, scores and navigation all survive the badge removal", () => {
  const source = fs.readFileSync(componentPath, "utf8");

  // The `eager` prop is a per-row loading hint (see EAGER_LOGO_ROW_LIMIT), not
  // part of the identity contract, so this matches the opening tag rather than
  // the whole element.
  assert.ok(source.includes("<SetIdentity variant=\"compact\" target={target}"), "identity still renders");
  assert.ok(source.includes("<RankBadge rank={tier}"), "tier still renders");
  assert.ok(source.includes("<RankMarker rank={modeRank}"), "rank still renders");
  assert.ok(source.includes('<ScoreCell target={target} modeId="overall" />'), "RIP Score still renders");
  assert.ok(source.includes('<ScoreCell target={target} modeId="financial" />'), "Financial RIP still renders");
  assert.ok(source.includes("href={buildRipLink(target)}"), "row navigation still renders");
  assert.ok(source.includes("getRipMovementForMode"), "rank movement still renders");
});

test("no interpretation severity tone is applied to a row", () => {
  const source = fs.readFileSync(componentPath, "utf8");

  assert.ok(!source.includes("getInterpretationTone"), "severity tone helper must not be used");
  assert.ok(!source.includes("getInterpretationBadgeStyle"), "badge styling must not be used");
  // getTierTone is a DIFFERENT thing and stays: it colours the lead-row edge
  // from the backend tier, which is canonical, not an interpretation verdict.
  assert.ok(source.includes("getTierTone"), "tier tone is canonical and must survive");
});
