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
  // The mobile summary block went with the sequential flow; both widths now
  // open straight on the view tabs and their panels.
  assert.ok(!section.includes("<CollectorProfileMobileSummary"));
  assert.ok(section.includes("<CollectorRosterAppealPanel presentation={desirability}"));
  assert.ok(section.includes("<CollectorOpeningPathsPanel presentation={opening}"));
});

// The CollectorProfileMobileSummary test stood here. That summary printed
// "Overall RIP = 90% RIP Core + 10% Collector Appeal" - a superseded model and a
// published composition weight - and it was the mobile half of the sequential
// Set Desirability -> Collector Appeal -> contribution flow. Both are removed.

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
  const cell = between(pageSource, "function CollectorMetricCell", "function CollectorProfileMobileRosterPanel");

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

test("Set/Top 10 and Collector Profile opt into the shared equal-width control foundation", () => {
  // The RIP score-mode control is gone: RIP Core is Financial RIP V2 and is not
  // a current alternative to the RIP Score, so there is one headline and no
  // toggle to size.
  assert.ok(pageSource.includes('ariaLabel="Set scope"'));
  assert.ok(!pageSource.includes('ariaLabel="RIP score mode"'));
  assert.ok(pageSource.includes('ariaLabel="Collector Profile view"'));

  const setScope = between(pageSource, "function SetValueScopeSelector", "function formatAxisCurrency");
  assert.ok(setScope.includes("equalWidth"));
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

test("the Collector Profile contract file guards the RETIRED chain semantics", () => {
  // It now asserts the flow is GONE rather than that it is drawn correctly.
  assert.ok(
    collectorContract.includes("the sequential Set Desirability -> Collector Appeal -> contribution flow is gone")
  );
  assert.ok(collectorContract.includes("no tooltip publishes a composition weight"));
});