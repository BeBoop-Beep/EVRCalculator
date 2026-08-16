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
const rankings = read("ExploreTopRankings.jsx");
const setPage = read("RipStatisticsPageClient.jsx");
const rankingsCss = read("explore.module.css");

test("Set Value and Top Chase consume the canonical market sparkline", () => {
  assert.ok(rankings.includes('import MarketSparkline from "./MarketSparkline"'));
  assert.ok(setPage.includes('import MarketSparkline from "@/components/explore/MarketSparkline"'));
  assert.ok(!rankings.includes("LineChart"), "the primitive ranking sparkline is gone");
});

test("canonical visual language includes frame, gradient, line, guide, marker, and edge dates", () => {
  for (const token of ["border-[var(--border-subtle)]", "linearGradient", "<polyline", "data-market-sparkline-guide", "data-market-sparkline-marker", "data-market-sparkline-dates"]) {
    assert.ok(shared.includes(token), `${token} must remain canonical`);
  }
});

test("ranking navigation and chart are siblings without event suppression", () => {
  const row = rankings.slice(rankings.indexOf("return <li key={target.setId}"), rankings.indexOf("</div></li>;"));
  const linkEnd = row.indexOf("aria-label={`${name} — open Set Market`} />");
  assert.ok(linkEnd > 0, "the row link is a self-closing stretched anchor, not a wrapper");
  assert.ok(row.indexOf("data-ranking-chart") > linkEnd, "the chart is a sibling of the link, never nested inside it");
  assert.ok(!rankings.includes("stopPropagation"));
});

test("the whole ranking row navigates while the chart opts out via stacking", () => {
  // The link covers the row instead of occupying the identity columns, so rank,
  // logo, name, era, value and change are all clickable from one anchor.
  assert.ok(rankingsCss.includes(".ladderNav {\n  position: absolute;\n  inset: 0;"));
  assert.ok(!rankingsCss.includes("grid-column: 1 / 3;"), "the link no longer claims grid cells");
  // ...and the chart sits above it rather than suppressing its events.
  assert.ok(rankingsCss.includes(".ladderRow > [data-ranking-chart] {\n  position: relative;\n  z-index: 2;\n}"));
});

test("tooltip delta uses the caller's selected-window baseline when given one", () => {
  assert.ok(shared.includes("computeChangeFromBaseline"), "the tooltip reuses the canonical window-delta helper");
  assert.ok(shared.includes("baselineValue = null"), "baseline-relative delta is opt-in per caller");
  assert.ok(
    rankings.includes("baselineValue={resolveDeltaWindowBaselineValue(movement, value)}"),
    "the rankings row derives the tooltip baseline from the same published movement as its summary chip"
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

test("mobile ranking chart spans the card and desktop trend width is unchanged", () => {
  assert.ok(!rankingsCss.includes("width: min(10rem, 42vw)"), "the mobile chart width cap is gone");
  assert.ok(rankingsCss.includes("grid-column: 1 / -1;"));
  assert.ok(rankings.includes('className="w-full"'));
  assert.ok(!rankings.includes("max-w-["), "no desktop cap is introduced on the rankings sparkline");
  assert.ok(rankingsCss.includes("grid-template-columns: 2.25rem minmax(9rem, 1.35fr) minmax(7rem, 1fr) minmax(8.5rem, auto);"));
});
