import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const read = (relativePath) =>
  fs.readFileSync(path.join(here, relativePath), "utf8").replace(/\r\n/g, "\n");

const pageSource = read("RipStatisticsPageClient.jsx");
const collectorContract = read("CollectorProfile.contract.test.mjs");
const segmentedSource = read("../ui/SegmentedControl.jsx");
const timeRangeSource = read("TimeRangeSelector.jsx");

const between = (text, startToken, endToken) => {
  const start = text.indexOf(startToken);
  assert.ok(start >= 0, `missing ${startToken}`);
  const end = text.indexOf(endToken, start);
  assert.ok(end > start, `missing ${endToken} after ${startToken}`);
  return text.slice(start, end);
};

test("Collector Profile uses one desktop branch and one mobile branch at the shared 1200px breakpoint", () => {
  const section = between(pageSource, "function CollectorProfileSection", "const TOP_CARD_IMAGE_CONTAINER_CLASS");

  assert.ok(section.includes('const isDesktopCollectorProfile = useMediaQuery("(min-width: 1200px)", true);'));
  assert.ok(section.includes("isDesktopCollectorProfile ? ("));
  assert.ok(section.includes("<CollectorProfileMobileSummary desirability={desirability} collectorAppeal={opening} />"));
  assert.ok(section.includes("<CollectorRosterAppealPanel presentation={desirability}"));
  assert.ok(section.includes("<CollectorOpeningPathsPanel presentation={opening}"));
});

test("mobile summary replaces the stacked contribution block with two score cells and explicit relationship lines", () => {
  const summary = between(pageSource, "function CollectorProfileMobileSummary", "function CollectorProfileMobilePathRow");

  assert.ok(summary.includes("grid grid-cols-2 divide-x divide-[var(--border-subtle)]"));
  assert.ok(summary.includes("Set desirability informs Collector Appeal"));
  assert.ok(summary.includes("Overall RIP = 90% RIP Core + 10% Collector Appeal"));
  assert.ok(!summary.includes("RIP Score Contribution"));
  assert.ok(!summary.includes("9.6 model points"));
});

test("mobile Collector Profile switcher is one shared full-width equal-segment control", () => {
  const section = between(pageSource, "function CollectorProfileSection", "const TOP_CARD_IMAGE_CONTAINER_CLASS");

  assert.ok(section.includes('ariaLabel="Collector Profile view"'));
  assert.ok(section.includes("equalWidth"));
  assert.ok(section.includes("mobileFullWidth"));
  assert.ok(section.includes('{ value: COLLECTOR_PROFILE_ROSTER_VIEW, label: "Roster Appeal" }'));
  assert.ok(section.includes('{ value: COLLECTOR_PROFILE_PATHS_VIEW, label: "Opening Paths" }'));
});

test("mobile roster view keeps all six metrics in shared three-column strips and only the top three drivers visible", () => {
  const roster = between(pageSource, "function CollectorProfileMobileRosterPanel", "function CollectorProfileMobileOpeningPathsPanel");

  assert.equal((roster.match(/<CollectorMetricRow>/g) || []).length, 2);
  for (const label of ["Chase Strength", "Chase Depth", "Hit Coverage", "Effective Subjects", "Top Subject", "Top 3"]) {
    assert.ok(roster.includes(`label="${label}"`), `${label} must remain visible`);
  }
  assert.ok(roster.includes("presentation.topSubjects.slice(0, 3)"));
  assert.ok(roster.includes('title="Profile details"'));
});

test("Collector metric strips stay three columns below desktop with shrink-safe cells", () => {
  const row = between(pageSource, "function CollectorMetricRow", "function CollectorMetricCell");
  const cell = between(pageSource, "function CollectorMetricCell", "function CollectorProfileMobileSummaryCell");

  assert.ok(row.includes('columns === 2 ? "grid-cols-2" : "grid-cols-3"'));
  assert.ok(cell.includes("min-w-0"));
  assert.ok(cell.includes("text-lg font-semibold leading-none tabular-nums"));
});

test("mobile opening paths leads with Access Path and Elite Path and moves supporting routes behind one disclosure", () => {
  const panel = between(pageSource, "function CollectorProfileMobileOpeningPathsPanel", "function CollectorProfileSection");

  assert.ok(panel.includes('title="Access Path"'));
  assert.ok(panel.includes('title="Elite Path"'));
  assert.ok(panel.includes('title="Path details"'));
  assert.ok(panel.includes("presentation.topSubjects.find((subject) => subject.accessiblePath)"));
  assert.ok(panel.includes("presentation.topSubjects.find((subject) => subject.elitePath)"));
  assert.ok(panel.includes("<OpeningExperienceSubjectRow"));
});

test("shared segmented control supports equal-width segments and full-width mobile distribution", () => {
  assert.ok(segmentedSource.includes("equalWidth = false"));
  assert.ok(segmentedSource.includes("mobileFullWidth = false"));
  assert.ok(segmentedSource.includes("style={equalWidthStyle}"));
  assert.ok(segmentedSource.includes("max-desk:flex-1 max-desk:basis-0 max-desk:justify-center"));
  assert.ok(segmentedSource.includes('role="radiogroup"'));
  assert.ok(segmentedSource.includes('role="radio"'));
  assert.ok(segmentedSource.includes('focus-visible:ring-2'));
  assert.ok(segmentedSource.includes('"ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Home", "End"'));
});

test("Set/Top 10, RIP Score/RIP Core, and Collector Profile all opt into the shared equal-width control foundation", () => {
  assert.ok(pageSource.includes('ariaLabel="Set scope"'));
  assert.ok(pageSource.includes('ariaLabel="RIP score mode"'));
  assert.ok(pageSource.includes('ariaLabel="Collector Profile view"'));

  const setScope = between(pageSource, "function SetValueScopeSelector", "function formatAxisCurrency");
  const ripMode = between(pageSource, "function RipScoreModeToggle", "function HeroScoreBadges");
  assert.ok(setScope.includes("equalWidth"));
  assert.ok(ripMode.includes("equalWidth"));
});

test("time range source of truth renders LT everywhere while keeping Lifetime as the accessible name", () => {
  assert.ok(timeRangeSource.includes('{ key: "lifetime", desktopLabel: "LT", mobileLabel: "LT", ariaLabel: "Lifetime" }'));
  assert.ok(!timeRangeSource.includes('desktopLabel: "LIFETIME"'));
  assert.ok(!timeRangeSource.includes('const VISIBLE_TIME_RANGE_LABELS = new Set(["1D", "7D", "30D", "3M", "6M", "1Y", "LT", "LIFETIME"])'));
});

test("return-to-top visibility is derived directly from the shared mobile set-context hidden state", () => {
  assert.ok(pageSource.includes("const showReturnToTop = isMobileSetContextHidden;"));
  assert.ok(!pageSource.includes("const [showReturnToTop, setShowReturnToTop] = useState(false);"));
  assert.ok(!pageSource.includes("window.innerHeight * 1.4"));
  assert.ok(pageSource.includes("revealMobileSetContext();\n                      window.scrollTo({ top: 0, behavior: \"smooth\" });"));
});

test("existing Collector Profile contract file is still present to guard desktop chain semantics", () => {
  assert.ok(collectorContract.includes("the summary states one directed chain"));
  assert.ok(collectorContract.includes("the two scores are stages of a chain, never options of a toggle"));
});