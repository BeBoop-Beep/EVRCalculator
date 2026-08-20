import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
// These sources are checked out with mixed CRLF/LF, so every multi-line anchor
// below is matched against LF-normalized text.
const read = (name) => fs.readFileSync(path.join(here, name), "utf8").replace(/\r\n/g, "\n");
const shared = read("MarketSparkline.jsx");
const setMarket = read("SetMarketExplorer.jsx");
const setPage = read("RipStatisticsPageClient.jsx");

test("Set Market and Top Chase consume the canonical market sparkline", () => {
  assert.ok(setMarket.includes('import MarketSparkline from "./MarketSparkline"'));
  assert.ok(setPage.includes('import MarketSparkline from "@/components/explore/MarketSparkline"'));
  assert.ok(!setMarket.includes("LineChart"), "no second charting primitive on the Market page");
});

test("canonical visual language includes frame, gradient, line, guide, marker, and edge dates", () => {
  for (const token of ["border-[var(--border-subtle)]", "linearGradient", "<polyline", "data-market-sparkline-guide", "data-market-sparkline-marker", "data-market-sparkline-dates"]) {
    assert.ok(shared.includes(token), `${token} must remain canonical`);
  }
});

test("Set Market mounts exactly ONE sparkline — the selected set's, never one per row", () => {
  // The scalability rule the master-detail redesign exists to enforce: a
  // 167-set catalogue must not mount 167 interactive charts.
  assert.equal((setMarket.match(/<MarketSparkline/g) || []).length, 1, "one chart in the whole component");
  const listPane = setMarket.slice(setMarket.indexOf("const listPane ="), setMarket.indexOf("const detailPane ="));
  assert.ok(!listPane.includes("MarketSparkline"), "the set list renders no chart at all");
  assert.ok(!listPane.includes("Sparkline"), "not even a wrapper around one");
});

test("the selected-set chart is a sibling of the row buttons, never nested in one", () => {
  const listPane = setMarket.slice(setMarket.indexOf("const listPane ="), setMarket.indexOf("const detailPane ="));
  // Rows are real buttons with no nested interactive children, so nothing has
  // to be repaired with event suppression.
  assert.ok(listPane.includes("<button"), "each row is a real button");
  assert.ok(!setMarket.includes("stopPropagation"));
});

test("tooltip delta uses the caller's selected-window baseline when given one", () => {
  assert.ok(shared.includes("computeChangeFromBaseline"), "the tooltip reuses the canonical window-delta helper");
  assert.ok(shared.includes("baselineValue = null"), "baseline-relative delta is opt-in per caller");
  assert.ok(
    setMarket.includes("baselineValue={resolveDeltaWindowBaselineValue(detailMovement, selected.value)}"),
    "the selected-set chart derives the tooltip baseline from the same published movement as its summary chip"
  );
  // Callers with no window concept keep the point-over-point reading.
  assert.ok(shared.includes("activePoint.y - previousPoint.y"));
});

test("the tooltip escapes its clipping ancestors through a body portal", () => {
  assert.ok(shared.includes('import { createPortal } from "react-dom"'));
  assert.ok(shared.includes("document.body"));
  assert.ok(shared.includes('className="fixed z-[80]"'));
  assert.ok(!shared.includes("bottom-[calc(100%+0.55rem)]"), "no absolute positioning inside the clipped plot");
});

test("the selected-set chart is given real height and no width cap", () => {
  assert.ok(setMarket.includes('className="w-full"'), "the chart fills its pane");
  assert.ok(setMarket.includes('plotClassName="h-44 desk:h-[15rem]"'), "a readable plot on both compositions");
  // Scoped to the chart itself — the toolbar's search field legitimately caps
  // its own desktop width.
  const chart = setMarket.slice(setMarket.indexOf("<MarketSparkline"), setMarket.indexOf("<SetMarketTopMovers"));
  assert.ok(!chart.includes("max-w-"), "no width cap is introduced on the Set Market chart");
});
