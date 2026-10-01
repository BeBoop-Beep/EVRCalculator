import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";
import { RANKINGS_SELECTED_SURFACE, RANKINGS_SELECTED_BORDERED_SURFACE } from "../../lib/explore/rankingsSelectedState.mjs";

const read = (name) => fs.readFileSync(new URL(name, import.meta.url), "utf8");
const primitives = read("./RankingsScorePrimitives.jsx");
const control = read("../ui/SegmentedControl.jsx");
const css = read("./explore.module.css");
const chart = read("./FinancialRipHistoryChart.jsx");
const cards = read("./CardRankingsHub.jsx");
const collector = read("./CardCollectorAppealRankings.jsx");

test("shared selected surface is green/teal with white text, never yellow or white-grey", () => {
  for (const surface of [RANKINGS_SELECTED_SURFACE, RANKINGS_SELECTED_BORDERED_SURFACE]) {
    assert.match(surface, /rgba\(16,185,129/);
    assert.match(surface, /rgba\(20,184,166/);
    assert.match(surface, /text-white/);
    assert.doesNotMatch(surface, /yellow|amber|bg-white\/|sky-/);
  }
});

test("main RIP badge border resolves from the supplied tier", () => {
  const badge = primitives.slice(primitives.indexOf("export function RankingsRipScoreBadge"), primitives.indexOf("export function RankingsCompactScore"));
  assert.match(badge, /tier=\{metric\?\.tier\}/);
  assert.doesNotMatch(badge, /accentColor|192,132,252/);
});

test("benchmark component primitive uses its own tier, no caption and no arrow", () => {
  const prim = primitives.slice(primitives.indexOf("export function RankingsBenchmarkComponentScore"), primitives.indexOf("export function BenchmarkReferenceRow"));
  assert.match(prim, /getTierTone\(metric\.tier\)/);
  assert.match(prim, /borderColor: tone\?\.accentColor/);
  assert.match(prim, /aria-label=\{`\$\{label\}:/);
  assert.doesNotMatch(prim, /deltaVsBenchmark|Position|[▲▼↑↓]|<small|<caption/);
  assert.match(prim, /aria-hidden="true">\{available/);
});

test("Rankings segmented variants and pill/family/graph/cards use the green selected state", () => {
  assert.doesNotMatch(control, /bg-white\/\[\.11\]/);
  assert.equal(control.split("RANKINGS_SELECTED_SURFACE").length - 1 >= 3, true);
  assert.match(css, /\.productFamilyTabActive \{[^}]*rgba\(16,185,129[^}]*color: #fff/);
  assert.doesNotMatch(css.match(/\.productFamilyTabActive \{[^}]*\}/)[0], /rgba\(255,255,255,\.11\)/);
  assert.equal(chart.split("RANKINGS_SELECTED_BORDERED_SURFACE").length - 1, 3);
  assert.doesNotMatch(chart, /bg-white\/10|border-sky-400\/40/);
  assert.match(cards, /variant="rankings"/);
  assert.match(collector, /variant="rankings"/);
});

test("accessibility semantics and the generic primary/pill variants are preserved", () => {
  assert.match(control, /aria-checked=\{isActive\}/);
  assert.match(control, /focus-visible:ring-2/);
  assert.match(control, /ArrowRight/);
  assert.match(control, /disabled:opacity-40/);
  assert.match(chart, /aria-checked=\{mode === item\.key\}/);
  assert.match(chart, /aria-checked=\{value === item\.key\}/);
  // The default (non-Rankings) pill selection is untouched.
  assert.match(control, /bg-\[rgba\(20,184,166,0\.16\)\] text-\[var\(--accent\)\]/);
  for (const source of [control, css, chart, primitives]) assert.doesNotMatch(source, /text-yellow|text-amber|color: *(#fde047|#facc15)/);
});
