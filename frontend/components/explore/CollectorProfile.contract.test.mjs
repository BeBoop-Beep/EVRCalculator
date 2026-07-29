// The Collector Profile — the "02 · Collector Profile" section on the set-page
// Insights tab.
//
// It replaced two sibling sections ("Set Desirability" and "Simulation Opening
// Experience") that left the reader to guess how they related. They are not
// alternatives and not duplicates: Set Desirability is the roster base CA7
// consumes, CA7 is the term RIP Score weights at 10%, and Set Desirability
// itself carries no RIP weight. The section shows that chain.
//
// Two things this file exists to protect:
//
//   1. the RELATIONSHIP is stated, not implied — one direction, three stages,
//      never a toggle between two measurements of the same thing; and
//   2. the two scores keep SEPARATE availability, because they fail for
//      different reasons (a checklist vs. a modeled pull structure). Merging
//      the presentation must not merge the gating.
//
// The component lives inside RipStatisticsPageClient.jsx and is not exported —
// and that file cannot be imported outside the Next build — so structural
// assertions read the rendered JSX source, matching the existing contract tests
// for this page. The value assertions run the real selectors.

import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import {
  selectOpeningExperiencePresentation,
  selectRipDesirabilityBreakdown,
  selectSetDesirabilityPresentation,
} from "../pokemon/set-page/Insights/openingExperienceSelector.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const source = fs.readFileSync(path.join(here, "RipStatisticsPageClient.jsx"), "utf8").replace(/\r\n/g, "\n");

function collectorProfileSection() {
  const start = source.indexOf("function CollectorProfileSection");
  const end = source.indexOf("\nconst TOP_CARD_IMAGE_CONTAINER_CLASS", start);
  assert.ok(start >= 0 && end > start, "CollectorProfileSection must exist");
  return source.slice(start, end);
}

function summaryFlow() {
  const section = collectorProfileSection();
  const start = section.indexOf("data-collector-profile-flow");
  const end = section.indexOf("<SectionViewTabs", start);
  assert.ok(start >= 0 && end > start, "the summary flow must precede the detail tabs");
  return section.slice(start, end);
}

// The bullet arrays behind the three information tooltips, read out of the
// source so the assertions below check the copy that actually ships.
function bulletList(name) {
  const start = source.indexOf(`const ${name} = [`);
  assert.ok(start >= 0, `${name} must exist`);
  const body = source.slice(source.indexOf("[", start) + 1, source.indexOf("\n];", start));
  return body
    .split("\n")
    .map((line) => line.trim().replace(/^"/, "").replace(/",$/, ""))
    .filter(Boolean);
}

const COLLECTOR_PROFILE_BULLETS = bulletList("COLLECTOR_PROFILE_INFO_BULLETS");
const SET_DESIRABILITY_BULLETS = bulletList("SET_DESIRABILITY_INFO_BULLETS");
const COLLECTOR_APPEAL_BULLETS = bulletList("COLLECTOR_APPEAL_INFO_BULLETS");

// ---------------------------------------------------------------------------
// The relationship
// ---------------------------------------------------------------------------

test("the summary states one directed chain: Set Desirability -> Collector Appeal -> 10%", () => {
  const flow = summaryFlow();

  const desirability = flow.indexOf('label="Set Desirability"');
  const appeal = flow.indexOf('label="Collector Appeal"');
  const contribution = flow.indexOf('label="RIP Score Contribution"');
  assert.ok(desirability >= 0 && appeal > desirability, "Collector Appeal follows Set Desirability");
  assert.ok(contribution > appeal, "the weighted term is the end of the chain");

  // Two connectors, so the direction is drawn and not merely implied by order.
  assert.equal((flow.match(/<CollectorProfileArrow \/>/g) || []).length, 2);
});

test("the two scores are stages of a chain, never options of a toggle", () => {
  const flow = summaryFlow();

  // A radio/segmented control here would say "pick one of these two views of
  // the same thing", which is the exact misreading the section fixes.
  assert.ok(!flow.includes("SegmentedControl"), "the flow must not be a control");
  assert.ok(!flow.includes("<SectionViewTabs"), "the flow must not be a control");
  assert.ok(!/role="radio"/.test(flow));
  assert.ok(!flow.includes("onChange"), "the stages are not selectable alternatives");
});

test("Set Desirability is labelled as supporting context, not a separate RIP weight", () => {
  const flow = summaryFlow();
  const stage = flow.slice(flow.indexOf('label="Set Desirability"'), flow.indexOf('label="Collector Appeal"'));

  assert.ok(stage.includes("Supporting input — no RIP Score weight of its own."));
  // Only the Collector Appeal stage carries a weight; Set Desirability has none.
  assert.ok(!stage.includes("weightLabel"));
  assert.ok(!/\d+%/.test(stage), "no percentage may sit on the Set Desirability stage");

  // And the tooltip states the same thing, at length.
  assert.ok(
    SET_DESIRABILITY_BULLETS.includes(
      "Supports Collector Appeal but does not receive its own RIP Score weight."
    )
  );
});

test("the contribution stage shows the backend weight and model points, not a recomputation", () => {
  const flow = summaryFlow();
  const stage = flow.slice(flow.indexOf('label="RIP Score Contribution"'));

  assert.ok(stage.includes('ripContribution?.weightLabel || "10%"'));
  assert.ok(stage.includes("ripContribution?.contributionPointsLabel"));
  assert.ok(stage.includes("RIP Core supplies the other 90%"), "the other 90% is named so 10% is not read as the whole");
  assert.ok(!/\*\s*0\.1\b/.test(flow), "the weight must never be applied in the markup");
});

// ---------------------------------------------------------------------------
// Separate availability
// ---------------------------------------------------------------------------

test("Set Desirability stays available when Collector Appeal is not", () => {
  const universal = {
    score: 87.9,
    rank: 59,
    rankedSetCount: 135,
    coverage: { status: "full" },
    components: { chase_subject_strength: 68.1, chase_subject_depth: 74.2, favorite_hit_coverage: 84.2 },
  };

  // No CA7 at all.
  const desirability = selectSetDesirabilityPresentation(universal);
  const opening = selectOpeningExperiencePresentation({ status: "unavailable", coverage: { reasons: ["no_pack_model"] } });

  assert.equal(desirability.available, true, "the roster score does not need a pull model");
  assert.equal(desirability.scoreLabel, "87.9");
  assert.equal(desirability.rankLabel, "#59 of 135");
  assert.equal(opening.available, false);
  // Critically: the desirability presentation is computed from its own
  // contract and cannot observe the CA7 one.
  assert.equal(selectSetDesirabilityPresentation(universal).available, true);
});

test("each panel is driven by its own presentation object", () => {
  const section = collectorProfileSection();

  assert.ok(section.includes("<CollectorRosterAppealPanel presentation={desirability}"));
  assert.ok(section.includes("<CollectorOpeningPathsPanel presentation={opening}"));
  // One panel's availability must never gate the other's.
  assert.ok(!/desirability\.available\s*&&\s*opening\.available/.test(section));
  assert.ok(!/opening\.available\s*&&\s*desirability\.available/.test(section));
});

test("an unavailable Collector Appeal scopes its message to the pull model", () => {
  const start = source.indexOf("function CollectorOpeningPathsPanel");
  const panel = source.slice(start, source.indexOf("function CollectorProfileSection", start));

  assert.ok(panel.includes("Collector Appeal needs this set&apos;s modeled pull structure"));
  assert.ok(panel.includes("Set Desirability is unaffected"));
  // It must not claim desirability is missing too, and must not print a 0.
  assert.ok(!/Set Desirability (isn&apos;t|is not) available/.test(panel));
  assert.ok(!/>\s*0\s*</.test(panel));
});

test("a missing CA7 explains RIP Score's absence in user-facing names, without a fake zero", () => {
  const model = selectRipDesirabilityBreakdown(
    // The backend shape for a set with a financial score but no CA7.
    { score: null, statusReason: "unavailable_missing_input", components: { financialRip: { score: 14.9575, weight: 0.9 } } },
    { score: 14.9575, relativeScore: 41.2, rank: 30, tier: "D", cohortSize: 33 },
    { score: 92.4, rank: 23, rankedSetCount: 135, coverage: { status: "full" } },
    { status: "unavailable" }
  );

  assert.equal(model.openingDesirability.score, null);
  assert.equal(model.openingDesirability.scoreLabel, null, "a missing term has no score label, not '0.0'");
  assert.equal(model.openingDesirability.contribution, null, "and no contribution, not 0");
  assert.equal(
    model.openingDesirability.unavailableReason,
    "Collector Appeal (CA7) is unavailable for this set, so RIP Score cannot be computed. RIP Core and Set Desirability are unaffected."
  );

  // The reason names the metrics the user can actually see. "Overall RIP" and
  // "Financial RIP" are internal names for RIP Score and RIP Core; printing
  // them here read as a third, unseen metric.
  assert.ok(!model.openingDesirability.unavailableReason.includes("Overall RIP"));
  assert.ok(!model.openingDesirability.unavailableReason.includes("Financial RIP"));

  // RIP Core and Set Desirability stay usable, and RIP Core is NOT promoted
  // into RIP Score's place.
  assert.equal(model.financialRip.relativeScore, 41.2);
  assert.equal(model.setDesirability.scoreLabel, "92.4");
  assert.equal(model.overallRip.score, null);
  assert.equal(model.overallRip.relativeScore, null);
  assert.notEqual(model.overallRip.score, model.financialRip.score);
});

// ---------------------------------------------------------------------------
// Diagnostics vs. weighted terms
// ---------------------------------------------------------------------------

test("Chase Appeal and Dual-Path Depth are labelled diagnostics, not weights", () => {
  const start = source.indexOf("function CollectorOpeningPathsPanel");
  const panel = source.slice(start, source.indexOf("function CollectorProfileSection", start));

  for (const label of ['label="Chase Appeal"', 'label="Dual-Path Depth"']) {
    assert.ok(panel.indexOf(label) >= 0, `${label} must render`);
  }

  // The "not a weight" caveat is education, so it belongs in the band's tooltip
  // rather than as a sentence printed under every value.
  assert.ok(panel.includes("infoBullets={OPENING_PATH_SUMMARY_INFO_BULLETS}"));
  const bandBullets = bulletList("OPENING_PATH_SUMMARY_INFO_BULLETS");
  assert.ok(bandBullets.includes("Both explain Collector Appeal; neither is added to RIP Score."));
  assert.ok(
    COLLECTOR_APPEAL_BULLETS.includes(
      "Chase Appeal and Dual-Path Depth are explanatory diagnostics, not separate RIP Score weights."
    )
  );
});

test("the stale 'neither is a pillar' copy is gone and the current model is stated", () => {
  // Written when CA7 sat outside the score entirely. Under overall_rip_v4
  // Collector Appeal IS a weighted term, so the old sentence is now false.
  assert.ok(!source.includes("neither is a pillar of the RIP Score"));
  assert.ok(!source.includes("It is a diagnostic — it is not a pillar of the RIP Score."));
  assert.ok(!source.includes("A separate diagnostic — it is not added to the RIP Score."));
  assert.ok(!source.includes("Chase Appeal is a separate desirability × scarcity diagnostic and is not added to the RIP Score."));

  // All four facts survive, one per bullet, across the tooltips that own them.
  assert.ok(COLLECTOR_PROFILE_BULLETS.includes("Collector Appeal contributes 10% to RIP Score."));
  assert.ok(COLLECTOR_APPEAL_BULLETS.includes("Contributes 10% to RIP Score."));
  assert.ok(
    COLLECTOR_APPEAL_BULLETS.includes("Chase Appeal helps explain the quality of the available chase.")
  );
  assert.ok(
    COLLECTOR_APPEAL_BULLETS.includes(
      "Dual-Path Depth measures how many desirable subjects have both accessible and elite paths."
    )
  );
  assert.ok(
    SET_DESIRABILITY_BULLETS.includes(
      "Supports Collector Appeal but does not receive its own RIP Score weight."
    )
  );
});

// ---------------------------------------------------------------------------
// One surface, bullet tooltips, no duplicated visible education
// ---------------------------------------------------------------------------

test("the heading carries no visible subtitle — the explanation is in its tooltip", () => {
  const section = collectorProfileSection();
  const card = section.slice(section.indexOf("<SectionCard"), section.indexOf(">", section.indexOf("bodyClassName")));

  assert.ok(!card.includes("subtitle="), "a subtitle under the heading repeats what the layout already shows");
  assert.ok(card.includes("titleInfoText={infoBullets(COLLECTOR_PROFILE_INFO_BULLETS)}"));

  // The old visible subtitle and the old visible Set Desirability footer
  // paragraph both moved into tooltips; neither may return as body copy.
  assert.ok(!source.includes("How this set's roster demand becomes the 10% Collector Appeal term in RIP Score."));
  assert.ok(
    !collectorProfileSection().includes(
      "Set Desirability measures the popularity and depth of the Pokémon subjects represented in this set."
    )
  );
});

test("the three information tooltips are bullet lists, not paragraph walls", () => {
  // Real list markup, so a screen reader announces a list of six facts rather
  // than one long sentence.
  assert.ok(source.includes('<ul data-info-bullets'), "InfoBullets must render a real <ul>");

  for (const [name, bullets] of [
    ["Collector Profile", COLLECTOR_PROFILE_BULLETS],
    ["Set Desirability", SET_DESIRABILITY_BULLETS],
    ["Collector Appeal", COLLECTOR_APPEAL_BULLETS],
  ]) {
    assert.ok(bullets.length >= 6, `${name} must be at least six bullets`);
    for (const bullet of bullets) {
      // One idea per bullet: no bullet may itself be a two-sentence paragraph.
      assert.ok(bullet.length <= 120, `${name} bullet is too long: ${bullet}`);
      assert.ok(!/\.\s+\S/.test(bullet), `${name} bullet packs two sentences: ${bullet}`);
    }
  }

  // And the flow's stage tooltips read those arrays, not a prose string.
  const flow = summaryFlow();
  assert.ok(flow.includes("infoBullets={SET_DESIRABILITY_INFO_BULLETS}"));
  assert.ok(flow.includes("infoBullets={COLLECTOR_APPEAL_INFO_BULLETS}"));
  assert.ok(!/infoText=/.test(flow), "no stage may take a prose tooltip");
});

test("each detail view is ONE bordered surface with internal bands", () => {
  const roster = source.slice(
    source.indexOf("function CollectorRosterAppealPanel"),
    source.indexOf("function CollectorOpeningPathsPanel")
  );
  const paths = source.slice(
    source.indexOf("function CollectorOpeningPathsPanel"),
    source.indexOf("function CollectorProfileSection")
  );

  for (const [name, view, bands] of [["Roster Appeal", roster, 3], ["Opening Paths", paths, 2]]) {
    assert.equal((view.match(/<CollectorPanel>/g) || []).length, 1, `${name} must be one surface`);
    assert.equal((view.match(/<CollectorBand /g) || []).length, bands);
    // The retired per-metric card surfaces must not come back.
    assert.ok(!view.includes("CollectorMetricGroup"), `${name} must not re-introduce per-group cards`);
    assert.ok(!view.includes("CollectorListPanel"), `${name} must not re-introduce a separate list card`);
    assert.ok(!/rounded-xl border/.test(view), `${name} must not add a border of its own`);
  }

  // Roster Appeal reads roster quality -> demand distribution -> the subjects
  // driving the score, in that order.
  const quality = roster.indexOf('title="Roster Quality"');
  const distribution = roster.indexOf('title="Demand Distribution"');
  const drivers = roster.indexOf('title="Top Desirability Drivers"');
  assert.ok(quality >= 0 && distribution > quality && drivers > distribution);
});

test("a subject's two pull paths belong to one row, without nested boxes", () => {
  const row = source.slice(
    source.indexOf("function OpeningExperienceSubjectRow"),
    source.indexOf("function SetDesirabilitySubjectRow")
  );

  // Name and demand share on one line, then both paths beneath it.
  assert.ok(row.includes("subject.subjectName"));
  assert.ok(row.includes("% of roster demand"));
  const accessible = row.indexOf('kind="Accessible Path"');
  const arrow = row.indexOf("<OpeningPathStepArrow />");
  const elite = row.indexOf('kind="Elite Chase"');
  assert.ok(accessible >= 0 && arrow > accessible && elite > arrow, "a connector runs between the two routes");

  // No border inside the row and none around either path — the hairline
  // between subjects is the only separator the list needs.
  assert.ok(!/border-t|rounded-xl border/.test(row));
  const path = source.slice(
    source.indexOf("function OpeningExperiencePathCard"),
    source.indexOf("function OpeningPathStepArrow")
  );
  assert.ok(!/data-opening-path[^>]*border/.test(path), "a path must not be its own bordered card");
});

// ---------------------------------------------------------------------------
// No duplication between the summary and the detail views
// ---------------------------------------------------------------------------

test("the detail views do not repeat the headline scores already in the summary", () => {
  const roster = source.slice(
    source.indexOf("function CollectorRosterAppealPanel"),
    source.indexOf("function CollectorOpeningPathsPanel")
  );
  const paths = source.slice(
    source.indexOf("function CollectorOpeningPathsPanel"),
    source.indexOf("function CollectorProfileSection")
  );

  assert.ok(!roster.includes("presentation.scoreLabel"), "the Set Desirability score belongs to the summary");
  assert.ok(!roster.includes("presentation.rankLabel"), "its rank belongs to the summary");
  assert.ok(!paths.includes("collectorAppeal.scoreLabel"), "the Collector Appeal score belongs to the summary");
  assert.ok(!paths.includes("collectorAppeal.rankLabel"), "its rank belongs to the summary");

  // The supporting material is still there.
  assert.ok(roster.includes("presentation.components.map"));
  assert.ok(roster.includes("Top Desirability Drivers"));
  assert.ok(paths.includes("presentation.dualPathDepth"));
  assert.ok(paths.includes("presentation.chaseAppeal"));
  assert.ok(paths.includes('title="Pull paths for top subjects"'));
});

// ---------------------------------------------------------------------------
// The values behind the flow
// ---------------------------------------------------------------------------

test("the flow's three stages read canonical backend values", () => {
  const rip = {
    score: 28.6777,
    relativeScore: 64.11,
    rank: 11,
    tier: "C",
    cohortSize: 21,
    components: {
      financialRip: { score: 21.187, weight: 0.9, contribution: 19.0683 },
      openingDesirability: { score: 96.0942, weight: 0.1, contribution: 9.6094 },
    },
  };
  const ripCore = { score: 21.187, relativeScore: 60.45, rank: 12, tier: "D", cohortSize: 21 };
  const universal = { score: 95.4809, rank: 1, rankedSetCount: 135, coverage: { status: "full" } };
  const opening = {
    status: "available",
    collectorAppeal: { score: 96.0942, rank: 1, tier: "S", cohortSize: 21 },
  };

  const model = selectRipDesirabilityBreakdown(rip, ripCore, universal, opening);

  assert.equal(model.setDesirability.scoreLabel, "95.5");
  assert.equal(model.setDesirability.rankLabel, "#1 of 135");
  assert.equal(model.setDesirability.note, "Supporting input to Opening Desirability (CA7); not a separate Overall RIP weight.");

  assert.equal(model.openingDesirability.scoreLabel, "96.1");
  assert.equal(model.openingDesirability.rankLabel, "#1 of 21");
  assert.equal(model.openingDesirability.weightLabel, "10%");
  assert.equal(model.openingDesirability.contribution, 9.6094);

  // The 10% is applied to the ABSOLUTE model score (96.0942 x 0.1 = 9.60942),
  // never to the public cohort-relative presentation.
  assert.equal(Number((rip.components.openingDesirability.score * 0.1).toFixed(4)), 9.6094);
  assert.notEqual(model.openingDesirability.contribution, Number((64.11 * 0.1).toFixed(4)));

  // RIP Core supplies the other 90%.
  assert.equal(model.financialRip.weightLabel, "90%");
  assert.equal(model.financialRip.contribution, 19.0683);
});

test("effective expanded weights stay 54 / 22.5 / 13.5 / 10", () => {
  const model = selectRipDesirabilityBreakdown(
    {
      score: 30,
      components: {
        financialRip: { score: 20, weight: 0.9, contribution: 18 },
        openingDesirability: { score: 90, weight: 0.1, contribution: 9 },
      },
      effectiveWeights: { profit: 0.54, safety: 0.225, stability: 0.135, opening_desirability: 0.1 },
    },
    { score: 20 },
    { score: 80 },
    { status: "available", collectorAppeal: { score: 90 } }
  );

  assert.deepEqual(
    model.effectiveWeights.map((row) => [row.label, row.valueLabel]),
    [
      ["Profit", "54.0%"],
      ["Safety", "22.5%"],
      ["Stability", "13.5%"],
      ["Opening Desirability", "10.0%"],
    ]
  );
  // They total 100%, unlike the 60/25/15/10 misstatement.
  const total = model.effectiveWeights.reduce((sum, row) => sum + row.value, 0);
  assert.equal(Number(total.toFixed(4)), 1);
});
