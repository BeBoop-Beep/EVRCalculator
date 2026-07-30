// RIP Score Breakdown ("01 · Verdict", set-page Insights) below 1200px, plus
// the Collector Profile and Simulation Results section shells beside it.
//
// PASS 1 flattened the nested cards into a feed but kept two things that put
// the density back: the section's own outer context card, and ONE top-level
// Details dropdown that opened every pillar's secondary block at once.
//
// PASS 2 (this contract) removes both. Below 1200px the section has no card at
// all — it joins the same continuous mobile feed Overview uses — and disclosure
// is the interaction mobile Decision Signals already established: compact rows
// on one column grid, exactly one selected row, exactly one shared detail
// region that updates in place. Overall is selected by default, so the complete
// Opening Outlook is on screen without a tap; it is no longer a large accented
// callout in the default view. Desktop at 1200px+ keeps the card, the dropdown
// and the callout byte-for-byte.
//
// Nothing about the data changed, which is most of what these tests assert:
// same props, same backend fields, same selectors, no new request path, and no
// arithmetic performed in the markup.
//
// RipStatisticsPageClient.jsx cannot be imported outside the Next build (it
// uses extensionless "@/..." specifiers only the bundler resolves), so the
// structural assertions read the rendered JSX source, matching every other
// contract test for this page. The file carries mixed CRLF/LF, so it is
// normalised before any multi-line anchor is searched for.

import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { selectRipScoreBreakdown } from "./ripScoreBreakdownSelector.mjs";
import { selectRipDesirabilityBreakdown } from "../pokemon/set-page/Insights/openingExperienceSelector.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const source = fs
  .readFileSync(path.join(here, "RipStatisticsPageClient.jsx"), "utf8")
  .replace(/\r\n/g, "\n");
const globals = fs
  .readFileSync(path.join(here, "../../app/styles/globals.css"), "utf8")
  .replace(/\r\n/g, "\n");

const between = (text, startToken, endToken) => {
  const start = text.indexOf(startToken);
  assert.ok(start >= 0, `missing ${startToken}`);
  const end = text.indexOf(endToken, start);
  assert.ok(end > start, `missing ${endToken} after ${startToken}`);
  return text.slice(start, end);
};

// The below-desktop presentation: the row, the feed that owns selection, and
// the single detail region's body.
const detailMetric = between(source, "function RipBreakdownDetailMetric(", "// One compact selectable row.");
const compactRow = between(source, "function RipBreakdownCompactRow(", "// The full below-desktop presentation");
const feed = between(source, "function RipBreakdownCompactFeed(", "// The body of the shared detail region");
const detail = between(source, "function RipBreakdownCompactDetail(", "function RipScoreBreakdownModule(");

// The module that mounts both presentations, and the desktop tree that must not
// have moved.
const section = between(source, "function RipScoreBreakdownModule(", "function StatTile(");
const desktopTile = between(source, "function CompactPillarSignalTile(", "// The RIP construction strip");
const desktopGroup = between(source, "function RipCompositionGroup(", "// The \"+\" between the 90% group");

const count = (text, pattern) => (text.match(pattern) || []).length;

// Several assertions below are about what the CODE does, and these components
// are heavily commented — prose like "score / tier / rank" would otherwise read
// as division. Strip line comments and JSX comment blocks first.
const code = (text) =>
  text
    .replace(/\{\/\*[\s\S]*?\*\/\}/g, "")
    .replace(/^\s*\/\/.*$/gm, "");

// ===========================================================================
// A. The mobile outer context card is gone; desktop keeps its card
// ===========================================================================

test("the RIP breakdown draws no context card below desktop", () => {
  const article = between(section, '<article className="set-glass-surface', ">");

  // The card is not "smaller" below desktop — every one of its properties is
  // switched off, so nothing is left to read as an enclosing surface.
  for (const stripped of [
    "max-desk:rounded-none",
    "max-desk:border-0",
    "max-desk:bg-transparent",
    "max-desk:p-0",
    "max-desk:shadow-none",
  ]) {
    assert.ok(article.includes(stripped), `the mobile surface must drop ${stripped.replace("max-desk:", "")}`);
  }
  // The old below-desktop inset is gone rather than merely reduced.
  assert.ok(!article.includes("max-desk:p-3"), "a reduced card inset is still a card inset");
});

test("the 1200px+ card is untouched", () => {
  const article = between(section, '<article className="set-glass-surface', ">");

  assert.ok(article.includes("set-glass-surface"), "desktop keeps the glass surface");
  assert.ok(article.includes("rounded-2xl"), "desktop keeps the radius");
  assert.ok(/(^|\s)border(\s|"|$)/.test(article), "desktop keeps the border");
  assert.ok(article.includes("p-4"), "desktop keeps its base inset");
  assert.ok(article.includes("desk:p-5"), "desktop keeps its 1200px+ inset");
});

test("the utilities are what strip the card, because the globals reset cannot", () => {
  // `important: true` in tailwind.config.js emits every utility as !important,
  // so `p-4`/`border`/`rounded-2xl` outrank the non-important feed reset in
  // globals.css no matter its specificity. The `max-desk:` variants are emitted
  // after the base utilities and are themselves !important, so they are the
  // only thing that can win. If this ever stops being true the reset alone
  // would leave the padding behind and the section would look inset again.
  const config = fs.readFileSync(path.join(here, "../../tailwind.config.js"), "utf8");
  assert.ok(/important:\s*true/.test(config), "the cascade assumption above still holds");
  assert.ok(globals.includes("[data-mobile-feed] .set-glass-surface"), "the feed reset still exists");
  assert.ok(
    !/\[data-mobile-feed\] \.set-glass-surface \{[^}]*!important/.test(globals),
    "the reset is not important, so it cannot strip padding on its own"
  );
});

test("Insights is the continuous mobile feed, with no doubled spacing", () => {
  assert.ok(
    source.includes('<section id="set-detail-insights" data-mobile-feed'),
    "the Insights tab opts into the same feed region Overview uses"
  );
  const tag = between(source, '<section id="set-detail-insights"', ">");
  assert.ok(tag.includes("max-desk:space-y-0"), "the !important space-y must be zeroed or both spacings stack");
  // Overview is the reference and must not have been disturbed by this.
  assert.ok(source.includes('<section id="set-detail-overview" data-mobile-feed'));
});

test("removing the card leaves no empty wrapper behind", () => {
  // Both score-mode arms are now desktop-only wrappers. Below desktop they
  // generate no box at all, so neither can contribute a stray margin above the
  // (already complete) compact feed.
  for (const arm of ["{showsCollectorAppeal ? (", "// RIP Core mode: the three financial cards only"]) {
    const start = section.indexOf(arm);
    assert.ok(start >= 0, `missing ${arm}`);
    const wrapper = section.slice(start, section.indexOf(">", section.indexOf("<div className=", start)));
    assert.ok(/\bhidden\b/.test(wrapper) && wrapper.includes("desk:block"), `${arm} must render nothing below desktop`);
  }
  assert.ok(!section.includes("max-desk:mt-3"), "no below-desktop margin survives on a tree that draws nothing");
});

// ===========================================================================
// B. The Details dropdown is gone below desktop; rows replaced it
// ===========================================================================

test("no Details dropdown is operable below desktop", () => {
  const start = section.indexOf("aria-expanded={detailsExpanded}");
  assert.ok(start >= 0, "the desktop control still exists");
  const control = section.slice(section.lastIndexOf("<button", start), section.indexOf("</button>", start));

  assert.ok(control.includes("max-desk:hidden"), "the control is display:none below 1200px");
  assert.ok(!/(^|[\s"])desk:hidden/.test(control), "no compact mobile variant of the label may remain");
  assert.ok(!control.includes(">Details<"), "the compact mobile label is gone with the control");
  // Its state must not reach the below-desktop tree at all.
  assert.ok(!feed.includes("detailsExpanded"), "the feed does not read the dropdown's state");
  assert.ok(!compactRow.includes("detailsExpanded"));
  assert.ok(!detail.includes("detailsExpanded"));
  assert.ok(
    !/<RipBreakdownCompactFeed[^>]*detailsExpanded/.test(section),
    "the dropdown's state is not passed into the compact tree"
  );
});

test("the desktop dropdown keeps its label, chevron and semantics", () => {
  const start = section.indexOf("aria-expanded={detailsExpanded}");
  const control = section.slice(section.lastIndexOf("<button", start), section.indexOf("</button>", start));

  assert.ok(control.includes('type="button"'));
  assert.ok(control.includes('{detailsExpanded ? "Hide Details" : "Show Details"}'));
  assert.ok(control.includes('aria-label={detailsExpanded ? "Hide RIP Score Breakdown details"'));
  assert.ok(control.includes('${detailsExpanded ? "rotate-180" : ""}'), "the chevron still flips when expanded");
  assert.ok(section.includes("detailsExpanded={detailsExpanded}"), "it still drives the desktop tiles");
});

test("the old expanded-details block is not mounted alongside the new one", () => {
  // Pass 1's per-pillar compact row and appeal summary are gone, not merely
  // unused — two disclosure systems on one screen is the defect.
  for (const retired of [
    "function RipPillarCompactRow(",
    "function RipCollectorAppealCompact(",
    "function RipCompositionCompactHeading(",
    "data-rip-pillar-compact-detail",
    "data-rip-collector-appeal-compact",
  ]) {
    assert.ok(!source.includes(retired), `${retired} belonged to the dropdown model and must be gone`);
  }
});

test("no per-pillar accordion was introduced in its place", () => {
  // Every row points at the SAME region id. A per-pillar accordion would give
  // each row its own.
  assert.equal(count(code(compactRow), /aria-controls=/g), 1);
  assert.ok(compactRow.includes("aria-controls={detailRegionId}"));
  assert.ok(!compactRow.includes("useState"), "a row owns no open/closed state of its own");
  assert.ok(!compactRow.includes("<details"));
  assert.equal(count(code(feed), /useId\(\)/g), 1, "one region id for the whole list");
});

// ===========================================================================
// C. Exactly one shared detail region, defaulting to Overall
// ===========================================================================

test("exactly one shared detail region is rendered", () => {
  assert.equal(count(code(feed), /data-rip-breakdown-detail/g), 1);
  assert.equal(count(code(source), /data-rip-breakdown-detail/g), 1, "and only one on the page");
  const region = between(feed, "id={detailRegionId}", "</div>");
  assert.ok(region.includes('aria-live="polite"'), "content changes are announced politely");
  assert.ok(region.includes("id={detailRegionId}"), "the rows' aria-controls resolves to it");
  // One restrained treatment, not another context card. The rule itself comes
  // from the shared COMPACT_DETAIL_CLASS so the RIP, Drivers and Metrics detail
  // regions cannot drift apart.
  assert.ok(!/rounded-(?:lg|xl|2xl|3xl)/.test(region), "the detail region must not draw a card");
  assert.ok(!region.includes("set-glass"), "no glass surface may wrap the detail region");
  assert.ok(region.includes("COMPACT_DETAIL_CLASS"), "the shared detail treatment is used");
  const detailClass = between(source, "const COMPACT_DETAIL_CLASS =", ";");
  assert.ok(detailClass.includes("border-l-2"), "a rule, not a box");
  assert.ok(detailClass.includes("compact-row-detail"), "it continues the selected row's accent rail");
});

test("Overall is selected by default and only one group ever renders", () => {
  assert.ok(feed.includes("useState(RIP_OVERALL_ROW_KEY)"), "Overall is the initial selection");
  // The detail body returns early per group: it is structurally incapable of
  // showing two groups at once.
  assert.ok(detail.includes("if (row.key === RIP_OVERALL_ROW_KEY) {"));
  assert.ok(detail.includes("if (row.key === RIP_APPEAL_ROW_KEY) {"));
  assert.ok(!/\{rows\.map/.test(code(detail)), "the detail region must never iterate every row");
});

test("the selection survives unrelated rerenders and a mode round trip", () => {
  // State lives in the feed, so a parent rerender (a poll settling, a sibling
  // fetch resolving) cannot reset it — there is no effect that writes it and no
  // key that would remount the component.
  assert.ok(feed.includes("const [selectedKey, setSelectedKey] = useState("));
  assert.ok(!feed.includes("useEffect"), "nothing resets the selection on rerender");
  // Bounded to the element's own tag: an unbounded `[\s\S]*?` would run past
  // `/>` and match the desktop tree's per-tile React keys.
  assert.ok(!/<RipBreakdownCompactFeed[^>]*\bkey=/.test(section), "no key may remount the feed");

  // The feed is mounted ONCE, outside both score-mode arms, so switching
  // RIP Score <-> RIP Core cannot unmount it.
  assert.equal(count(code(section), /<RipBreakdownCompactFeed/g), 1);
  assert.ok(
    section.indexOf("<RipBreakdownCompactFeed") < section.indexOf("{showsCollectorAppeal ? ("),
    "the feed is mounted before either mode arm, not inside one"
  );
  // A row that the active mode removed falls back for RENDER only, so
  // switching back restores what was selected.
  assert.ok(feed.includes("rows.find((row) => row.key === selectedKey) || rows[0]"));
  assert.ok(!/setSelectedKey\(RIP_OVERALL_ROW_KEY\)/.test(feed), "the fallback must not overwrite the selection");
});

test("re-activating the selected row keeps it selected", () => {
  // Decision Signals toggles off; here collapsing is explicitly not required,
  // and an empty region would hide the outlook. onSelect sets, never clears.
  assert.ok(compactRow.includes("onClick={() => onSelect(row.key)}"));
  assert.ok(!compactRow.includes("previous === "), "no toggle-to-null on the selected row");
  assert.ok(!feed.includes("setSelectedKey(null)"));
});

// ===========================================================================
// D. The five rows, their scan fields and their details
// ===========================================================================

test("the five rows are Overall, the three pillars and Collector Appeal", () => {
  assert.ok(feed.includes("key: RIP_OVERALL_ROW_KEY"));
  assert.ok(feed.includes('label: "Overall"'));
  assert.ok(feed.includes("...pillars.map((pillar) => ({"), "Profit/Safety/Stability come from the same props as desktop");
  assert.ok(feed.includes("key: RIP_APPEAL_ROW_KEY"));
  assert.ok(feed.includes('label: "Collector Appeal"'));
  // The 10% term is not a term of RIP Core, so RIP Core mode builds no row for
  // it — not greyed, not emptied, not left as a gap.
  assert.ok(feed.includes("...(showsCollectorAppeal && collectorAppeal"));
});

test("every row states name, score, tier and rank on one shared column grid", () => {
  for (const field of ["{row.label}", "{row.scoreText}", "row.rankTier", "roundedRank"]) {
    assert.ok(compactRow.includes(field), `${field} must render on the row`);
  }
  // One grid definition, used by the rows AND by the column header, so every
  // score, tier and rank in the section lines up.
  assert.ok(source.includes('const RIP_COMPACT_GRID = "grid-cols-[minmax(0,1fr)_3rem_3.5rem_2.5rem]"'));
  assert.ok(compactRow.includes("${RIP_COMPACT_GRID}"));
  assert.ok(feed.includes("${RIP_COMPACT_GRID}"), "the column header shares the row grid");
  assert.equal(count(code(feed) + code(compactRow), /grid-cols-\[/g), 0, "no row may declare a private grid");
  // Alignment: scores and ranks right, tier centred, name track is the only
  // flexible one.
  assert.ok(compactRow.includes('className="text-right text-sm font-semibold leading-none tabular-nums'));
  assert.ok(compactRow.includes('<span className="flex justify-center">'));
});

test("the Overall row carries the overall score, tier and rank", () => {
  const overall = between(feed, "key: RIP_OVERALL_ROW_KEY", "...pillars.map");
  assert.ok(overall.includes("scoreText: formatRawScore(score)"));
  assert.ok(overall.includes("rankTier: rankTier"));
  assert.ok(overall.includes("rankValue: overallRank"));
  assert.ok(overall.includes("rankTitle: overallRankTitle"));
});

test("each pillar row carries its score, tier, rank and short verdict", () => {
  const pillarRows = between(feed, "...pillars.map((pillar) => ({", "...(showsCollectorAppeal");
  assert.ok(pillarRows.includes("label: pillar.title"));
  assert.ok(pillarRows.includes("scoreText: formatScore(pillar.score)"));
  assert.ok(pillarRows.includes("rankTier: pillar.rankTier"));
  assert.ok(pillarRows.includes("rankValue: toNumber(pillar.rankValue)"));
  assert.ok(pillarRows.includes("secondary: pillar.highlight"), "the backend's short verdict phrase stays on the row");
  assert.ok(compactRow.includes("{row.secondary}"));
  // Compact secondary text, not a second primary line.
  const secondary = between(compactRow, "data-rip-breakdown-row-secondary", ">");
  assert.ok(secondary.includes("text-[10px]") && secondary.includes("text-[var(--text-secondary)]"));
});

test("the Collector Appeal row states its 10% contribution on the row itself", () => {
  const appealRow = between(feed, "key: RIP_APPEAL_ROW_KEY", "]");
  assert.ok(appealRow.includes("scoreText: collectorAppeal.available ? collectorAppeal.scoreLabel"));
  assert.ok(appealRow.includes("collectorAppeal.tier"));
  assert.ok(appealRow.includes("toNumber(collectorAppeal.rank)"));
  assert.ok(
    appealRow.includes("collectorAppeal.weightLabel ? `${collectorAppeal.weightLabel} of RIP Score`"),
    "the weight label is the backend's, not a hardcoded 10%"
  );
  assert.ok(!/secondary:\s*"10%/.test(appealRow), "the percentage is never hardcoded in the markup");
});

test("selecting Overall shows the complete Opening Outlook plus the composition", () => {
  const overall = between(detail, "if (row.key === RIP_OVERALL_ROW_KEY) {", "if (row.key === RIP_APPEAL_ROW_KEY) {");

  // Canonical text, complete, with the same fallback convention as desktop.
  assert.ok(overall.includes('{openingOutlook || "No opening outlook is available for this set yet."}'));
  assert.ok(!overall.includes("line-clamp"), "the outlook is not truncated");
  assert.ok(!overall.includes("<details"));
  assert.ok(overall.includes("Opening Outlook"), "the label says what it is");
  assert.ok(overall.includes("<InfoPopover text={RIP_OUTLOOK_INFO_TEXT} />"), "the info tooltip is kept");
  // The 90/10 composition the group headers used to carry is preserved here,
  // from the backend's own weight labels.
  assert.ok(overall.includes("data-rip-breakdown-composition"));
  assert.ok(overall.includes("`RIP Core ${coreWeightLabel}`"));
  assert.ok(overall.includes("coreWeightsCaption"));
  assert.ok(overall.includes("`Collector Appeal ${collectorAppeal.weightLabel}`"));
});

test("Opening Outlook is compact here, not the accented callout", () => {
  // The component comments name the treatments it deliberately does NOT use, so
  // these "must not contain" probes read stripped code rather than prose.
  const overall = code(between(detail, "if (row.key === RIP_OVERALL_ROW_KEY) {", "if (row.key === RIP_APPEAL_ROW_KEY) {"));

  assert.ok(!overall.includes("outlookWash"), "no wash — that was the large callout treatment");
  assert.ok(!overall.includes("rip-outlook-callout"), "no accented callout below desktop");
  assert.ok(!/rounded/.test(overall), "a rounded container would read as a highlighted box");
  assert.ok(!/\bpx-3\.5|\bpy-2\.5|\bpx-4\b/.test(overall), "the callout's padding does not come with it");
  // Smaller supporting typography than the desktop callout's text-sm body.
  assert.ok(overall.includes("text-xs font-medium leading-snug"), "supporting type, still readable");
  assert.ok(!overall.includes("text-sm"), "the outlook body steps down below desktop");
});

test("selecting Profit, Safety or Stability shows that pillar's existing details", () => {
  const pillar = detail.slice(detail.indexOf("const pillar = row.pillar;"));

  assert.ok(pillar.includes("<InterpretationBadge"), "the coarse state badge survives");
  assert.ok(pillar.includes("{pillar.highlight}"), "the short interpretation survives");
  assert.ok(pillar.includes("{`${Math.round(parsedWeight * 100)}% of RIP Core`}"), "the weight survives");
  assert.ok(pillar.includes("`${parsedContribution.toFixed(1)} pts`"), "the contribution survives");
  assert.ok(pillar.includes("infoText={RIP_CONTRIBUTION_INFO_TEXT}"));
  // EVERY supporting metric row the desktop tile renders, from the same array
  // — Pack Market Price, Expected Value, Chance to Beat Pack Cost and the rest
  // for Profit; the Safety and Stability arrays likewise.
  assert.ok(pillar.includes("{metrics.map((metric) => ("));
  assert.ok(pillar.includes("const metrics = pillar.metrics || [];"));
  for (const passthrough of ["label={metric.label}", "value={metric.value}", "trend={metric.trend}", "content={metric.content}"]) {
    assert.ok(pillar.includes(passthrough), `${passthrough} must reach the detail metric`);
  }
  assert.ok(pillar.includes("metric.infoText || getMetricTooltip(metric.label)"), "the per-metric tooltip survives");
  assert.ok(!/slice\(0,|\.filter\(/.test(pillar), "no metric may be dropped to hit a height target");
});

test("selecting Collector Appeal shows its weight, rank and description", () => {
  const appeal = between(detail, "if (row.key === RIP_APPEAL_ROW_KEY) {", "const pillar = row.pillar;");

  assert.ok(appeal.includes("{collectorAppeal.weightLabel}"), "the contribution percentage");
  assert.ok(appeal.includes("{collectorAppeal.rankLabel}"), "the denominated rank");
  assert.ok(
    appeal.includes("Roster desirability translated through this set&apos;s modeled opening paths."),
    "the complete existing description"
  );
  // Never a fake 0 and never a fake tier when the term is missing.
  assert.ok(appeal.includes("{collectorAppeal?.unavailableReason ||"));
  assert.ok(appeal.includes("Collector Appeal (CA7) is unavailable for this set"));
  assert.ok(!/>\s*0\s*</.test(appeal));
});

test("the weighted contribution term is not printed below desktop", () => {
  // Approved removal. "Opening Desirability x 10% = 9.6 pts" invited the reader
  // to check arithmetic they cannot: the two scores on this screen are
  // cohort-relative presentations that do not visibly sum with that model term.
  // The WEIGHT still carries the same meaning, on the row and in the detail.
  // Stripped, because the component's comment EXPLAINS the removal by naming
  // the field it no longer renders.
  const appeal = code(between(detail, "if (row.key === RIP_APPEAL_ROW_KEY) {", "const pillar = row.pillar;"));
  assert.ok(!appeal.includes("contributionLabel"), "no weighted point term below desktop");
  assert.ok(!appeal.includes("Contribution to RIP Score"), "and no row labelled as one");
  assert.ok(appeal.includes("{collectorAppeal.weightLabel}"), "the 10% weight is what remains");
  assert.ok(feed.includes("`${collectorAppeal.weightLabel} of RIP Score`"), "and the row still states it");

  // Nothing was recomputed and nothing was deleted upstream: the selector still
  // produces the field and 1200px+ still renders it.
  assert.ok(section.includes("{collectorAppeal.contributionLabel}"), "desktop keeps the contribution line");
  assert.ok(section.includes("data-rip-collector-appeal-contribution"));
});

// ===========================================================================
// E. The compact overall score summary
// ===========================================================================

test("the summary keeps mode, score, /100, tier, rank and verdict", () => {
  const summary = between(feed, "data-rip-compact-summary", "Core breakdown");

  assert.ok(summary.includes("{formatRawScore(score)}"), "the score");
  assert.ok(summary.includes(">/100<"), "the denominator");
  assert.ok(summary.includes('<RankBadge rank={rankTier} format="tier" size="compact" subtle'), "the tier");
  assert.ok(summary.includes("Rank #{Math.round(overallRank)}"), "the rank");
  assert.ok(summary.includes("data-rip-compact-summary-verdict"), "the verdict phrase");
  assert.ok(summary.includes("{verdict}"));
  assert.ok(summary.includes("<InfoPopover text={explanation} />"), "the overall explanation stays reachable");
  // The mode control is mounted once for the whole section, above this.
  assert.equal(count(code(section), /<RipScoreModeToggle/g), 1);
  assert.ok(section.indexOf("<RipScoreModeToggle") < section.indexOf("<RipBreakdownCompactFeed"));
});

test("the summary reads as one line, not five badges", () => {
  const summary = between(feed, "data-rip-compact-summary", "Core breakdown");

  // The score is the only strong element; tier/rank/verdict are secondary.
  assert.ok(summary.includes("text-3xl font-semibold"), "the score stays the strongest element");
  assert.ok(count(summary, /text-\[11px\]/g) >= 3, "tier, rank and verdict all sit at supporting size");

  // The verdict is a thin tier-toned rule plus text — never a filled pill, and
  // never larger than the tier and rank beside it.
  const verdictSpan = between(summary, "data-rip-compact-summary-verdict", ">");
  assert.ok(verdictSpan.includes("border-l") && verdictSpan.includes("pl-2"), "a rule, not a pill");
  assert.ok(!/rounded/.test(verdictSpan), "the verdict must not be a rounded pill");
  assert.ok(!/\bbg-/.test(verdictSpan), "the verdict must not carry a fill");
  assert.ok(!/\bpx-3|\bpy-1\.5|\bpx-3\.5/.test(verdictSpan), "the pill's padding does not come with it");
  assert.ok(!/uppercase/.test(verdictSpan), "no shouting label");
  assert.ok(verdictSpan.includes("min-w-0"), "it may wrap on a narrow phone rather than overflow");

  // Exactly one outlined chip on the line — the tier.
  assert.equal(count(code(summary), /<RankBadge/g), 1);
  assert.ok(!summary.includes("<InterpretationBadge"), "no second outlined chip competes with the tier");
  assert.ok(!summary.includes("<HeroScoreBadges"), "the desktop badge row is not reused below desktop");
});

test("the desktop score row and its badge row are unchanged and desktop only", () => {
  const desktopSummary = between(section, '<div className="mt-3 hidden min-w-0 flex-wrap', "data-insights-opening-outlook");
  assert.ok(
    desktopSummary.includes("<HeroScoreBadges rank={rankValue} tier={rankTier} cohortSize={cohortSize} interpretation={verdict} />")
  );
  assert.ok(desktopSummary.includes("text-4xl"), "desktop keeps the larger figure");
  assert.ok(desktopSummary.includes("{formatRawScore(score)}"), "desktop keeps the same formatted score");
  const wrapper = between(section, '<div className="mt-3 hidden min-w-0 flex-wrap', ">");
  assert.ok(wrapper.includes("desk:flex"), "the desktop summary is desktop only");
  const callout = between(section, "data-insights-opening-outlook", "style=");
  assert.ok(/\bhidden\b/.test(callout) && callout.includes("desk:block"), "the accented callout is desktop only");
});

// ===========================================================================
// F. Layout, touch targets and keyboard
// ===========================================================================

test("tier pills stay on one line and ranks never touch the right edge", () => {
  assert.ok(compactRow.includes('size="compact"'), "the compact pill is what fits '#' + tier on one line");
  assert.ok(compactRow.includes("subtle"));
  // The row reserves symmetric padding: the selected wash runs the full row and
  // the rank stops short of the edge. A negative margin here is the bug that
  // made a selected row bleed into the gutter on Overview.
  assert.ok(compactRow.includes("pl-1.5 pr-1.5"));
  assert.ok(!/-ml-|-mr-/.test(compactRow), "no negative margin may slide the row into the gutter");
  assert.ok(compactRow.includes("w-full"), "the selected background spans the row");
});

test("nothing can overflow horizontally at 320px", () => {
  // The name track is the only flexible one and it truncates; the three numeric
  // tracks are fixed and total 9rem, leaving the name ~108px at 320px.
  assert.ok(compactRow.includes('<span className="min-w-0">'));
  assert.ok(count(compactRow, /truncate/g) >= 2, "both the name and its secondary line truncate");
  assert.ok(feed.includes('className="min-w-0'), "the feed shrinks with its column");
  assert.ok(detail.includes('className="min-w-0'));
  assert.ok(detailMetric.includes("truncate"), "long metric labels truncate rather than push the value out");
  assert.ok(detailMetric.includes("flex-none"), "the value never shrinks below its content");
  assert.ok(!/\bw-\[|\bmin-w-\[\d/.test(compactRow), "no fixed pixel width may exceed a 320px viewport");
});

test("rows keep a 44px touch target and are fully keyboard operable", () => {
  assert.ok(compactRow.includes("<button"), "a real button, so Enter and Space come free");
  assert.ok(compactRow.includes('type="button"'));
  assert.ok(compactRow.includes("min-h-11"), "44px minimum height");
  assert.ok(compactRow.includes("focus-visible:ring-2"), "focus stays visible");
  assert.ok(!compactRow.includes("tabIndex={-1}"), "every row stays in the tab order");
  assert.ok(compactRow.includes("aria-expanded={isSelected}"));
  // Selection changes a colour, never a column position: the edge is a border
  // every row reserves as transparent. Both states now come from the shared
  // constants, so the three compact lists select identically.
  assert.ok(compactRow.includes("border-l-2"));
  assert.ok(compactRow.includes("COMPACT_ROW_SELECTED_CLASS"));
  assert.ok(compactRow.includes("COMPACT_ROW_IDLE_CLASS"));
  const selectedClass = between(source, "const COMPACT_ROW_SELECTED_CLASS =", ";");
  const idleClass = between(source, "const COMPACT_ROW_IDLE_CLASS =", ";");
  assert.ok(idleClass.includes("border-l-transparent"));
  assert.ok(selectedClass.includes("border-l-[var(--accent)]"));
});

test("tier and direction are communicated in text, not by colour alone", () => {
  assert.ok(compactRow.includes('aria-label="Rank unavailable"'));
  assert.ok(compactRow.includes('aria-label="Tier unavailable"'));
  assert.ok(compactRow.includes('<span className="sr-only">{`Rank ${roundedRank}`}</span>'));
  assert.ok(compactRow.includes("title={row.rankTitle}"), "the cohort denominator stays in the tooltip");
  assert.ok(source.includes("of ${Math.round(parsedCohort)} ranked sets"));
});

test("a missing score, tier or rank degrades independently and invents nothing", () => {
  assert.ok(compactRow.includes("roundedRank === null ? ("), "a missing rank renders as a dash");
  assert.ok(compactRow.includes("{row.rankTier ? ("), "a missing tier renders as a dash, not a fake tier");
  assert.ok(!/rankTier\s*\|\|\s*"/.test(compactRow), "no substituted tier");
  assert.ok(feed.includes('collectorAppeal.available ? collectorAppeal.scoreLabel : "—"'));
  assert.ok(!/>\s*0\s*</.test(feed), "a missing term never renders as 0");
});

// ===========================================================================
// G. No request or calculation changes
// ===========================================================================

test("the redesign introduces no request path and performs no arithmetic on a score", () => {
  for (const [name, tree] of [
    ["the section", section],
    ["the feed", feed],
    ["the row", compactRow],
    ["the detail region", detail],
  ].map(([name, tree]) => [name, code(tree)])) {
    assert.ok(!/\bfetch\(|axios|useSWR|getPokemonSet/.test(tree), `${name} adds no request path`);
    assert.ok(!/\bscore\s*[*/+]|\*\s*score\b/.test(tree), `${name} performs no arithmetic on a score`);
    assert.ok(!/\*\s*0\.1\b|\*\s*0\.9\b/.test(tree), `${name} must not apply a blend weight in the markup`);
    assert.ok(!/relativeScore\s*\*/.test(tree), `${name} must not derive anything from a relative score`);
    assert.ok(!tree.includes("sort("), `${name} must not re-order what the backend ranked`);
  }
  // Weight -> percent and contribution -> "N pts" are the same two reads the
  // desktop tile already performed, on the same backend fields.
  assert.ok(desktopTile.includes("{`${Math.round(parsedWeight * 100)}% of RIP Core`}"));
  assert.ok(detail.includes("{`${Math.round(parsedWeight * 100)}% of RIP Core`}"));
  assert.ok(desktopTile.includes("parsedContribution.toFixed(1)"));
  assert.ok(detail.includes("parsedContribution.toFixed(1)"));
});

test("both presentations render from the same props, and only one at a time", () => {
  // Same pillar objects, same collectorAppeal object — no second view model.
  assert.ok(section.includes("pillars={pillars}"));
  assert.ok(section.includes("collectorAppeal={collectorAppeal}"));
  assert.ok(desktopTile.includes("metrics = []"), "desktop reads the same metrics array");
  // The compact tree is below-desktop only and the desktop tree desktop only,
  // so assistive technology reaches exactly one.
  assert.ok(section.includes('<div className="mt-3 min-w-0 desk:hidden">'));
  assert.ok(feed.includes('data-rip-breakdown-compact className="min-w-0 desk:hidden"'));
  assert.ok(!/(^|[\s"`])sm:/.test(code(feed)), "no band-scoped style max-desk cannot outrank");
  assert.ok(!/(^|[\s"`])sm:/.test(code(compactRow)));
});

test("the 1200px+ composition is untouched", () => {
  assert.ok(section.includes('eyebrow="RIP Core"'));
  assert.ok(section.includes('tone="appeal"'));
  assert.ok(section.includes("<RipCompositionJoin />"));
  assert.ok(section.includes("<CompactPillarSignalTile key={`rip-pillar:${pillar.title}`} {...pillar} detailsExpanded={detailsExpanded} />"));
  assert.ok(section.includes("sm:grid-cols-3"), "the desktop three-up grid stays");
  assert.ok(desktopGroup.includes("rounded-xl border"), "the desktop group keeps its card");
  assert.ok(desktopTile.includes("set-glass-inner"), "the desktop tile keeps its inner surface");
  assert.ok(section.includes("data-rip-collector-appeal-contribution"), "the desktop 10% contribution line stays");
});

// ===========================================================================
// H. Section shells — Collector Profile and Simulation Results
// ===========================================================================

test("the Collector Profile outer card is removed below desktop and kept on desktop", () => {
  assert.ok(
    source.includes("const SECTION_CARD_MOBILE_FLUSH_CLASS ="),
    "one definition of the flush treatment, shared by the sections that opted in"
  );
  const flush = between(source, "const SECTION_CARD_MOBILE_FLUSH_CLASS =", ";");
  for (const stripped of [
    "max-desk:rounded-none",
    "max-desk:border-0",
    "max-desk:bg-transparent",
    "max-desk:p-0",
    "max-desk:shadow-none",
  ]) {
    assert.ok(flush.includes(stripped), `the flush treatment must drop ${stripped.replace("max-desk:", "")}`);
  }

  // Opt-in per caller: SectionCard also renders on Explore, the Cards tab and
  // the expert layouts, which keep their cards at every width.
  assert.ok(source.includes("mobileFlush = false"), "the default is unchanged");
  assert.ok(source.includes('mobileFlush ? SECTION_CARD_MOBILE_FLUSH_CLASS : ""'));
  const collectorCard = between(source, 'eyebrow="02 · Collector Profile"', "</SectionCard>");
  assert.ok(collectorCard.includes("mobileFlush"), "Collector Profile opted in");

  // A flush card states its 1200px+ inset with desk:, not sm:. `max-desk:`
  // utilities are emitted BEFORE `sm:` and both are !important, so an
  // sm-scoped inset wins back 640-1199px and the card still looks inset on a
  // tablet — the one band where the reset silently does nothing.
  assert.ok(source.includes('mobileFlush ? "p-4 desk:p-5" : "p-4 sm:p-5"'));

  // Desktop is untouched: the same article, radius, border and inset. Callers
  // that keep their card still get p-4 sm:p-5.
  const sectionCard = between(source, "function SectionCard(", "</article>");
  assert.ok(sectionCard.includes("rounded-2xl border border-[var(--border-subtle)] ${insetClass}"));
  assert.ok(sectionCard.includes('"set-glass-surface w-full max-w-full min-w-0"'));
});

test("all Collector Profile content survives the shell cleanup", () => {
  const collector = between(source, "function CollectorProfileSection(", "const TOP_CARD_IMAGE_CONTAINER_CLASS");

  assert.ok(collector.includes("data-collector-profile-flow"), "the three-stage flow strip stays");
  assert.ok(collector.includes('label="Set Desirability"'));
  assert.ok(collector.includes('label="Collector Appeal"'));
  assert.ok(collector.includes('label="RIP Score Contribution"'));
  assert.ok(collector.includes('label: "Roster Appeal"'));
  assert.ok(collector.includes('label: "Opening Paths"'));
  assert.ok(collector.includes("<CollectorRosterAppealPanel"));
  assert.ok(collector.includes("<CollectorOpeningPathsPanel"));
  assert.ok(collector.includes("<SectionViewTabs"), "the view control is unchanged");
  // Every deep-link anchor still resolves.
  for (const anchor of [
    "set-detail-set-desirability",
    "set-detail-desirability-evidence",
    "set-detail-desirability-proof",
    "set-detail-desirability-validation",
    "set-detail-card-desirability-price",
    "set-detail-opening-experience",
  ]) {
    assert.ok(collector.includes(anchor), `${anchor} must still resolve`);
  }
  // No internal redesign in this pass.
  assert.ok(!collector.includes("max-desk:grid-cols"), "the internal metric presentation is untouched");
});

test("the Simulation Results outer card is removed below desktop and kept on desktop", () => {
  const article = between(
    source,
    '"set-glass-surface w-full max-w-full min-w-0 rounded-2xl border p-4 desk:p-5",',
    "].filter"
  );

  assert.ok(article.includes("SECTION_CARD_MOBILE_FLUSH_CLASS"), "it reuses the one shared flush treatment");
  assert.ok(article.includes("openingOutcomesUsesExpandedLayout"), "the expanded-layout min-height is unchanged");
  // Same trap as SectionCard: an sm-scoped inset would survive across the whole
  // tablet band. desk:p-5 is identical at 1200px+.
  assert.ok(
    !source.includes('rounded-2xl border p-4 sm:p-5",'),
    "the Simulation Results card must not state its inset at the sm breakpoint"
  );
});

test("every simulation view and its supporting copy survive the shell cleanup", () => {
  const simulation = between(source, "<SectionEyebrow>03 · Raw evidence</SectionEyebrow>", "</SectionErrorBoundary>");

  assert.ok(simulation.includes(">Simulation Results</h2>"), "the title stays");
  assert.ok(simulation.includes("The raw evidence — full simulation outputs behind the score."), "the description stays");
  assert.ok(simulation.includes("<InfoPopover text={SIMULATION_RESULTS_INFO_TEXT} />"));
  for (const view of [
    'value: "outcome-distribution", label: "Outcome Distribution"',
    'value: "historical-trend", label: "Opening Profit vs Cost"',
    'value: "simulation-drivers", label: "Simulation Drivers"',
    'value: "value-contribution", label: "Value Structure"',
    'value: "pack-breakdown", label: "Pack Paths"',
    'value: "simulation-metrics", label: "Metrics"',
  ]) {
    assert.ok(simulation.includes(view), `${view} must remain selectable`);
  }
  for (const panel of [
    "set-detail-outcome-distribution",
    "set-detail-opening-performance-cost",
    "set-detail-simulation-drivers",
    "set-detail-value-structure",
    "set-detail-pack-breakdown",
    "set-detail-simulation-metrics",
  ]) {
    assert.ok(simulation.includes(panel), `${panel} must still render`);
  }
  // Chart interactions and data are untouched.
  assert.ok(simulation.includes("<RipDistributionChart bins={distributionBins}"));
  assert.ok(simulation.includes("<PackValueHistoryChart"));
  assert.ok(simulation.includes("<SimulationMetricsContent"));
});

test("desktop shells are unchanged for every section", () => {
  // The whole cleanup is expressed in max-desk: utilities and a media-queried
  // reset, so no rule can reach 1200px+.
  const flush = between(source, "const SECTION_CARD_MOBILE_FLUSH_CLASS =", ";");
  assert.ok(!/(^|[\s"`])desk:/.test(flush), "the flush treatment declares no desktop-scoped style");
  assert.ok(/max-desk:/.test(flush), "the flush treatment is below-desktop only");
  const feedBlock = globals.slice(globals.indexOf("@media (max-width: 1199.98px) {"));
  assert.ok(feedBlock.includes("[data-mobile-feed] .set-glass-surface"), "the reset is inside the mobile media query");
});

// ===========================================================================
// I. Values unchanged — the selectors behind both presentations
// ===========================================================================

const RIP_FIXTURE = {
  score: 64.1,
  relativeScore: 66.8,
  rank: 11,
  tier: "C",
  cohortSize: 140,
  interpretation: { label: "Elite but swingy", summary: "Big ceiling, rough misses." },
  financialRip: {
    components: {
      profit: { score: 22.5, rank: 4, tier: "A", cohortSize: 140, weight: 0.6, contribution: 13.5 },
      safety: { score: 21.5, rank: 5, tier: "B", cohortSize: 140, weight: 0.25, contribution: 5.375 },
      stability: { score: 15.6, rank: 18, tier: "F", cohortSize: 140, weight: 0.15, contribution: 2.34 },
    },
  },
};

test("the three pillar values both presentations display are unchanged", () => {
  const { rows, sourceUsed, fallbackUsed } = selectRipScoreBreakdown(RIP_FIXTURE, {});

  assert.deepEqual(
    rows.map((row) => [row.title, row.score, row.rankValue, row.rankTier, row.weight, row.contribution]),
    [
      ["Profit", 22.5, 4, "A", 0.6, 13.5],
      ["Safety", 21.5, 5, "B", 0.25, 5.375],
      ["Stability", 15.6, 18, "F", 0.15, 2.34],
    ]
  );
  assert.equal(sourceUsed, "rip.financialRip.components");
  assert.equal(fallbackUsed, false);
});

test("the 90/10 composition and the Collector Appeal term are unchanged", () => {
  const composition = selectRipDesirabilityBreakdown(
    RIP_FIXTURE,
    { score: 63.4, relativeScore: 65.0, rank: 12, tier: "C", cohortSize: 140 },
    { score: 96.1, rank: 1, tier: "S", rankedSetCount: 140 },
    { collectorAppeal: { score: 96.1, rank: 1, tier: "S", cohortSize: 140 } }
  );

  assert.equal(composition.financialRip.weightLabel, "90%");
  assert.equal(composition.openingDesirability.weightLabel, "10%");
  // The 10% term reads the ABSOLUTE CA7 score, never a cohort-relative one.
  assert.equal(composition.openingDesirability.scoreLabel, "96.1");
  assert.equal(composition.openingDesirability.rank, 1);
  assert.equal(composition.openingDesirability.tier, "S");
  assert.equal(composition.openingDesirability.contributionLabel, "Opening Desirability × 10% = 9.6 pts");
});
