const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const chartPath = path.join(__dirname, "CompactRankedBarChart.jsx");
const helpersPath = path.join(__dirname, "rankedBarChartFormatting.mjs");
const packageJsonPath = path.join(__dirname, "..", "..", "package.json");

test("CompactRankedBarChart is a static Recharts vertical bar chart with fixed label/value columns", () => {
  const source = fs.readFileSync(chartPath, "utf8").replace(/\r\n/g, "\n");

  // Shared reusable component with the agreed data-driven props.
  assert.ok(source.includes("export default function CompactRankedBarChart({"));
  for (const prop of ["rows", "valueKey", "labelKey", "rightLabelFormatter", "tooltipContent", "height", "barColor"]) {
    assert.ok(source.includes(prop), `CompactRankedBarChart must accept ${prop}`);
  }

  // Recharts horizontal-bars form: vertical layout, hidden numeric axis with a
  // readable "nice" ceiling, thin rounded-end bars, no animation.
  assert.ok(source.includes('layout="vertical"'));
  assert.ok(source.includes('<XAxis type="number" domain={[0, domainMaximum]} hide />'));
  assert.ok(source.includes("getNiceShareDomainMaximum"));
  assert.ok(source.includes("barSize={14}"));
  assert.ok(source.includes("radius={[0, 4, 4, 0]}"));
  assert.ok(source.includes("isAnimationActive={false}"));
  assert.ok(!source.includes("@keyframes"), "no keyframe/replay behavior");
  assert.ok(!source.includes("setInterval"), "no replay timers");

  // Fixed columns: category names left, compact values right — never text
  // forced inside the bars, so tiny bars stay readable.
  assert.ok(source.includes('type="category"'));
  assert.ok(source.includes('orientation="right"'), "a fixed right value column must exist");
  assert.ok(source.includes("truncateChartLabel"), "left labels truncate with ellipsis, one line");
  assert.ok(source.includes("<title>{fullLabel}</title>"), "full name stays available on the label");
  assert.ok(source.includes("interval={0}"), "every row keeps its label and value tick");

  // Compact geometry via the shared pure helper (~23px row pitch).
  assert.ok(source.includes("getCompactChartHeight"));

  // Tooltip escapes clipping and floats above neighbors.
  assert.ok(source.includes("allowEscapeViewBox={{ x: true, y: true }}"));
  assert.ok(source.includes('wrapperStyle={{ zIndex: 9999, pointerEvents: "none" }}'));
  assert.ok(source.includes("overflow-visible"), "chart wrappers must not clip the tooltip");

  // Site-native restraint: one teal/cyan series with a brighter hover, not a
  // per-category rainbow.
  assert.ok(source.includes("rgba(20,184,166"));
  assert.ok(source.includes("activeBar={{ fill: HOVER_BAR_COLOR }}"));

  // No D3 — Recharts only.
  assert.ok(!source.includes('from "d3'), "no D3 dependency in the chart");
});

test("no d3 package dependency is introduced", () => {
  const pkg = JSON.parse(fs.readFileSync(packageJsonPath, "utf8"));
  const allDeps = Object.keys({ ...(pkg.dependencies || {}), ...(pkg.devDependencies || {}) });
  assert.deepEqual(allDeps.filter((name) => name === "d3" || name.startsWith("d3-")), []);
});

test("compact bar chart pure helpers stay framework-free", () => {
  const source = fs.readFileSync(helpersPath, "utf8").replace(/\r\n/g, "\n");
  assert.ok(!source.includes("import React"), "helpers must stay pure/framework-free");
  assert.ok(!source.includes('from "recharts"'), "helpers must stay pure/framework-free");
  assert.ok(source.includes("export function getNiceShareDomainMaximum"));
  assert.ok(source.includes("export function sortRowsByValueDescending"));
  assert.ok(source.includes("export function truncateChartLabel"));
  assert.ok(source.includes("export function formatAbbreviatedCount"));
  assert.ok(source.includes("export function formatAbbreviatedCurrency"));
});
