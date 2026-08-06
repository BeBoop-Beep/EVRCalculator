// Shared set-page mobile control contracts.
//
// PROVENANCE: these three requirements were the only ones in
// CollectorProfileMobileOverhaul.contract.test.mjs that were NOT about the
// Collector Profile. That suite was deleted with the section it tested; these
// were moved here first rather than dropped, because each guards a control that
// is still on the page and is used by surfaces that have nothing to do with
// Collector Appeal:
//
//   - SegmentedControl's equal-width / full-width-on-mobile foundation, still
//     used by the Set/Top 10 scope selector and the Simulation Results tabs;
//   - the time-range selector's "LT" labelling;
//   - the return-to-top trigger's derivation from the shared mobile
//     set-context state.
//
// The Collector-Profile-specific assertions that lived alongside them (the
// 1200px desktop/mobile branch, the "Collector Profile view" tab control, the
// roster and opening-path mobile panels, the six-metric strips) are gone with
// the section itself and are deliberately not reproduced here.

import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const read = (relativePath) =>
  fs.readFileSync(path.join(here, relativePath), "utf8").replace(/\r\n/g, "\n");

const pageSource = read("RipStatisticsPageClient.jsx");
const segmentedSource = read("../ui/SegmentedControl.jsx");
const timeRangeSource = read("TimeRangeSelector.jsx");

const between = (text, startToken, endToken) => {
  const start = text.indexOf(startToken);
  assert.ok(start >= 0, `missing ${startToken}`);
  const end = text.indexOf(endToken, start);
  assert.ok(end > start, `missing ${endToken} after ${startToken}`);
  return text.slice(start, end);
};

test("shared segmented control supports equal-width segments and full-width mobile distribution", () => {
  assert.ok(segmentedSource.includes("equalWidth = false"));
  assert.ok(segmentedSource.includes("mobileFullWidth = false"));
  assert.ok(segmentedSource.includes("style={equalWidthStyle}"));
  assert.ok(segmentedSource.includes("max-desk:flex-1 max-desk:basis-0 max-desk:justify-center"));
  assert.ok(segmentedSource.includes('role="radiogroup"'));
  assert.ok(segmentedSource.includes('role="radio"'));
  assert.ok(segmentedSource.includes("focus-visible:ring-2"));
  assert.ok(segmentedSource.includes('"ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Home", "End"'));
});

test("the Set/Top 10 scope control opts into the shared equal-width foundation", () => {
  // The RIP score-mode control is gone: RIP Core is Financial RIP V2 and is not
  // a current alternative to the RIP Score, so there is one headline and no
  // toggle to size. The "Collector Profile view" control is gone with its
  // section, so neither aria-label may reappear.
  assert.ok(pageSource.includes('ariaLabel="Set scope"'));
  assert.ok(!pageSource.includes('ariaLabel="RIP score mode"'));
  assert.ok(!pageSource.includes('ariaLabel="Collector Profile view"'));

  const setScope = between(pageSource, "function SetValueScopeSelector", "function formatAxisCurrency");
  assert.ok(setScope.includes("equalWidth"));
});

test("time range source of truth renders LT everywhere while keeping Lifetime as the accessible name", () => {
  assert.ok(
    timeRangeSource.includes('{ key: "lifetime", desktopLabel: "LT", mobileLabel: "LT", ariaLabel: "Lifetime" }')
  );
  assert.ok(!timeRangeSource.includes('desktopLabel: "LIFETIME"'));
  assert.ok(
    !timeRangeSource.includes(
      'const VISIBLE_TIME_RANGE_LABELS = new Set(["1D", "7D", "30D", "3M", "6M", "1Y", "LT", "LIFETIME"])'
    )
  );
});

// KNOWN PRE-EXISTING FAILURE, carried over unchanged.
//
// This assertion fails on the clean tree at commit 1593a92, before any of the
// Frontend Pass 2 work: RipStatisticsPageClient still holds `showReturnToTop`
// in `useState` rather than deriving it from `isMobileSetContextHidden`. It is
// preserved verbatim rather than relaxed, deleted or marked `todo`, because the
// requirement is still the intended one and softening it here would quietly
// retire a real signal while the section that happened to host the test was
// being removed. Fixing the page is out of scope for this pass.
test("return-to-top visibility is derived directly from the shared mobile set-context hidden state", () => {
  assert.ok(pageSource.includes("const showReturnToTop = isMobileSetContextHidden;"));
  assert.ok(!pageSource.includes("const [showReturnToTop, setShowReturnToTop] = useState(false);"));
  assert.ok(!pageSource.includes("window.innerHeight * 1.4"));
  assert.ok(
    pageSource.includes('revealMobileSetContext();\n                      window.scrollTo({ top: 0, behavior: "smooth" });')
  );
});
