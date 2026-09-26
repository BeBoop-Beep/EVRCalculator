// .jsx on purpose: the catalog-search module imports a CJS-ambiguous route helper via the detail resolver.
import test from "node:test";
import assert from "node:assert/strict";
import {
  ASSET_OPTION_ACTION,
  NO_APPROVED_SEALED_QUICK_COPY,
  approvedSealedQuickMarkets,
  normalizeRarityOptions,
  normalizeSealedTypeOptions,
  resolveAssetOptionAction,
} from "./marketExplorerAssetOptions.mjs";
import { resolveCompositionCapability, unifySeriesByKey } from "./marketExplorerComposition.mjs";
import { isEnumerableSeries, resolveActiveDetailSeriesId, resolveSeriesConstituents } from "./marketExplorerConstituents.mjs";
import {
  SEARCH_PLACEHOLDER,
  createCatalogSearchController,
  resolveSearchResultAction,
} from "./marketExplorerCatalogSearch.mjs";
import { buildPreparedSeries } from "./marketExplorerPrepared.mjs";

const RARITIES = ["Rare Holo GX", "Rare Holo EX", "Rare Holo V", "Rare Holo VMAX", "Rare Holo VSTAR", "Rare Ultra", "Rare Secret", "Ultra Rare", "Special Illustration Rare"];
const rar = (label, over) => ({ key: label.toLowerCase().replace(/[^a-z]+/g, ""), label, preparedMarketAvailable: false, preparedMarketKey: null, eligibilityState: "UNAVAILABLE", reason: null, ...over });

test("rarity matrix: every state resolves to exactly one truthful action, for every rarity, with no rarity special-casing", () => {
  const cases = [
    [{ eligibilityState: "PREPARED", preparedMarketAvailable: true, preparedMarketKey: "rarity:x" }, "prepared", "rarity:x"],
    [{ eligibilityState: "CUSTOM_BUILD_AVAILABLE", preparedMarketKey: "rarity:candidate" }, "prepared", "rarity:candidate"],
    [{ eligibilityState: "CUSTOM_BUILD_AVAILABLE" }, "build", null],
    [{ eligibilityState: "INSUFFICIENT_COHORT", reason: "Only 3 priced cards." }, "none", null],
    [{ eligibilityState: "INSUFFICIENT_HISTORY" }, "none", null],
    [{ eligibilityState: "UNAVAILABLE" }, "none", null],
    [{ eligibilityState: "SOMETHING_NEW" }, "none", null],
  ];
  for (const label of RARITIES) {
    for (const [over, action, key] of cases) {
      const [option] = normalizeRarityOptions({ rarities: [rar(label, over)] });
      assert.equal(option.action, action, `${label} ${over.eligibilityState}`);
      assert.equal(option.marketKey, key);
      if (action === "none") assert.ok(option.reason && option.reason.length > 5, "blocked options always explain themselves");
    }
  }
});

test("Rare Holo GX works through the generic contract (custom build available, then a candidate prepared key)", () => {
  const gx = { key: "rareHoloGx", label: "Rare Holo GX", eligibilityState: "CUSTOM_BUILD_AVAILABLE", currentPricedCardCount: 159, representedSetCount: 15, imageCount: 159 };
  assert.equal(normalizeRarityOptions({ rarities: [gx] })[0].action, "build");
  const withCandidate = { ...gx, preparedMarketKey: "rarity:rareHoloGx", preparedMarketAvailable: true };
  assert.deepEqual(resolveAssetOptionAction(withCandidate), { action: "prepared", marketKey: "rarity:rareHoloGx", reason: null, state: "CUSTOM_BUILD_AVAILABLE" });
});

test("a maintained prepared identity is never downgraded by an empty current audit", () => {
  const result = resolveAssetOptionAction({ key: "doubleRare", eligibilityState: "UNAVAILABLE", preparedMarketAvailable: true, preparedMarketKey: "rarity:doubleRare" });
  assert.equal(result.action, ASSET_OPTION_ACTION.prepared);
});

const SEALED_TYPES = ["booster_box", "half_booster_box", "enhanced_booster_box", "elite_trainer_box", "pokemon_center_elite_trainer_box", "booster_bundle", "loose_booster_pack", "sleeved_booster_pack", "build_and_battle_box", "build_and_battle_stadium", "three_pack_blister", "single_pack_blister", "collection_product", "case", "display", "multi_product_bundle", "fun_pack", "other"];

test("sealed matrix: every published family gets a truthful action across all states; the list is read, not hard-coded", () => {
  const states = [
    ["PREPARED", true, "sealed-type:K", "prepared"],
    ["PREPARED_CANDIDATE", false, "sealed-type:K", "prepared"],
    ["PREPARED_CANDIDATE", false, null, "build"],
    ["SEARCHABLE_BUILDABLE", false, null, "build"],
    ["INSUFFICIENT_HISTORY", false, null, "none"],
    ["UNAVAILABLE", false, null, "none"],
  ];
  for (const family of SEALED_TYPES) {
    for (const [state, available, key, action] of states) {
      const payload = { types: [{ key: family, label: family, eligibilityState: state, preparedMarketAvailable: available, preparedMarketKey: key ? key.replace("K", family) : null, bulkContainer: family === "case" || family === "display", parentMembership: family !== "case" }] };
      const [type] = normalizeSealedTypeOptions(payload);
      assert.equal(type.action, action, `${family} ${state}`);
      if (action === "none") assert.ok(type.reason);
    }
  }
  assert.equal(normalizeSealedTypeOptions({ types: [] }).length, 0, "nothing invented when the DB publishes nothing");
});

test("Cases are bulk containers: a note explains they are separate from Total Sealed, never marked invalid", () => {
  const [caseType] = normalizeSealedTypeOptions({ types: [{ key: "case", label: "Case", eligibilityState: "PREPARED_CANDIDATE", preparedMarketKey: "sealed-type:case", bulkContainer: true, parentMembership: false }] });
  assert.equal(caseType.action, "prepared");
  assert.match(caseType.note, /Bulk container — tracked separately from Total Sealed/);
  const [box] = normalizeSealedTypeOptions({ types: [{ key: "booster_box", label: "Booster Box", eligibilityState: "PREPARED", preparedMarketKey: "sealed-type:booster_box", preparedMarketAvailable: true, bulkContainer: false, parentMembership: true }] });
  assert.equal(box.note, null);
});

test("Sealed Quick Markets: proposed definitions are never selectable; zero approved shows the honest empty copy", () => {
  const payload = { quickMarkets: [{ key: "q1", label: "Budget", status: "PROPOSED" }] };
  assert.equal(approvedSealedQuickMarkets(payload).length, 0);
  assert.equal(NO_APPROVED_SEALED_QUICK_COPY, "No approved Sealed Quick Markets yet.");
  assert.equal(approvedSealedQuickMarkets({ quickMarkets: [{ key: "q2", label: "X", status: "APPROVED" }] }).length, 1);
});

test("composition capability follows published metadata, not the word 'parent'", () => {
  const v2Raw = { key: "raw", isParent: true, compositionKind: "index_and_composition", availability: "available" };
  assert.equal(resolveCompositionCapability(v2Raw).inspectable, true);
  assert.equal(resolveCompositionCapability(v2Raw).indexAndComposition, true);
  assert.equal(isEnumerableSeries(v2Raw), true);
  assert.equal(resolveCompositionCapability({ ...v2Raw, availability: "unavailable", unavailableReason: "Raw roster not READY" }).inspectable, false);
  assert.equal(resolveCompositionCapability({ ...v2Raw, compositionKind: "index" }).inspectable, false);
  // V1 Raw: no composition authority -> stays non-enumerable
  const v1Raw = { key: "raw", isParent: true };
  assert.equal(isEnumerableSeries(v1Raw), false);
  assert.equal(resolveSeriesConstituents(v1Raw).availability, "notApplicable");
  // V2 Total Sealed with composition
  assert.equal(isEnumerableSeries({ key: "sealedMarket", isParent: true, compositionKind: "composition", availability: "available" }), true);
  // detail target follows the same rule
  assert.equal(resolveActiveDetailSeriesId([v1Raw, v2Raw], null), "raw");
  assert.equal(resolveActiveDetailSeriesId([v1Raw], null), null);
});

test("ONE identity per visible market: V2 parent supersedes the legacy overview entry", () => {
  const legacy = { key: "raw", isParent: true, label: "Raw (overview)" };
  const v2 = { key: "raw", isParent: true, compositionKind: "index_and_composition", availability: "available", label: "Raw" };
  const other = { key: "set:a" };
  const out = unifySeriesByKey([legacy, other, v2]);
  assert.deepEqual(out.map((s) => s.key), ["raw", "set:a"]);
  assert.equal(out[0].compositionKind, "index_and_composition");
  assert.equal(unifySeriesByKey([v2, legacy])[0], v2);
});

test("V2 directory row maps into the prepared series (identity = marketKey; alias keeps requested key)", () => {
  const row = { market_key: "sealed-type:booster_box", requested_market_key: "format:booster-box", label: "Booster Boxes", asset: "sealed", market_type: "prepared_format", generation_id: "g1", source_kind: "surface_v2", set_id: null, era_id: null, comparison_as_of: "2026-09-24", history_available: true, comparison_value: 10, comparison_index_value: 105, constituent_count: 12, composition_kind: "composition", availability: "available", available: true, scope_kind: "type", surface_version: "v2", window_movements: {}, metadata: {} };
  const history = [{ market_key: "sealed-type:booster_box", requested_market_key: "format:booster-box", market_date: "2026-09-24", index_value: 105, tracked_value: 10 }];
  const [series] = buildPreparedSeries([row], history);
  assert.equal(series.key, "format:booster-box");
  assert.equal(series.canonicalMarketKey, "sealed-type:booster_box");
  assert.equal(series.asset, "sealed");
  assert.equal(series.generationId, "g1");
  assert.equal(series.compositionKind, "composition");
  assert.equal(series.trend.length, 1);
  assert.equal(series.constituentCount, 12);
  const [unavailable] = buildPreparedSeries([{ ...row, requested_market_key: undefined, available: false, availability: "unavailable", unavailable_reason: "no roster" }], []);
  assert.equal(unavailable.available, false);
  assert.equal(unavailable.unavailableReason, "no roster");
});

// ---------------------------------------------------------------- search
test("search actions: market activates via prepared loader; instrument opens detail + Exact Basket; graded is explicit", () => {
  const market = resolveSearchResultAction({ asset: "cards", result_kind: "set", label: "Fossil", market_key: "set:fossil", availability: "AVAILABLE" });
  assert.deepEqual(market, { primary: { kind: "activate", marketKey: "set:fossil" }, secondary: null });
  const sealed = resolveSearchResultAction({ asset: "sealed", result_kind: "instrument", label: "Evolving Skies Booster Box", instrument_id: "sp-1", availability: "AVAILABLE", metadata: { sealedProductId: "sp-1", productFamily: "booster_box" } });
  assert.equal(sealed.primary.kind, "detail");
  assert.match(sealed.primary.href, /sp-1/);
  assert.equal(sealed.secondary.kind, "basket");
  assert.equal(sealed.secondary.item.asset, "sealed");
  assert.equal(sealed.secondary.item.instrumentId, "sp-1");
  const card = resolveSearchResultAction({ asset: "cards", result_kind: "instrument", label: "Gengar", instrument_id: "v1", set_id: "s1", availability: "AVAILABLE", metadata: { cardVariantId: "v1" } });
  // The DB card-instrument row carries no canonicalCardId, so the existing detail resolver cannot link it: explicit, never a fake link.
  assert.equal(card.primary.kind, "none");
  assert.equal(card.secondary.kind, "basket");
  const graded = resolveSearchResultAction({ asset: "graded", result_kind: "graded_instrument", label: "Graded Markets", subtitle: "Graded production coverage is not yet broad enough.", availability: "INSUFFICIENT_AUTHORITY" });
  assert.equal(graded.primary.kind, "unavailable");
  assert.equal(graded.secondary, null);
  assert.equal(resolveSearchResultAction({ asset: "cards", result_kind: "set", market_key: "set:x", availability: "UNAVAILABLE" }).primary.kind, "unavailable");
});

test("placeholders match the contract per asset", () => {
  assert.equal(SEARCH_PLACEHOLDER.cards, "Search cards, Sets, Eras, rarities, and card markets…");
  assert.equal(SEARCH_PLACEHOLDER.sealed, "Search sealed products, Sets, Eras, and sealed markets…");
  assert.equal(SEARCH_PLACEHOLDER.graded, "Search graded cards…");
});

function harness() {
  const timers = []; const calls = [];
  const controller = createCatalogSearchController({
    debounceMs: 250,
    setTimer: (fn, ms) => { timers.push({ fn, ms }); return timers.length - 1; },
    clearTimer: (id) => { if (timers[id]) timers[id].cleared = true; },
    fetchResults: (args) => new Promise((resolve, reject) => {
      const call = { args, resolve, reject };
      args.signal.addEventListener("abort", () => reject(Object.assign(new Error("aborted"), { name: "AbortError" })));
      calls.push(call);
    }),
  });
  const fire = async (index) => { const t = timers[index]; if (t && !t.cleared) { t.fn(); await Promise.resolve(); } };
  return { controller, timers, calls, fire };
}

test("search debounces (200-300ms), ignores <2 chars, and only the last keystroke fetches", async () => {
  const h = harness();
  h.controller.search("g");
  assert.equal(h.controller.getSnapshot().status, "idle");
  assert.equal(h.timers.length, 0);
  h.controller.search("ge"); h.controller.search("gen");
  assert.ok(h.timers.every((t) => t.ms >= 200 && t.ms <= 300));
  await h.fire(0);
  assert.equal(h.calls.length, 0, "a superseded timer never fetches");
  await h.fire(1);
  assert.equal(h.calls.length, 1, "only the last keystroke fetches");
  assert.equal(h.calls[0].args.q, "gen");
  assert.equal(h.controller.getSnapshot().status, "loading");
});

test("stale responses never overwrite a newer query; abort is not an error; asset switch invalidates", async () => {
  const h = harness();
  h.controller.search("gengar", "cards");
  await h.fire(0);
  const first = h.calls[0];
  h.controller.search("fossil", "cards");
  assert.equal(first.args.signal.aborted, true, "previous request aborted");
  await h.fire(1);
  h.calls[1].resolve([{ label: "Fossil" }]);
  await new Promise((r) => setImmediate(r));
  first.resolve([{ label: "Gengar" }]);
  await new Promise((r) => setImmediate(r));
  assert.deepEqual(h.controller.getSnapshot().results.map((r) => r.label), ["Fossil"]);
  assert.equal(h.controller.getSnapshot().status, "ready");
  // asset switch re-runs with the new scope and drops old results
  h.controller.search("fossil", "sealed");
  assert.equal(h.controller.getSnapshot().asset, "sealed");
  assert.equal(h.controller.getSnapshot().status, "loading");
});

test("failure is retryable and clear resets", async () => {
  const h = harness();
  h.controller.search("gengar");
  await h.fire(0);
  h.calls[0].reject(Object.assign(new Error("x"), { code: "CATALOG_SEARCH_FAILED", status: 503 }));
  await new Promise((r) => setImmediate(r));
  assert.equal(h.controller.getSnapshot().status, "error");
  h.controller.retry();
  assert.equal(h.controller.getSnapshot().status, "loading");
  h.controller.clear();
  assert.deepEqual(h.controller.getSnapshot(), { status: "idle", query: "", asset: "cards", results: [], error: null });
});
