// RIP Score Breakdown — the "01 · Verdict" section on the set-page Insights tab.
//
// The section was simplified to a user-facing verdict: score → what it means →
// the three pillars. The formula-construction panel ("How Overall RIP Is Built"
// with its contribution points, the 90/10 blend line and the effective final
// weights) explained how the number is assembled rather than what it means, so
// it is gone from the UI. None of the arithmetic changed: the same backend
// contract, the same selectors, the same scores/ranks/tiers/weights.
//
// The component lives inside RipStatisticsPageClient.jsx and is not exported —
// and that file cannot be imported outside the Next build (it uses extensionless
// "@/..." specifiers that only the bundler resolves), so structural assertions
// here read the rendered JSX source, matching the existing contract tests for
// this page. The value assertions below run the real selectors.

import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { selectRipScoreBreakdown } from "./ripScoreBreakdownSelector.mjs";
import { RIP_CORE_MODE, RIP_SCORE_MODE, selectRipHeroScoreMode } from "./ripHeroScoreMode.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const clientPath = path.join(here, "RipStatisticsPageClient.jsx");
const source = fs.readFileSync(clientPath, "utf8").replace(/\r\n/g, "\n");

// The rendered body of RipScoreBreakdownModule, in source order.
function verdictSection() {
  const start = source.indexOf("function RipScoreBreakdownModule");
  const end = source.indexOf("function StatTile", start);
  assert.ok(start >= 0 && end > start, "RipScoreBreakdownModule must exist");
  return source.slice(start, end);
}

function orderOf(section, marker) {
  const index = section.indexOf(marker);
  assert.ok(index >= 0, `expected the verdict section to contain ${marker}`);
  return index;
}

// ---------------------------------------------------------------------------
// Removed content
// ---------------------------------------------------------------------------

test("the redundant verdict subtitle is gone and the title block stays", () => {
  const section = verdictSection();

  assert.ok(
    !source.includes("The verdict — how this set scores and why."),
    "the subtitle restated the heading and was removed, not replaced"
  );
  assert.ok(section.includes("<SectionEyebrow>01 · Verdict</SectionEyebrow>"));
  assert.ok(section.includes(">RIP Score Breakdown</h2>"));
});

test("the retired flat construction panel does not come back", () => {
  const section = verdictSection();

  // The panel that was retired was a FLAT formula readout: a "How Overall RIP
  // Is Built" table of contribution points and effective final weights, sitting
  // below the pillars and shown in both score modes. That stays gone.
  //
  // What replaced it is not that panel: it is the two-level COMPOSITION the
  // score actually has (90% RIP Core over Profit/Safety/Stability, plus a 10%
  // Collector Appeal term), which is the structure of the score rather than a
  // transcript of its arithmetic. See the composition tests below.
  for (const forbidden of [
    "How Overall RIP Is Built",
    "Effective final weights",
    "RipDesirabilityBreakdownStrip",
    "ripDesirabilityBreakdown",
  ]) {
    assert.ok(!source.includes(forbidden), `"${forbidden}" must not appear anywhere on the page`);
    assert.ok(!section.includes(forbidden), `"${forbidden}" must not appear in the verdict section`);
  }
});

test("the composition never states four peer weights that total 110%", () => {
  // RIP Score is 90/10 over (RIP Core, Collector Appeal); RIP Core is 60/25/15
  // over the pillars. Presenting Profit 60 + Safety 25 + Stability 15 +
  // Collector Appeal 10 as one flat list sums to 110% and is the specific
  // misstatement this layout exists to prevent.
  for (const forbidden of [
    "Profit 60% · Safety 25% · Stability 15% · Collector Appeal 10%",
    "profit, safety, desirability, and stability",
  ]) {
    assert.ok(!source.includes(forbidden), `"${forbidden}" states a flat four-way blend`);
  }
  // The nesting is stated instead. After the 80/20 cutover the CANONICAL
  // statement is the one the page renders; the retired 90/10 wording is gone
  // from the UI and survives only as a comment marking the legacy v4 block.
  assert.ok(source.includes("Overall RIP = 80% Financial RIP + 20% Collector Appeal"));
  assert.ok(!source.includes("RIP Score = 90% RIP Core + 10% Collector Appeal"));
});

test("the breakdown branches on score mode, and only on the canonical mode contract", () => {
  const section = verdictSection();

  // The two modes are genuinely different breakdowns — RIP Core has no
  // Collector Appeal term — so the section must branch. It branches on the
  // canonical RIP_CORE_MODE constant from the shared selector, never on a
  // label, a score value, or a locally-invented mode string.
  assert.ok(
    section.includes("const showsCollectorAppeal = scoreMode !== RIP_CORE_MODE;"),
    "mode branching must key on the canonical RIP_CORE_MODE contract"
  );
  assert.equal(
    (section.match(/RIP_CORE_MODE/g) || []).length,
    1,
    "one mode check drives the whole layout; scattered checks let the two halves disagree"
  );
  assert.ok(!section.includes("hidden md:block"), "no display-toggled region may remain");
});

// The two arms of the `showsCollectorAppeal` ternary. Sliced on the RIP Core
// arm's own comment rather than on `) : (`, which also appears inside the
// nested availability ternary in the RIP Score arm.
const CORE_ARM_MARKER = "// RIP Core mode: the three financial cards only, using the full width.";

function scoreModeArm() {
  const section = verdictSection();
  const start = section.indexOf("{showsCollectorAppeal ? (");
  const end = section.indexOf(CORE_ARM_MARKER, start);
  assert.ok(start >= 0 && end > start, "the RIP Score arm must exist");
  return section.slice(start, end);
}

function coreModeArm() {
  const section = verdictSection();
  const start = section.indexOf(CORE_ARM_MARKER);
  assert.ok(start >= 0, "the RIP Core arm must exist");
  return section.slice(start);
}

test("RIP Core mode renders the three financial pillars and no Collector Appeal at all", () => {
  const elseBranch = coreModeArm();

  // Not faded, not disabled, not an empty slot — absent.
  assert.ok(!elseBranch.includes("Collector Appeal"), "RIP Core mode must not render a Collector Appeal block");
  assert.ok(!elseBranch.includes('tone="appeal"'), "no Collector Appeal group may render in RIP Core mode");
  assert.ok(!elseBranch.includes("RipCompositionJoin"), "no dangling '+' may remain once the 10% term is gone");
  assert.ok(!/opacity-\d|disabled/.test(elseBranch), "a faded or disabled placeholder is not the same as removing it");

  // The three cards take the full width instead of leaving a fourth column.
  assert.ok(elseBranch.includes("sm:grid-cols-3"));
  assert.ok(elseBranch.includes("<CompactPillarSignalTile"));
});

test("RIP Score mode nests the pillars inside a 90% RIP Core group beside a 10% term", () => {
  const group = scoreModeArm();

  // The pillars sit INSIDE the RIP Core group, so the 60/25/15 reads as a
  // split of the 90%, not as three of four top-level weights.
  const coreGroup = group.indexOf('eyebrow="RIP Core"');
  const pillarGrid = group.indexOf("<CompactPillarSignalTile");
  const join = group.indexOf("<RipCompositionJoin />");
  const appealGroup = group.indexOf('eyebrow="Collector Appeal"');
  assert.ok(coreGroup >= 0 && pillarGrid > coreGroup, "the pillars must render inside the RIP Core group");
  assert.ok(pillarGrid < join, "the '+' separates the group from the term that follows it");
  assert.ok(join < appealGroup, "Collector Appeal follows the join as a sibling term");

  // Both weights come from the backend contract, never typed into the markup.
  assert.ok(group.includes("weightLabel={coreWeightLabel}"));
  assert.ok(group.includes("weightLabel={collectorAppeal?.weightLabel || null}"));
  assert.ok(!/eyebrow="RIP Core"[\s\S]{0,200}weightLabel="9/.test(group), "the 90% must not be hard-coded");
});

test("Collector Appeal contribution comes from the backend model score, not a relative score", () => {
  const section = verdictSection();

  // The section renders the backend's own contributionLabel. It never
  // multiplies anything itself, and in particular never multiplies the public
  // cohort-relative 0-100 score by a weight — that product sums to nothing the
  // backend computed.
  assert.ok(section.includes("{collectorAppeal.contributionLabel}"));
  assert.ok(!/relativeScore\s*\*/.test(section), "no contribution may be derived from a relative score");
  assert.ok(!/\*\s*0\.1\b/.test(section), "the 10% weight must not be applied in the markup");

  // The selector that produces it reads the ABSOLUTE component scores.
  const selectorSource = fs
    .readFileSync(path.join(here, "../pokemon/set-page/Insights/openingExperienceSelector.mjs"), "utf8")
    .replace(/\r\n/g, "\n");
  const contribution = selectorSource.slice(
    selectorSource.indexOf("const openingContribution ="),
    selectorSource.indexOf("const eff =")
  );
  assert.ok(contribution.includes("ca7Score"), "contribution math uses the absolute CA7 score");
  assert.ok(!contribution.includes("relativeScore"), "contribution math must never touch a relative score");
});

test("a missing Collector Appeal term explains itself instead of showing a fake zero", () => {
  const section = verdictSection();
  const appeal = section.slice(section.indexOf('eyebrow="Collector Appeal"'));

  assert.ok(appeal.includes("collectorAppeal?.available ?"), "availability gates the term");
  assert.ok(appeal.includes("collectorAppeal?.unavailableReason"), "the backend's own reason renders");
  assert.ok(
    appeal.includes("RIP Core and Set Desirability are unaffected"),
    "the unavailable copy must scope itself to CA7 rather than implying the other scores are gone"
  );
  assert.ok(!/>\s*0\s*</.test(appeal), "a missing term must never render as 0");
});

// ---------------------------------------------------------------------------
// Preserved content
// ---------------------------------------------------------------------------

test("the verdict section keeps its score summary, mode toggle and pillar grid", () => {
  const section = verdictSection();

  // Score-mode toggle, wired exactly as before.
  assert.ok(section.includes("<RipScoreModeToggle value={scoreMode} onChange={onScoreModeChange} coreAvailable={coreAvailable} />"));

  // Primary score summary: score, /100, the metadata block and the
  // explanation tooltip. The bare trend arrow is gone — see the metadata test
  // below and the pillar-card test further down.
  assert.ok(section.includes("{formatRawScore(score)}"));
  assert.ok(section.includes(">/100</span>"));
  assert.ok(section.includes("{explanation ? <InfoPopover text={explanation} /> : null}"));

  // Pillar grid: three columns where space permits, stacked below that.
  assert.ok(section.includes("sm:grid-cols-3"));
  assert.ok(section.includes("<CompactPillarSignalTile key={`rip-pillar:${pillar.title}`} {...pillar} detailsExpanded={detailsExpanded} />"));
});

test("score metadata is a tier bubble, a plain rank, and the interpretation bubble", () => {
  const section = verdictSection();
  const badges = source.slice(source.indexOf("function HeroScoreBadges"), source.indexOf("function formatLensScore"));

  // The primary score row hands tier/rank/verdict to ONE shared metadata
  // component rather than assembling decorated badges of its own.
  const scoreRow = section.slice(
    section.indexOf("{formatRawScore(score)}"),
    section.indexOf("data-insights-opening-outlook")
  );
  assert.ok(
    scoreRow.includes("<HeroScoreBadges rank={rankValue} tier={rankTier} cohortSize={cohortSize} interpretation={verdict} />")
  );
  assert.ok(!scoreRow.includes("<RankBadge"), "the score row must not assemble its own badge");
  assert.ok(!scoreRow.includes("<RecommendationBadge"), "the verdict renders through the shared metadata component");

  // The tier keeps a bubble, and it is the SHARED tier badge — not a private
  // palette — so the hero, the pillar cards and Collector Appeal agree.
  assert.ok(
    badges.includes('<RankBadge rank={normalizedTier} format="tier"'),
    "the tier renders through the shared tier badge"
  );

  // The rank does not: plain inline text, no border, no rounding, no fill.
  const rankStart = badges.indexOf("data-rip-score-rank");
  assert.ok(rankStart >= 0, "the rank renders as its own element");
  const rankTag = badges.slice(rankStart, badges.indexOf(">", badges.indexOf("title=", rankStart)));
  assert.ok(!/rounded/.test(rankTag), "the rank must not be a rounded chip");
  assert.ok(!/\bborder/.test(rankTag), "the rank must not draw a border");
  assert.ok(!/\bbg-/.test(rankTag), "the rank must not carry a background fill");

  // Exactly one highlighted pill remains, and it carries the interpretation.
  assert.equal((badges.match(/data-rip-summary-pill/g) || []).length, 1);
  const pill = badges.slice(badges.indexOf("data-rip-summary-pill"));
  assert.ok(pill.includes("{interpretationLabel}"), "the one pill carries the interpretation");
  assert.ok(!pill.includes("normalizedTier"), "the tier must not be inside the interpretation pill");
  assert.ok(!pill.includes("roundedRank"), "the rank must not be inside the interpretation pill");

  // Nothing wraps the row as a whole — three chips inside a fourth outline was
  // the presentation this replaced.
  const rowTag = badges.slice(badges.indexOf("data-rip-score-metadata"), badges.indexOf(">", badges.indexOf("data-rip-score-metadata")));
  assert.ok(!/rounded|border|bg-/.test(rowTag), "the metadata row must not become one capsule");

  // The rank renders bare; the cohort denominator stays in the tooltip.
  assert.ok(badges.includes("Rank #{roundedRank}"), "the rendered rank is bare");
  assert.ok(!/>\s*Rank #\{roundedRank\} of /.test(badges), 'no "of N" in the rendered rank');
  assert.ok(badges.includes("const rankTooltip ="), "the cohort stays available as a tooltip");
});

test("no helper subtitle sits beneath the primary score in either mode", () => {
  const section = verdictSection();

  // The score, the mode toggle, the tier, the rank, the interpretation and
  // Opening Outlook already say what the number is. A sentence repeating that
  // under the score was filling space, so it is gone in BOTH modes — which
  // follows from there being no helper element at all rather than from a
  // mode-dependent branch.
  assert.ok(!section.includes("data-rip-score-helper"));
  assert.ok(!section.includes("scoreHelper"));
  assert.ok(!source.includes("scoreHelper={heroScoreSelection.helper}"));
  assert.ok(!section.includes("Complete opening profile"));
  assert.ok(!section.includes("Financial opening profile only"));

  // Nothing replaced it: between the metadata row and Opening Outlook there is
  // no other paragraph.
  const between = section.slice(
    section.indexOf("<HeroScoreBadges"),
    section.indexOf("data-insights-opening-outlook")
  );
  assert.ok(!/<p\b/.test(between.slice(between.indexOf("</div>"))), "no new subtitle may appear under the score");

  // The copy itself still exists on the selector and still reaches the user as
  // the hero toggle's tooltip — it was demoted, not deleted.
  const modes = fs.readFileSync(path.join(here, "ripHeroScoreMode.mjs"), "utf8").replace(/\r\n/g, "\n");
  assert.ok(modes.includes('"Complete opening profile — financial performance plus Collector Appeal."'));
  assert.ok(modes.includes('"Financial opening profile only — Profit, Safety and Stability, without Collector Appeal."'));
  assert.ok(source.includes("<InfoPopover text={heroScoreSelection.helper} />"), "the helper survives as a tooltip");
});

test("the RIP Core group header does not restate the per-card weights", () => {
  const section = verdictSection();

  // The group header says WHAT the group is and its 90% share. The 60/25/15
  // split is on the three cards inside it ("60% of RIP Core", …), so spelling
  // it out again a few pixels above was the same numbers twice.
  assert.ok(source.includes('const ripCoreWeightsCaption = "Financial opening performance";'));
  assert.ok(!source.includes("Financial opening performance — Profit"));
  assert.ok(!/Profit 60% · Safety 25% · Stability 15%/.test(source));

  // Both top-level weights survive, from the backend contract.
  assert.ok(section.includes("weightLabel={coreWeightLabel}"), "RIP Core keeps its 90%");
  assert.ok(section.includes("weightLabel={collectorAppeal?.weightLabel || null}"), "Collector Appeal keeps its 10%");
  // And the per-card weights are untouched.
  const tileStart = source.indexOf("function CompactPillarSignalTile");
  const tile = source.slice(tileStart, source.indexOf("\n}\n", tileStart));
  assert.ok(tile.includes("{`${Math.round(parsedWeight * 100)}% of RIP Core`}"));
});

test("Collector Appeal renders a tier bubble, a plain rank, and a secondary contribution", () => {
  const section = verdictSection();
  const appeal = section.slice(section.indexOf('eyebrow="Collector Appeal"'));

  // Same hierarchy as the primary score row, using the same shared tier badge.
  assert.ok(appeal.includes('<RankBadge rank={collectorAppeal.tier} format="tier" />'));

  const rankStart = appeal.indexOf("data-rip-collector-appeal-rank");
  assert.ok(rankStart >= 0, "the rank renders as its own element");
  const rankTag = appeal.slice(rankStart, appeal.indexOf(">", appeal.indexOf("title=", rankStart)));
  assert.ok(!/rounded|\bborder|\bbg-/.test(rankTag), "the rank must stay plain text");
  assert.ok(appeal.includes("Rank #{Math.round(collectorAppeal.rank)}"));
  assert.ok(!/>\s*\{collectorAppeal\.rankLabel\}/.test(appeal), 'the denominated "#5 of 21" label is not rendered here');

  // The contribution drops to its own line as secondary metadata rather than
  // sitting inline with the score, tier and rank.
  const contribution = appeal.slice(appeal.indexOf("data-rip-collector-appeal-contribution"));
  assert.ok(contribution.includes("mt-1.5"), "the contribution sits on its own line");
  assert.ok(/text-\[11px\]|text-xs/.test(contribution), "the contribution stays secondary in size");
  assert.ok(appeal.includes("{collectorAppeal.contributionLabel}"), "the contribution is still shown");
  assert.ok(
    appeal.indexOf("data-rip-collector-appeal-rank") < appeal.indexOf("data-rip-collector-appeal-contribution"),
    "score/tier/rank precede the contribution"
  );

  // The description under the header is the only sentence in the block.
  assert.equal(
    (appeal.match(/caption=/g) || []).length,
    1,
    "no second explanatory sentence may be added under Collector Appeal"
  );
});

test("the pillar cards keep their canonical Profit / Safety / Stability bindings", () => {
  const tilesStart = source.indexOf("const ripPillarTiles = [");
  const tilesEnd = source.indexOf("const overviewPillarSignals", tilesStart);
  assert.ok(tilesStart >= 0 && tilesEnd > tilesStart);
  const tiles = source.slice(tilesStart, tilesEnd);

  assert.ok(tiles.indexOf('title: "Profit"') < tiles.indexOf('title: "Safety"'));
  assert.ok(tiles.indexOf('title: "Safety"') < tiles.indexOf('title: "Stability"'));
  for (const pillar of ["Profit", "Safety", "Stability"]) {
    assert.ok(tiles.includes(`ripBreakdownRowByTitle.get("${pillar}")?.score`));
    assert.ok(tiles.includes(`ripBreakdownRowByTitle.get("${pillar}")?.rankValue`));
    assert.ok(tiles.includes(`ripBreakdownRowByTitle.get("${pillar}")?.rankTier`));
    assert.ok(tiles.includes(`infoText: getFormattedTooltip("${pillar}")`));
  }
});

test("Opening Outlook renders once, from the canonical value handed to the section", () => {
  const section = verdictSection();

  assert.equal(
    (source.match(/data-insights-opening-outlook/g) || []).length,
    1,
    "the outlook must not be duplicated after being moved above the pillars"
  );
  // Canonical text only: no frontend rewriting, no score-range wording, no
  // verdict derived from the pillar scores.
  assert.ok(section.includes("{openingOutlook || \"No opening outlook is available for this set yet.\"}"));
  // The tooltip body is now a shared constant (the below-desktop presentation
  // renders the same outlook in its shared detail region and must quote the
  // same sentence, not a retyped near-copy). Canonical text, one definition.
  assert.ok(section.includes("<InfoPopover text={RIP_OUTLOOK_INFO_TEXT} />"));
  assert.ok(source.includes("It does not evaluate sealed-product appreciation"));
  assert.equal(
    (source.match(/It does not evaluate sealed-product appreciation/g) || []).length,
    1,
    "the disclaimer has exactly one definition"
  );
  assert.ok(!section.includes("<details"), "the outlook stays complete rather than truncated behind a disclosure");
});

test("Opening Outlook reads as a restrained highlighted callout, not a dashboard card", () => {
  const section = verdictSection();
  const start = section.indexOf("data-insights-opening-outlook");
  const callout = section.slice(start, section.indexOf("</div>", section.indexOf("{openingOutlook ||", start)));

  // Small uppercase eyebrow + stronger-than-body copy contrast.
  assert.ok(callout.includes("uppercase tracking-[0.08em]"));
  assert.ok(callout.includes(">Opening Outlook</p>"));
  assert.ok(callout.includes("text-[var(--text-primary)]"), "the copy must be fully opaque primary text");
  assert.ok(callout.includes("text-sm"), "body copy stays at the readable minimum");

  // A narrow rail plus a horizontal wash, both from the shared tier
  // presentation — never a flat fill spanning the content width.
  assert.ok(callout.includes("border-l-2"), "the tier-coloured rail stays");
  assert.ok(section.includes("getRipTierPresentation({ label: verdict, rankTier })"));
  assert.ok(callout.includes("borderLeftColor: outlookAccent.outlookRail.borderLeftColor"));
  assert.ok(callout.includes("backgroundImage: outlookAccent.outlookWash"));
  assert.ok(
    !/backgroundColor:/.test(callout),
    "a uniform background colour would re-create the full-width alert banner"
  );

  // No box: the wash fades out on its own, so nothing draws a right-hand edge.
  assert.ok(!callout.includes("rounded"), "a rounded container would read as an alert box");
  assert.ok(
    !/\bborder(?![-\w])|border-\[|border-r|border-t|border-b/.test(callout),
    "the markup may draw only the left rail; the localized top highlight is a masked pseudo-element"
  );

  // Not a heavy panel: no glass class, no blur, no parent opacity.
  assert.ok(!callout.includes("set-glass"), "the callout must not reuse the heavy glass surface");
  assert.ok(!callout.includes("backdrop-blur"));
  assert.ok(!/\bopacity-\d/.test(callout), "no parent-level opacity may dim the callout contents");
  // Meaning is not carried by the border colour alone — the label says it.
  assert.ok(callout.includes("Opening Outlook"));
});

test("Opening Outlook is lit from the upper-left corner, not outlined all the way round", () => {
  const section = verdictSection();
  const start = section.indexOf("data-insights-opening-outlook");
  const callout = section.slice(start, section.indexOf("</div>", section.indexOf("{openingOutlook ||", start)));
  const globals = fs
    .readFileSync(path.join(here, "../../app/styles/globals.css"), "utf8")
    .replace(/\r\n/g, "\n");

  // The highlight is a pseudo-element, so it cannot stack a second card behind
  // the callout: it carries the edge colour and nothing else.
  assert.ok(callout.includes("rip-outlook-callout"), "the callout opts into the edge treatment");
  assert.ok(callout.includes('"--rip-outlook-edge": outlookAccent.outlookEdge'), "the colour comes from the shared presentation");

  const rule = globals.slice(globals.indexOf(".rip-outlook-callout::before"));
  const body = rule.slice(0, rule.indexOf("}"));
  assert.ok(body.includes("border-top: 1px solid var(--rip-outlook-edge, transparent)"), "only the top edge is drawn");
  for (const forbidden of ["border-right", "border-bottom", "border-left", "background:", "box-shadow"]) {
    assert.ok(!body.includes(forbidden), `the pseudo-element must not declare ${forbidden}`);
  }

  // The mask fades the run out well before the midpoint and never reaches the
  // right-hand side, so the lit corner cannot become a perimeter outline.
  const mask = body.match(/[^-]mask-image: linear-gradient\(90deg,([^;]+)\);/);
  assert.ok(mask, "the top edge must be masked by a horizontal gradient");
  const lastStop = Number(mask[1].trim().split(",").pop().trim().match(/([\d.]+)%/)[1]);
  assert.ok(lastStop <= 25, `the highlight must end within the first ~25% (got ${lastStop}%)`);
  assert.ok(lastStop < 50, "the highlight must be fully transparent before the midpoint");
  assert.ok(/rgba\(0, 0, 0, 0\)\s+[\d.]+%\s*$/.test(mask[1].trim()), "it must fade to fully transparent, not cut off");
});

test("Opening Outlook keeps the full content width and takes no fixed measure", () => {
  const section = verdictSection();
  const start = section.indexOf("data-insights-opening-outlook");
  const openTag = section.slice(start, section.indexOf(">", section.indexOf("style={{", start)));

  assert.ok(openTag.includes("min-w-0"), "the callout must still shrink with its column");
  assert.ok(
    !/\b(max-w-|w-1\/2|w-\[)/.test(openTag),
    "the container must not be capped at a half or fixed width — only the colour stops early"
  );
});

// ---------------------------------------------------------------------------
// Ordering
// ---------------------------------------------------------------------------

test("the verdict reads heading → details toggle → mode toggle → score → outlook → pillars", () => {
  const section = verdictSection();

  const eyebrow = orderOf(section, "<SectionEyebrow>01 · Verdict</SectionEyebrow>");
  const heading = orderOf(section, ">RIP Score Breakdown</h2>");
  const detailsToggle = orderOf(section, "aria-expanded={detailsExpanded}");
  const modeToggle = orderOf(section, "<RipScoreModeToggle");
  const score = orderOf(section, "{formatRawScore(score)}");
  const outlook = orderOf(section, "data-insights-opening-outlook");
  const pillars = orderOf(section, "{pillars.map((pillar) => (");

  assert.ok(eyebrow < heading, "the chapter marker precedes the heading");
  assert.ok(heading < detailsToggle, "Show Details sits in the header, aligned with the heading block");
  assert.ok(detailsToggle < modeToggle, "the details control precedes the score-mode toggle");
  assert.ok(modeToggle < score, "the score-mode toggle precedes the score it switches");
  assert.ok(score < outlook, "the primary score appears before Opening Outlook");
  assert.ok(outlook < pillars, "Opening Outlook appears before the Profit / Safety / Stability grid");
});

test("the composition is the last thing in each mode", () => {
  // In RIP Score mode the 10% Collector Appeal term is the one thing that
  // follows the pillar grid — that is the composition, not a reinstated
  // formula panel. Nothing else may render after it in either arm.
  const scoreArm = scoreModeArm();
  const afterAppeal = scoreArm.slice(scoreArm.indexOf('eyebrow="Collector Appeal"'));
  assert.ok(!afterAppeal.includes("How Overall RIP"));
  assert.ok(!afterAppeal.includes("data-insights-opening-outlook"), "the old outlook placement must be gone");
  assert.ok(
    !afterAppeal.includes("<CompactPillarSignalTile"),
    "the pillars must not render a second time below the 10% term"
  );

  const coreArm = coreModeArm();
  const afterPillars = coreArm.slice(coreArm.lastIndexOf("<CompactPillarSignalTile"));
  assert.ok(!/<[A-Z][A-Za-z]*/.test(afterPillars.slice(afterPillars.indexOf("/>"))), "RIP Core mode ends with the pillar grid");
});

test("the section header and outlook stay compact rather than reserving deleted space", () => {
  const section = verdictSection();

  // The subtitle's spacing went with the subtitle; the header block is now
  // eyebrow + heading only, and the vertical rhythm below it is uniform.
  assert.ok(!section.includes('className="mt-1 min-w-0 max-w-full text-sm text-[var(--text-secondary)]"'));
  assert.ok(!section.includes("mt-5"), "the old oversized gaps are gone");
  assert.ok(!section.includes("border-t border-[var(--border-subtle)] pt-4"), "the outlook divider is no longer needed");
  // Header wraps cleanly on mobile instead of overlapping the control.
  assert.ok(section.includes("flex-wrap items-start justify-between gap-x-3 gap-y-2"));
  assert.ok(section.includes("inline-flex flex-none items-center"), "the control must not stretch or float");
});

// ---------------------------------------------------------------------------
// Show Details
// ---------------------------------------------------------------------------

test("Show Details still controls real user-facing detail, not the removed panel", () => {
  const section = verdictSection();

  // Semantics and keyboard/focus behaviour preserved.
  assert.ok(section.includes('type="button"'));
  assert.ok(section.includes("aria-expanded={detailsExpanded}"));
  assert.ok(section.includes("focus-visible:ring-2"));
  assert.ok(section.includes('{detailsExpanded ? "Hide Details" : "Show Details"}'));
  assert.ok(section.includes('aria-hidden="true"'), "the chevron stays decorative");

  // What it expands: the supporting per-pillar metric rows plus the backend's
  // own contribution figure for that component.
  assert.ok(section.includes("detailsExpanded={detailsExpanded}"));

  const tileStart = source.indexOf("function CompactPillarSignalTile");
  const tileEnd = source.indexOf("\n}\n", tileStart);
  assert.ok(tileStart >= 0 && tileEnd > tileStart);
  const tile = source.slice(tileStart, tileEnd);
  assert.ok(
    tile.includes("{detailsExpanded && (metrics.length > 0 || parsedContribution !== null) ? ("),
    "no empty details region may render"
  );
  assert.ok(tile.includes("<MetricRow"));

  // Weight and contribution are the BACKEND's component fields, so the card
  // may show them — but only as read, never recomputed here.
  const signature = tile.slice(0, tile.indexOf("}) {"));
  assert.ok(signature.includes("weight = null"), "the card shows the canonical component weight");
  assert.ok(signature.includes("contribution = null"), "the card shows the canonical contribution");
  assert.ok(!/score\s*\*\s*(weight|parsedWeight)/.test(tile), "contribution must be read, never multiplied here");
  assert.ok(tile.includes("{`${Math.round(parsedWeight * 100)}% of RIP Core`}"), "the weight is a share of RIP Core");
});

test("the financial pillar cards no longer render a bare trend arrow", () => {
  const tileStart = source.indexOf("function CompactPillarSignalTile");
  const tileEnd = source.indexOf("\n}\n", tileStart);
  const tile = source.slice(tileStart, tileEnd);

  // The arrow carried a direction with no timeframe and no delta, so there was
  // nothing for the reader to check or size. It is removed from the card, and
  // the gap it reserved beside every score goes with it.
  assert.ok(!tile.includes("<TrendIndicator"), "no trend indicator may render in a pillar card");
  assert.ok(!tile.includes("scoreTrend"), "the card must not read the trend prop at all");
  assert.ok(
    !/formatScore\(score\)\}<\/span>\s*\n\s*<[A-Z]/.test(tile),
    "no sibling element may re-reserve the arrow's slot beside the score"
  );

  // The trend data itself stays on the shared selector — other surfaces and
  // the diagnostics rows still consume it.
  const selectorSource = fs.readFileSync(path.join(here, "ripScoreBreakdownSelector.mjs"), "utf8");
  assert.ok(selectorSource.includes("scoreTrend: safeTrends[pillar.trendKey] || null"));
});

test("expanded pillar detail is real user-facing supporting data", () => {
  const metricsStart = source.indexOf("const stabilityPillarMetrics = [");
  const metricsEnd = source.indexOf("];", metricsStart);
  const metrics = source.slice(metricsStart, metricsEnd);

  assert.ok(metrics.includes('label: "Cards Carrying Value"'));
  assert.ok(metrics.includes('label: "Top Chase Share"'));
  assert.ok(!metrics.includes("Effective"), "no effective-weight rows may hide under the toggle");
});

// ---------------------------------------------------------------------------
// Missing optional data
// ---------------------------------------------------------------------------

test("a missing Opening Outlook degrades to the existing unavailable copy", () => {
  const section = verdictSection();

  // The existing unavailable-data convention is kept, so the callout is never
  // empty and never prints `undefined`.
  assert.ok(section.includes('"No opening outlook is available for this set yet."'));
  // Never rendered unguarded. Handing the raw value to the below-desktop feed
  // as a PROP is not rendering it — that tree applies the same `||` fallback,
  // which the mobile contract test asserts separately.
  assert.ok(!/>\s*\{openingOutlook\}\s*</.test(source), "the raw value is never rendered unguarded");
  assert.ok(!/\{openingOutlook\}\s*<\/p>/.test(source), "no paragraph prints the raw value");
});

test("a missing score, rank or cohort renders unavailable rather than crashing", () => {
  const badges = source.slice(source.indexOf("function HeroScoreBadges"), source.indexOf("function formatLensScore"));
  const tileStart = source.indexOf("function CompactPillarSignalTile");
  const tile = source.slice(tileStart, source.indexOf("\n}\n", tileStart));

  // The metadata component drops absent segments instead of printing "null".
  assert.ok(badges.includes("const numericRank = toNumber(rank);"));
  assert.ok(badges.includes("const numericCohort = toNumber(cohortSize);"));
  assert.ok(badges.includes("roundedRank === null"));
  assert.ok(
    badges.includes("if (!normalizedTier && roundedRank === null && !interpretationLabel) {"),
    "an empty metadata row renders nothing"
  );

  // The pillar card still names an unavailable rank rather than inventing one.
  assert.ok(tile.includes('? "Rank unavailable"'));
  assert.ok(tile.includes("const parsedWeight = toNumber(weight);"));
  assert.ok(tile.includes("const parsedContribution = toNumber(contribution);"));

  // formatRawScore is the shared null-safe formatter ("—" for missing).
  assert.ok(source.includes("return parsed === null ? \"—\" : parsed.toFixed(1);"));
});

// ---------------------------------------------------------------------------
// Values unchanged — the layout update touched presentation only.
// ---------------------------------------------------------------------------

const RIP_FIXTURE = {
  score: 68.4,
  relativeScore: 70.9,
  rank: 12,
  tier: "B",
  cohortSize: 140,
  interpretation: { label: "Good value, rough misses", summary: "This set has good value for the price." },
  financialRip: {
    components: {
      profit: { score: 74.2, rank: 9, tier: "A", cohortSize: 140, weight: 0.6, contribution: 44.52 },
      safety: { score: 51.8, rank: 61, tier: "C", cohortSize: 140, weight: 0.25, contribution: 12.95 },
      stability: { score: 63.1, rank: 30, tier: "B", cohortSize: 140, weight: 0.15, contribution: 9.465 },
    },
  },
};

const RIP_CORE_FIXTURE = {
  score: 66.1,
  relativeScore: 64.3,
  rank: 21,
  tier: "B",
  cohortSize: 140,
  interpretation: { label: "Solid financial floor", summary: "Financial profile only." },
};

test("the three pillar values the section displays are unchanged", () => {
  const { rows, sourceUsed, fallbackUsed } = selectRipScoreBreakdown(RIP_FIXTURE, {});

  assert.deepEqual(
    rows.map((row) => [row.title, row.score, row.rankValue, row.rankTier]),
    [
      ["Profit", 74.2, 9, "A"],
      ["Safety", 51.8, 61, "C"],
      ["Stability", 63.1, 30, "B"],
    ]
  );
  assert.equal(sourceUsed, "rip.financialRip.components");
  assert.equal(fallbackUsed, false);
});

test("both score modes still resolve the same values the section renders", () => {
  const payload = { rip: RIP_FIXTURE, ripCore: RIP_CORE_FIXTURE };

  const ripScore = selectRipHeroScoreMode({ mode: RIP_SCORE_MODE, payload });
  assert.equal(ripScore.mode, RIP_SCORE_MODE);
  assert.equal(ripScore.score, 70.9);
  assert.equal(ripScore.absoluteScore, 68.4);
  assert.equal(ripScore.rank, 12);
  assert.equal(ripScore.tier, "B");
  assert.equal(ripScore.interpretation.label, "Good value, rough misses");
  assert.equal(ripScore.coreAvailable, true);

  const ripCore = selectRipHeroScoreMode({ mode: RIP_CORE_MODE, payload });
  assert.equal(ripCore.mode, RIP_CORE_MODE);
  assert.equal(ripCore.score, 64.3);
  assert.equal(ripCore.absoluteScore, 66.1);
  assert.equal(ripCore.rank, 21);
  assert.equal(ripCore.tier, "B");
  assert.equal(ripCore.interpretation.label, "Solid financial floor");

  // Switching modes changes the values, never the pillar contract.
  assert.notEqual(ripScore.score, ripCore.score);
  assert.deepEqual(
    selectRipScoreBreakdown(RIP_FIXTURE, {}).rows.map((row) => row.score),
    [74.2, 51.8, 63.1]
  );
});
