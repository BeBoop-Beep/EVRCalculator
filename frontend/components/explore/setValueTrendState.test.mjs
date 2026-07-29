import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const source = fs
  .readFileSync(path.resolve(here, "RipStatisticsPageClient.jsx"), "utf8")
  .replace(/\r\n/g, "\n");

const card = source.slice(
  source.indexOf("function SetValueTrendCard("),
  source.indexOf("function OverviewMetricTile(")
);

test("the chart identity does not depend on anything a rerender can jiggle", () => {
  const keyLine = /const chartKey = `([^`]+)`;/.exec(card);
  assert.ok(keyLine, "chartKey must be locatable");
  const key = keyLine[1];
  // A remount discards the active point and replays the mount animation. The
  // key may only change when the underlying series genuinely changes identity.
  for (const forbidden of ["window.innerWidth", "isDesktopComposition", "pointerMode", "isCoarsePointer", "activeIndex"]) {
    assert.ok(!key.includes(forbidden), `chartKey must not include ${forbidden}`);
  }
  assert.ok(key.includes("${setId"), "set identity is a legitimate remount trigger");
  assert.ok(key.includes("${selectedTrend.scope}"), "scope change is a legitimate remount trigger");
});

test("the timeframe reset is scoped to set and scope changes only", () => {
  const resetEffect = /useEffect\(\(\) => \{\s*setSelectedWindowKey\(null\);\s*\}, \[([^\]]+)\]\);/.exec(card);
  assert.ok(resetEffect, "the reset effect must be locatable");
  const deps = resetEffect[1].split(",").map((entry) => entry.trim()).filter(Boolean);
  assert.deepEqual(deps.sort(), ["selectedScope", "setId"], "no other dependency may reset the timeframe");
});

test("the selected scope is owned above the card so a card rerender cannot lose it", () => {
  assert.ok(card.includes("selectedScope = CANONICAL_SET_VALUE_SCOPE,"), "scope is a prop, not local state");
  assert.ok(card.includes("onSelectedScopeChange"), "scope changes are lifted to the page");
  assert.ok(
    source.includes("selectedScope={setValueTrendScope}") && source.includes("onSelectedScopeChange={setSetValueTrendScope}"),
    "the page owns Checklist / Hits / Top 10 state"
  );
});

test("pointer mode and composition never gate the data the chart receives", () => {
  // Parity: responsive state may change presentation and interaction, never
  // which points, series or timeframe the chart is given.
  const lineChart = source.slice(
    source.indexOf("function SetValueLineChart("),
    source.indexOf("function SetValueTrendCard(")
  );
  assert.ok(
    !/isDesktopComposition\s*\?\s*[a-zA-Z]*[Pp]oints/.test(lineChart),
    "the point series must not branch on composition"
  );
  assert.ok(
    !/isCoarsePointer\s*\?\s*[a-zA-Z]*[Pp]oints/.test(lineChart),
    "the point series must not branch on pointer mode"
  );
  assert.ok(lineChart.includes("data={numericPoints}"), "one data source feeds the chart at every width");
});
