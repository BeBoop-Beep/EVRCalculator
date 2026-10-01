import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const read = (name) => fs.readFileSync(new URL(name, import.meta.url), "utf8");

test("benchmark /10 badge hides its redundant caption and decorative position arrow", () => {
  const primitive = read("./RankingsScorePrimitives.jsx");
  const badge = read("./RipScoreBadge.jsx");
  assert.match(primitive, /scoreScale=\{RIP_SCORE_SCALE_BENCHMARK_10\}/);
  assert.doesNotMatch(primitive, /192,132,252|accentColor="/);
  assert.match(primitive, /accentColor=\{getBenchmarkTierTone\(metric\?\.tier\)\?\.accentColor\}/);
  assert.match(primitive, /showLabel=\{false\}/);
  assert.doesNotMatch(primitive, /BenchmarkPositionIndicator|data-benchmark-position|deltaVsBenchmark/);
  assert.match(badge, /<span className="sr-only">\{label\}<\/span>/);
  assert.match(badge, />\/ 10</);
});

test("component scores are accessible neutral numbers without internal decoration", () => {
  const primitive = read("./RankingsScorePrimitives.jsx");
  const table = read("./BenchmarkEntityScoreTable.jsx");
  assert.match(primitive, /data-rankings-neutral-metric aria-label=/);
  assert.match(primitive, /font-semibold tabular-nums text-\[var\(--text-primary\)\]/);
  const neutral = primitive.slice(primitive.indexOf("export function RankingsNeutralMetric"), primitive.indexOf("// Benchmark Set/Era component score"));
  assert.doesNotMatch(neutral, /data-rankings-compact-score|borderColor|rounded-lg border bg-/);
  assert.match(table, /RankingsBenchmarkComponentScore metric=\{row\[column\.key\]\} label=\{column\.label\}/);
});

test("rankings Set identity uses bounded artwork projections on primary surfaces", () => {
  const metric = read("./SetRipScoreLeaderboard.jsx");
  const packs = read("./SetPackMetrics.jsx");
  const overview = read("./RankingsOverviewHighlights.jsx");
  for (const source of [metric, packs, overview]) assert.match(source, /SetIdentity/);
  assert.match(packs, /logo_image_url: row\.logoImageUrl/);
  assert.match(packs, /variant="compact"/);
  assert.match(packs, /variant="mobileRanking"/);
  assert.doesNotMatch(packs, /fetch\(|axios|useSWR/);
});

test("rankings-only toggles use green selection with white text and keep visible focus", () => {
  const control = read("../ui/SegmentedControl.jsx");
  const lazy = read("./RankingsLazyClient.jsx");
  const css = read("./explore.module.css");
  assert.match(lazy, /variant="rankingsPrimary"/);
  assert.match(control, /variant === "rankings"/);
  assert.doesNotMatch(control, /bg-white\/\[\.11\]/);
  assert.match(control, /RANKINGS_SELECTED_SURFACE/);
  assert.match(css, /productFamilyTab:focus-visible/);
});

test("Product calibration remains pending and is not converted in B2 presentation code", () => {
  const product = read("./RankingsProductLensClient.jsx");
  assert.doesNotMatch(product, /overallRipScore\s*\/\s*10|Math\.min\(\s*10|Math\.max\(\s*0/);
  assert.doesNotMatch(product, /benchmarkReferenceScore\s*:/);
  assert.match(product, /row\.ripScore/);
});
