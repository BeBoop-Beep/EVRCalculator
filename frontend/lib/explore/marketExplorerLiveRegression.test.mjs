// Regression guards for the live-develop Explorer defects (Fossil -> Jungle prompting
// for Index+, truthless empty states, ambiguous Set/Era chips). Behavioural proof lives in
// e2e/market-explorer/*.playwright.spec.mjs; these keep the pure rules from drifting.
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { assetContextLabel, buildPreparedSeries } from "./marketExplorerPrepared.mjs";
import { isEnumerableSeries } from "./marketExplorerConstituents.mjs";
import { resolveCompositionCapability } from "./marketExplorerComposition.mjs";

const read = (p) => fs.readFileSync(new URL(p, import.meta.url), "utf8").replace(/\r\n/g, "\n");

test("Set and Era chips carry the PUBLISHED asset, other markets stay quiet", () => {
  assert.equal(assetContextLabel({ label: "Fossil", market_type: "set", asset: "cards" }), "Fossil — Cards");
  assert.equal(assetContextLabel({ label: "Fossil", market_type: "set", asset: "sealed" }), "Fossil — Sealed");
  assert.equal(assetContextLabel({ label: "Base Set 2", scope_kind: "set", asset: "cards" }), "Base Set 2 — Cards");
  assert.equal(assetContextLabel({ label: "Base/WOTC", market_type: "era", asset: "sealed" }), "Base/WOTC — Sealed");
  assert.equal(assetContextLabel({ label: "Total Sealed", market_type: "parent", asset: "sealed" }), "Total Sealed");
  assert.equal(assetContextLabel({ label: "Sealed Base Set", market_type: "set", asset: "sealed" }), "Sealed Base Set");
  const [series] = buildPreparedSeries([{ market_key: "sealed-set:x", market_type: "set", label: "Fossil", asset: "sealed", comparison_as_of: "2026-09-22" }], []);
  assert.equal(series.shortLabel, "Fossil — Sealed");
  assert.equal(series.label, "Fossil"); // identity label is untouched
});

test("V1 parent without a roster explains itself; V2 Raw with composition is inspectable", () => {
  const v1Raw = { key: "raw", label: "Raw Card Market", isParent: true };
  assert.equal(isEnumerableSeries(v1Raw), false);
  assert.match(resolveCompositionCapability(v1Raw).reason, /Raw Card Market composition is not available in the current published generation\./);
  const v2Raw = { key: "raw", label: "Raw Card Market", isParent: true, compositionKind: "index_and_composition", availability: "available" };
  assert.equal(isEnumerableSeries(v2Raw), true);
  assert.equal(resolveCompositionCapability({ ...v2Raw, availability: "unavailable", unavailableReason: "Frozen roster pending." }).reason, "Frozen roster pending.");
});

test("component contract: single-market selection replaces, comparison is Index+ only, rows never show a per-row upsell", () => {
  const client = read("../../components/explore/MarketExplorerClient.jsx");
  assert.match(client, /preparedLoader\.replace\(seriesId\)/);
  assert.match(client, /if \(canComparePreparedMarkets\) \{[\s\S]*return comparePrepared\(seriesId\);/);
  const browse = read("../../components/explore/MarketExplorerBrowse.jsx");
  assert.doesNotMatch(browse, /Compare with Index\+/);
  // The secondary control exists only to Remove an active market / Retry a failed one.
  assert.match(browse, /\{canCompare && \(active \|\| failed\) \? <button type="button" data-compare-market=/);
  assert.match(browse, /data-compare-upsell/);
  const loader = read("./marketExplorerPreparedLoader.mjs");
  assert.match(loader, /const contextKeys = replaceOthers\s*\n\s*\? \[\]/);
  const backend = read("../../../backend/api/main.py");
  assert.match(backend, /comparing = len\(set\(payload\.marketKeys\) \| set\(payload\.contextMarketKeys\)\) > 1/); // real comparisons stay entitled
});

test("constituent panel distinguishes locked / failed / not-inspectable", () => {
  const panel = read("../../components/explore/MarketExplorerConstituents.jsx");
  assert.match(panel, /data-market-constituents-state="locked"/);
  assert.match(panel, /data-market-constituents-state="failed"/);
  assert.match(panel, /data-market-constituents-not-inspectable/);
});
