import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const shared = fs.readFileSync(path.join(here, "MarketSparkline.jsx"), "utf8");
const rankings = fs.readFileSync(path.join(here, "ExploreTopRankings.jsx"), "utf8");
const setPage = fs.readFileSync(path.join(here, "RipStatisticsPageClient.jsx"), "utf8");

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
  const linkEnd = row.indexOf("</Link>");
  assert.ok(linkEnd > 0);
  assert.ok(row.indexOf("data-ranking-chart") > linkEnd);
  assert.ok(!rankings.includes("stopPropagation"));
});

test("tooltip daily delta comes only from the prior loaded numeric point", () => {
  assert.ok(shared.includes("numericPoints[activeIndex - 1]"));
  assert.ok(shared.includes("activePoint.y - previousPoint.y"));
  assert.ok(shared.includes("previousPoint?.y ?"));
});
