import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";
import { resolvePaidScorecards } from "../../lib/rankings/paidScorecardVisibility.mjs";
import { SET_RANKING_VIEWS } from "./setRankingViews.mjs";

const read = (name) => fs.readFileSync(new URL(name, import.meta.url), "utf8").replace(/\r\n/g, "\n");
const lazy = read("./RankingsLazyClient.jsx");
const hub = read("./SetRankingsHub.jsx");
const era = read("./EraRankings.jsx");
const setBoard = read("./SetRipScoreLeaderboard.jsx");
const table = read("./BenchmarkEntityScoreTable.jsx");
const hook = read("../../lib/rankings/usePaidScorecards.js");
const model = read("./unifiedScoreTableModel.mjs");

test("Era data path: public Overall renders first, the paid wide scorecard merges only when entitled", () => {
  assert.equal((lazy.match(/readPublicRankingsHeadlines\("era"/g) || []).length, 1);
  assert.match(era, /usePaidScorecards\("era", \{ sessionCache, entitled: canViewRankingsIntelligence \}\)/);
  assert.match(era, /mergeScorecardRows\(scorecards, canViewRankingsIntelligence \? paid\.scorecards : null\)/);
  assert.match(lazy, /canViewRankingsIntelligence=\{canViewRankingsIntelligence\}/);
  assert.match(lazy, /key=\{sessionCache\.identity\}/);
  // The public render is never awaited behind the paid request.
  assert.doesNotMatch(era, /await |readRankingsScorecards/);
});

test("Set data path: one public read, one paid wide scorecard, no per-metric or per-row reads", () => {
  assert.equal((lazy.match(/readPublicRankingsHeadlines\("set"/g) || []).length, 1);
  assert.match(setBoard, /usePaidScorecards\("set", \{ sessionCache, entitled: canViewRankingsIntelligence \}\)/);
  assert.equal((hook.match(/readRankingsScorecards\(/g) || []).length, 1);
  for (const source of [era, setBoard, table, model, hub]) assert.doesNotMatch(source, /\bfetch\(|metric=financial|lens=(financial|collector|chase)/);
  assert.match(hook, /readRankingsScorecards\(entityType, \{ sessionCache \}\)/);
});

test("sorting and search are client-local: no request is made from the table or the model", () => {
  assert.doesNotMatch(table, /readRankings|fetch\(|sessionCache|useEffect/);
  assert.doesNotMatch(model, /fetch|import /);
  assert.match(table, /sortScoreRows\(filterScoreRows\(rows, \{ query, eraFilter \}\), sort\)/);
});

test("rank and tier are never reimplemented in React: only canonical metric values are read", () => {
  for (const source of [table, era, setBoard, model]) {
    assert.doesNotMatch(source, /tier\s*=\s*|calculateTier|benchmarkTier|rankFromIndex|index \+ 1/);
    assert.doesNotMatch(source, /\b(4\.75|5\.25)\b|Math\.abs\(/);
  }
  assert.match(table, /displayedRank\(row, sortKey\)/);
});

test("access transitions: paid cells vanish immediately on downgrade, late/other-identity responses are ignored", () => {
  const state = { identity: "user-a:2026-09-30", status: "ready", scorecards: { rows: [1] } };
  assert.deepEqual(resolvePaidScorecards({ entitled: true, identity: "user-a:2026-09-30", state }).scorecards, { rows: [1] });
  assert.equal(resolvePaidScorecards({ entitled: false, identity: "user-a:2026-09-30", state }).scorecards, null);
  assert.equal(resolvePaidScorecards({ entitled: true, identity: "user-b:2026-09-30", state }).scorecards, null);
  assert.equal(resolvePaidScorecards({ entitled: true, identity: null, state }).scorecards, null);
  assert.equal(resolvePaidScorecards({ entitled: false, identity: "user-a:2026-09-30", state }).status, "idle");
  assert.match(hook, /let live = true;/);
  assert.match(hook, /if \(live\) setState/);
  assert.match(hook, /return \(\) => \{ live = false; \};/);
  assert.match(hook, /if \(!entitled \|\| !sessionCache\) \{\s*setState\(\{ identity: null, status: "idle", scorecards: null \}\)/);
  // The cache identity carries the access identity AND the publication.
  assert.match(lazy, /createRankingsSessionCache\(`\$\{requestKey\}:\$\{publicationIdentity\}`\)/);
});

test("Set navigation is exactly RIP Score + Pack Economics and Pack Economics is still separate", () => {
  assert.deepEqual(SET_RANKING_VIEWS.map((view) => view.value), ["ripScore", "packEconomics"]);
  assert.match(hub, /view === "packEconomics"/);
  assert.match(hub, /<SetPackMetrics/);
  assert.doesNotMatch(table, /SetPackMetrics|packEconomics/i);
});

test("Era -> Sets handoff keeps the Era filter and opens the unified Set table", () => {
  assert.match(era, /onSelectEra\?\.\(\{ eraId: row\.entityId, eraName: row\.name/);
  assert.match(lazy, /setSelectedEra\(era\?\.eraName \|\| null\)/);
  assert.match(lazy, /setSetEntryView\("ripScore"\)/);
  assert.match(lazy, /eraFilter=\{selectedEra\}/);
  assert.match(setBoard, /eraFilter=\{eraFilter\}/);
  // Score cells are plain values, not navigation targets.
  assert.doesNotMatch(table, /ScoreCell[^\n]*(onClick|href)/);
});

test("B1 regressions: selected-state styling, absolute tier helper and Product scale are untouched", () => {
  assert.match(read("../../lib/explore/rankingsSelectedState.mjs"), /rgba\(16,185,129/);
  assert.match(table, /styles\.productFamilyTabActive/);
  assert.ok(!/white\/\[\.11\]/.test(read("../ui/SegmentedControl.jsx")));
  const product = read("./RankingsProductLensClient.jsx");
  assert.doesNotMatch(product, /overallRipScore\s*\/\s*10|benchmarkReferenceScore\s*:/);
  assert.match(product, /row\.ripScore/);
});
