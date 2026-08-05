// The Collector Profile — the "02 · Collector Profile" section on the set-page
// Insights tab.
//
// It replaced two sibling sections ("Set Desirability" and "Simulation Opening
// Experience") that left the reader to guess how they related.
//
// This section used to open with a three-stage flow — Set Desirability ->
// Collector Appeal -> RIP Score Contribution — drawn with arrows. That flow has
// been removed: it claimed a sequential pipeline the model does not have, and
// its final stage published a composition weight and a contribution in model
// points. Collector Appeal's score and its three canonical V3 factors are now
// presented once, under RIP Score. What remains here is the EVIDENCE behind
// them: Roster Appeal and Opening Paths.
//
// Two things this file exists to protect:
//
//   1. no sequential chain and no published weight returns to this section; and
//   2. the two panels keep SEPARATE availability, because they fail for
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

test("the sequential Set Desirability -> Collector Appeal -> contribution flow is gone", () => {
  // It claimed Roster Desirability is a first STAGE feeding Collector Appeal.
  // The three Collector Appeal V3 factors are parallel inputs to one weighted
  // combination, and the final stage published a weight and a contribution in
  // model points - both internal to the model.
  const section = collectorProfileSection();
  assert.ok(!section.includes("data-collector-profile-flow"));
  assert.ok(!section.includes('label="RIP Score Contribution"'));
  assert.ok(!section.includes("<CollectorProfileArrow"));
  assert.ok(!section.includes("<CollectorProfileStage"));
  assert.ok(!section.includes("ripContribution"));
  const sectionCode = section
    .split("\n")
    .filter((line) => !line.trimStart().startsWith("//") && !line.trimStart().startsWith("*"))
    .join("\n");
  assert.ok(!/\d+%/.test(sectionCode), "no weight percentage may sit in this section");
  // The components themselves are gone from the page, not merely unused.
  assert.ok(!source.includes("function CollectorProfileArrow("));
  assert.ok(!source.includes("function CollectorProfileStage("));
});

test("Set Desirability is still labelled as supporting context, not a RIP weight", () => {
  assert.ok(
    SET_DESIRABILITY_BULLETS.includes(
      "Supports Collector Appeal but does not receive its own RIP Score weight."
    )
  );
});

test("no tooltip publishes a composition weight", () => {
  for (const [name, bullets] of [
    ["COLLECTOR_PROFILE_INFO_BULLETS", COLLECTOR_PROFILE_BULLETS],
    ["COLLECTOR_APPEAL_INFO_BULLETS", COLLECTOR_APPEAL_BULLETS],
    ["SET_DESIRABILITY_INFO_BULLETS", SET_DESIRABILITY_BULLETS],
  ]) {
    for (const bullet of bullets) {
      assert.ok(!/\d+%/.test(bullet), name + ' must not state a weight: ' + bullet);
      assert.ok(!/contributes \d/i.test(bullet), name + ' must not state a contribution: ' + bullet);
    }
  }
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

// The following were removed with selectRipDesirabilityBreakdown and the
// Overall RIP v4 construction strip it fed:
//   * the "missing CA7 explains RIP Score's absence" copy test, whose
//     asserted sentence named "CA7" and "RIP Core" on a public surface;
//   * the three-stage flow value test and the effective 54/22.5/13.5/10
//     weight test, both of which published composition weights.
// A missing Collector Appeal now renders the backend status reason on the
// canonical V3 surface; see CollectorAppealBreakdown.contract.test.mjs.

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

  // The surviving facts, one per bullet. The two that stated a 10% weight are
  // deliberately absent: no public tooltip publishes a composition weight.
  assert.ok(
    COLLECTOR_APPEAL_BULLETS.includes("One of the two halves of RIP Score, alongside Financial RIP.")
  );
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
    assert.ok(bullets.length >= 5, `${name} must be at least five bullets`);
    for (const bullet of bullets) {
      // One idea per bullet: no bullet may itself be a two-sentence paragraph.
      assert.ok(bullet.length <= 120, `${name} bullet is too long: ${bullet}`);
      assert.ok(!/\.\s+\S/.test(bullet), `${name} bullet packs two sentences: ${bullet}`);
    }
  }

  // The section heading still reads its array rather than a prose string.
  assert.ok(source.includes("titleInfoText={infoBullets(COLLECTOR_PROFILE_INFO_BULLETS)}"));
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

