import "../../test-support/renderComponentRegister.mjs";
import test from "node:test";
import assert from "node:assert/strict";
import React from "react";
import TestRenderer, { act } from "react-test-renderer";
import MarketExplorerContextualSearch from "./MarketExplorerContextualSearch.jsx";
import MarketExplorerSealedTypes, { MarketExplorerSealedQuickMarkets } from "./MarketExplorerSealedTypes.jsx";
import MarketExplorerRarityMarkets from "./MarketExplorerRarityMarkets.jsx";
import MarketExplorerBrowse from "./MarketExplorerBrowse.jsx";
import { createCatalogSearchController, resolveSearchResultAction } from "../../lib/explore/marketExplorerCatalogSearch.mjs";
import ConstituentThumbnail from "./MarketExplorerConstituentPreview.jsx";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
globalThis.requestAnimationFrame = (callback) => { callback(); return 1; };
const noop = () => {};
const text = (renderer) => JSON.stringify(renderer.toJSON());
const tick = () => new Promise((resolve) => setTimeout(resolve, 15));

function searchHarness(results) {
  const fetches = [];
  const factory = () => createCatalogSearchController({
    debounceMs: 0,
    fetchResults: async (args) => { fetches.push(args); return typeof results === "function" ? results(args) : results; },
  });
  return { fetches, factory };
}

async function mountSearch(props, results) {
  const h = searchHarness(results);
  let renderer;
  await act(async () => {
    renderer = TestRenderer.create(<MarketExplorerContextualSearch controllerFactory={h.factory} {...props} />, { createNodeMock: () => ({ focus: noop }) });
  });
  return { renderer, ...h };
}
const input = (r) => r.root.findByProps({ "data-market-explorer-search-input": true });
const type = async (r, value) => { await act(async () => input(r).props.onChange({ target: { value } })); await act(async () => { await tick(); await tick(); }); };
const key = async (r, k) => act(async () => input(r).props.onKeyDown({ key: k, preventDefault: noop }));

const SET = { asset: "cards", result_kind: "set", label: "Fossil", subtitle: "Set market", market_key: "set:fossil", availability: "AVAILABLE", metadata: {} };
const PRODUCT = { asset: "sealed", result_kind: "instrument", label: "Evolving Skies Booster Box", subtitle: "Evolving Skies · Booster Box", instrument_id: "sp-9", image_url: null, availability: "AVAILABLE", metadata: { sealedProductId: "sp-9", productFamily: "booster_box" } };

test("search: placeholders, combobox/listbox semantics, keyboard navigation and market activation via the shared loader callback", async () => {
  const activated = [];
  const { renderer, fetches } = await mountSearch({ asset: "cards", onActivateMarket: (k) => activated.push(k) }, [SET, { ...SET, label: "Gengar Set", market_key: "set:gengar" }]);
  const el = input(renderer);
  assert.equal(el.props.placeholder, "Search cards or card markets…");
  assert.equal(el.props.role, "combobox");
  assert.equal(el.props["aria-autocomplete"], "list");
  await type(renderer, "fos");
  assert.equal(fetches[0].asset, "cards");
  assert.equal(fetches[0].q, "fos");
  assert.ok(renderer.root.findByProps({ role: "listbox" }));
  assert.equal(renderer.root.findAllByProps({ role: "option" }).length, 2);
  await key(renderer, "ArrowDown");
  await key(renderer, "ArrowDown");
  assert.match(input(renderer).props["aria-activedescendant"], /-1$/);
  await key(renderer, "ArrowUp");
  await key(renderer, "Enter");
  assert.deepEqual(activated, ["set:fossil"]);
  renderer.unmount();
});

test("search result type is rendered; a market result shows active/loading/failed through the same lifecycle keys", async () => {
  const { renderer } = await mountSearch({ asset: "cards", activeKeys: ["set:fossil"], pendingKeys: ["set:gengar"], failedKeys: ["set:x"], onActivateMarket: noop },
    [SET, { ...SET, market_key: "set:gengar", label: "G" }, { ...SET, market_key: "set:x", label: "X" }]);
  await type(renderer, "set");
  const labels = renderer.root.findAllByProps({ "data-search-primary": "activate" }).map((n) => n.children.join(""));
  assert.deepEqual(labels, ["Remove", "Adding…", "Retry"]);
  assert.match(text(renderer), /"Set"/);
  renderer.unmount();
});

test("instrument result: primary Open detail (new tab), secondary Add to Exact Basket; never an aggregate market", async () => {
  const basket = []; const activated = [];
  const { renderer } = await mountSearch({ asset: "sealed", onActivateMarket: (k) => activated.push(k), onAddToBasket: (i) => basket.push(i) }, [PRODUCT]);
  assert.equal(input(renderer).props.placeholder, "Search sealed products or sealed markets…");
  await type(renderer, "evolving skies booster box");
  const detail = renderer.root.findByProps({ "data-search-primary": "detail" });
  assert.equal(detail.props.target, "_blank");
  assert.match(detail.props.rel, /noopener/);
  assert.match(detail.props.href, /sp-9/);
  assert.equal(renderer.root.findAllByProps({ "data-search-primary": "activate" }).length, 0);
  await act(async () => renderer.root.findByProps({ "data-search-secondary": "basket" }).props.onClick());
  assert.equal(basket.length, 1);
  assert.equal(basket[0].instrumentId, "sp-9");
  assert.deepEqual(activated, []);
  // null image renders an intentional placeholder, not a broken image
  assert.equal(renderer.root.findAllByProps({ "data-search-result-placeholder": true }).length, 1);
  renderer.unmount();
});

test("search: graded fail-closed result is explained and offers no action; clear resets; failure is retryable", async () => {
  const graded = { asset: "graded", result_kind: "graded_instrument", label: "Graded Markets", subtitle: "Graded production coverage is not yet broad enough.", availability: "INSUFFICIENT_AUTHORITY", metadata: {} };
  const { renderer } = await mountSearch({ asset: "graded" }, [graded]);
  assert.equal(input(renderer).props.placeholder, "Search graded cards…");
  await type(renderer, "psa 10");
  assert.equal(renderer.root.findAllByProps({ "data-search-primary": "activate" }).length, 0);
  assert.equal(renderer.root.findAllByProps({ "data-search-primary": "detail" }).length, 0);
  assert.match(text(renderer), /not yet broad enough/);
  await act(async () => renderer.root.findByProps({ "data-market-explorer-search-clear": true }).props.onClick());
  assert.equal(input(renderer).props.value, "");
  renderer.unmount();
  let fail = true;
  const again = await mountSearch({ asset: "cards" }, () => { if (fail) throw Object.assign(new Error("x"), { code: "CATALOG_SEARCH_FAILED" }); return [SET]; });
  await type(again.renderer, "fossil");
  assert.ok(again.renderer.root.findByProps({ "data-market-explorer-search-state": "error" }));
  fail = false;
  await act(async () => again.renderer.root.findByProps({ "data-market-explorer-search-retry": true }).props.onClick());
  await act(async () => { await tick(); await tick(); });
  assert.equal(again.renderer.root.findAllByProps({ role: "option" }).length, 1);
  again.renderer.unmount();
});

test("search: switching asset re-scopes the same field (no second dropdown) and re-queries with the new asset", async () => {
  const h = searchHarness(() => []);
  let renderer;
  await act(async () => { renderer = TestRenderer.create(<MarketExplorerContextualSearch asset="cards" controllerFactory={h.factory} />, { createNodeMock: () => ({ focus: noop }) }); });
  await type(renderer, "evolving");
  await act(async () => { renderer.update(<MarketExplorerContextualSearch asset="sealed" controllerFactory={h.factory} />); });
  await act(async () => { await tick(); await tick(); });
  assert.equal(h.fetches.at(-1).asset, "sealed");
  assert.equal(input(renderer).props.placeholder, "Search sealed products or sealed markets…");
  assert.equal(renderer.root.findAllByType("select").length, 0);
  renderer.unmount();
});

// ------------------------------------------------------------------ rarity
const RARITY_STATES = [
  ["Rare Holo GX", { eligibilityState: "CUSTOM_BUILD_AVAILABLE" }, "build"],
  ["Rare Holo EX", { eligibilityState: "PREPARED", preparedMarketAvailable: true, preparedMarketKey: "rarity:rareHoloEx" }, "prepared"],
  ["Rare Holo V", { eligibilityState: "CUSTOM_BUILD_AVAILABLE", preparedMarketKey: "rarity:rareHoloV" }, "prepared"],
  ["Rare Holo VMAX", { eligibilityState: "INSUFFICIENT_COHORT", reason: "Only 4 priced cards." }, "none"],
  ["Rare Holo VSTAR", { eligibilityState: "INSUFFICIENT_HISTORY" }, "none"],
  ["Rare Ultra", { eligibilityState: "UNAVAILABLE" }, "none"],
];

test("rarity matrix in the UI: prepared selects, build adds a query, blocked options are disabled AND explain why (no click-to-nothing)", async () => {
  const selected = []; const queries = [];
  const assetOptions = { rarities: RARITY_STATES.map(([label, over]) => ({ key: label.replace(/\s+/g, ""), label, ...over })) };
  let renderer;
  await act(async () => { renderer = TestRenderer.create(<MarketExplorerRarityMarkets assetOptions={assetOptions} directory={[]} canUse onSelect={(k) => selected.push(k)} onAddQuery={async (s) => { queries.push(s); return "added"; }} onRemoveQuery={noop} />); });
  await act(async () => renderer.root.findByProps({ "data-rarity-market-trigger": true }).props.onClick());
  for (const [label, , action] of RARITY_STATES) {
    const row = renderer.root.findByProps({ "data-rarity-market": label.replace(/\s+/g, "") });
    assert.equal(row.props["data-rarity-market-action"], action, label);
    if (action === "none") {
      assert.equal(row.props.disabled, true, `${label} disabled`);
      assert.ok(row.findAllByProps({ "data-rarity-market-reason": true }).length >= 1, `${label} explains itself`);
    } else assert.notEqual(row.props.disabled, true);
  }
  await act(async () => renderer.root.findByProps({ "data-rarity-market": "RareHoloEX" }).props.onClick());
  assert.deepEqual(selected, ["rarity:rareHoloEx"]);
  await act(async () => renderer.root.findByProps({ "data-rarity-market": "RareHoloGX" }).props.onClick());
  assert.deepEqual(queries[0].segmentIds, ["RareHoloGX"], "Rare Holo GX flows through the generic build pathway");
  renderer.unmount();
});

test("rarity LEGACY MODE (no V2 options): existing behavior untouched", async () => {
  let renderer;
  await act(async () => { renderer = TestRenderer.create(<MarketExplorerRarityMarkets rarityOptions={[{ key: "a", label: "A" }]} directory={[]} canUse onSelect={noop} onAddQuery={async () => "added"} onRemoveQuery={noop} />); });
  await act(async () => renderer.root.findByProps({ "data-rarity-market-trigger": true }).props.onClick());
  assert.equal(renderer.root.findByProps({ "data-rarity-market": "a" }).props["data-rarity-market-action"], undefined);
});

// ------------------------------------------------------------------ sealed
const FAMILIES = ["booster_box", "half_booster_box", "enhanced_booster_box", "elite_trainer_box", "pokemon_center_elite_trainer_box", "booster_bundle", "loose_booster_pack", "sleeved_booster_pack", "build_and_battle_box", "build_and_battle_stadium", "three_pack_blister", "single_pack_blister", "collection_product", "case", "display", "multi_product_bundle", "fun_pack", "other"];

test("Sealed Types renders whatever the DB publishes with truthful actions; Cases are bulk containers, not 'invalid'", async () => {
  const types = FAMILIES.map((family, i) => ({
    key: family, label: family.replace(/_/g, " "),
    eligibilityState: i % 3 === 0 ? "PREPARED" : i % 3 === 1 ? "SEARCHABLE_BUILDABLE" : "INSUFFICIENT_HISTORY",
    preparedMarketAvailable: i % 3 === 0, preparedMarketKey: i % 3 === 0 ? `sealed-type:${family}` : null,
    bulkContainer: family === "case" || family === "display", parentMembership: family !== "case" && family !== "display",
  }));
  const selected = []; const built = [];
  let renderer;
  await act(async () => { renderer = TestRenderer.create(<MarketExplorerSealedTypes options={{ types }} canBuild onSelect={(k) => selected.push(k)} onAddQuery={async (s) => { built.push(s); return "added"; }} onRemoveQuery={noop} />); });
  assert.equal(renderer.root.findAll((n) => n.props?.["data-sealed-type"]).length, FAMILIES.length);
  for (const type of types) {
    const li = renderer.root.findByProps({ "data-sealed-type": type.key });
    const expected = type.eligibilityState === "PREPARED" ? "prepared" : type.eligibilityState === "SEARCHABLE_BUILDABLE" ? "build" : "none";
    assert.equal(li.props["data-sealed-type-action"], expected, type.key);
    if (expected === "none") assert.ok(li.findAllByProps({ "data-sealed-type-reason": true }).length === 1, `${type.key} explains itself`);
  }
  const caseRow = renderer.root.findByProps({ "data-sealed-type": "case" });
  const note = caseRow.findByProps({ "data-sealed-type-note": true });
  assert.match(note.children.join(""), /Bulk container — tracked separately from Total Sealed/);
  assert.equal(renderer.root.findByProps({ "data-sealed-type": "booster_box" }).findAllByProps({ "data-sealed-type-note": true }).length, 0);
  await act(async () => renderer.root.findByProps({ "data-sealed-type-action-button": "booster_box" }).props.onClick());
  assert.deepEqual(selected, ["sealed-type:booster_box"]);
  await act(async () => renderer.root.findByProps({ "data-sealed-type-action-button": "half_booster_box" }).props.onClick());
  assert.equal(built[0].asset, "sealed");
  assert.deepEqual(built[0].segmentIds, ["half_booster_box"]);
  renderer.unmount();
});

test("Sealed Types is not the rarity component relabelled and hides card rarity UI entirely", async () => {
  let renderer;
  await act(async () => { renderer = TestRenderer.create(<MarketExplorerSealedTypes options={{ types: [] }} />); });
  assert.equal(renderer.root.findAllByProps({ "data-market-explorer-rarity-markets": true }).length, 0);
  assert.ok(renderer.root.findByProps({ "data-market-explorer-sealed-types": true }));
});

test("Sealed Quick Markets: zero approved -> honest empty state, proposed entries never selectable", async () => {
  let renderer;
  await act(async () => { renderer = TestRenderer.create(<MarketExplorerSealedQuickMarkets options={{ quickMarkets: [{ key: "q", label: "Budget", status: "PROPOSED" }] }} onSelect={noop} />); });
  assert.match(text(renderer), /No approved Sealed Quick Markets yet\./);
  assert.equal(renderer.root.findAllByProps({ "data-sealed-quick-market": "q" }).length, 0);
});

// ------------------------------------------------------------------ browse
const cardSet = { market_key: "set:fossil", market_type: "set", asset: "cards", label: "Fossil", parent_era_id: "e1" };
const cardEra = { market_key: "era:e1", market_type: "era", asset: "cards", era_id: "e1", label: "WotC" };
const sealedSet = { market_key: "sealed-set:s1", market_type: "set", asset: "sealed", label: "Fossil Sealed", parent_era_id: "e1", surface_version: "v2" };
const sealedEra = { market_key: "sealed-era:e1", market_type: "era", asset: "sealed", era_id: "e1", label: "WotC Sealed", surface_version: "v2" };
const sealedType = { market_key: "sealed-type:booster_box", market_type: "prepared_format", asset: "sealed", label: "Booster Box", surface_version: "v2" };

const mountBrowse = async (directory, extra = {}) => {
  let renderer;
  await act(async () => { renderer = TestRenderer.create(<MarketExplorerBrowse directory={directory} activeKeys={["set:fossil"]} canCompare onSelect={noop} onCompare={noop} onBuild={noop} {...extra} />, { createNodeMock: () => ({ focus: noop }) }); });
  return renderer;
};
const rowKeys = (r) => r.root.findAll((n) => n.type === "button" && n.props?.["data-prepared-market"]).map((n) => n.props["data-prepared-market"]);
const cats = (r) => r.root.findAll((n) => n.type === "button" && n.props?.["data-market-directory-category"]).map((n) => n.props["data-market-directory-category"]);

test("V2 Sealed IA: Sets, Eras, Quick, Sealed Types in one layer; NO redundant flat Sealed Markets; no family presented through two categories", async () => {
  const changes = []; const calls = [];
  const renderer = await mountBrowse([cardSet, cardEra, sealedSet, sealedEra, sealedType], { onAssetLayerChange: (v) => changes.push(v), onSelect: (k) => calls.push(k), sealedTypesPanel: <div data-panel-marker="types">TYPES</div> });
  assert.deepEqual(cats(renderer), ["sets", "eras", "quick"]);
  await act(async () => renderer.root.findByProps({ "data-market-directory-asset": "sealed" }).props.onClick());
  assert.deepEqual(cats(renderer), ["sets", "eras", "quick", "types"]);
  assert.ok(renderer.root.findByProps({ "data-market-explorer-build-trigger": true }));
  const seen = [];
  for (const id of ["sets", "eras", "quick"]) {
    await act(async () => renderer.root.findByProps({ "data-market-directory-category": id }).props.onClick());
    seen.push(...rowKeys(renderer));
    await act(async () => renderer.root.findByProps({ "data-market-directory-category": id }).props.onClick());
  }
  assert.deepEqual(seen, ["sealed-set:s1", "sealed-era:e1"]);
  // the type market is reachable ONLY through Sealed Types
  assert.equal(seen.includes("sealed-type:booster_box"), false);
  await act(async () => renderer.root.findByProps({ "data-market-directory-category": "types" }).props.onClick());
  assert.ok(renderer.root.findByProps({ "data-panel-marker": "types" }));
  assert.deepEqual(rowKeys(renderer), []);
  assert.deepEqual(changes, ["sealed"]);
  assert.deepEqual(calls, [], "browse-asset switching never touches the chart selection");
  renderer.unmount();
});

test("V2 Sealed Quick with zero approved entries is a deliberate empty state, not a broken control", async () => {
  const renderer = await mountBrowse([sealedSet, sealedType], { assetLayer: "sealed" });
  await act(async () => renderer.root.findByProps({ "data-market-directory-category": "quick" }).props.onClick());
  assert.ok(renderer.root.findByProps({ "data-market-directory-popover": true }));
  assert.match(text(renderer), /No approved Sealed Quick Markets yet\./);
  assert.ok(renderer.root.findByProps({ "data-market-browser-search": true }), "same popover + search chrome as Cards");
  renderer.unmount();
});

test("V1 fallback keeps the SAME Sealed IA as V2 (superseded flat Sealed Markets list): formats live inside Sealed Types", async () => {
  const v1Sealed = { market_key: "format:etb", market_type: "prepared_format", asset: "sealed", label: "Elite Trainer Boxes" };
  const renderer = await mountBrowse([cardSet, v1Sealed], { assetLayer: "sealed" });
  assert.deepEqual(cats(renderer), ["sets", "eras", "quick", "types"]);
  await act(async () => renderer.root.findByProps({ "data-market-directory-category": "types" }).props.onClick());
  const formats = renderer.root.findAll((node) => node.type === "button" && node.props?.["data-prepared-market"]).map((node) => node.props["data-prepared-market"]);
  assert.deepEqual(formats, ["format:etb"]);
  renderer.unmount();
});

const CARD = { asset: "cards", result_kind: "instrument", label: "Gengar", subtitle: "Fossil · 5 Rare Holo", instrument_id: "var-1", set_id: "set-1", image_url: "https://img/x.png", availability: "AVAILABLE", metadata: { cardVariantId: "var-1", cardNumber: "5", rarity: "Rare Holo" } };

test("card search result without canonicalCardId renders no malformed detail link; basket stays; sealed detail stays enabled", async () => {
  const { renderer } = await mountSearch({ asset: "cards", onAddToBasket: noop }, [CARD]);
  await type(renderer, "gengar");
  assert.equal(renderer.root.findAll((n) => n.type === "a").length, 0, "no anchor of any kind");
  assert.equal(renderer.root.findAllByProps({ "data-search-primary": "detail" }).length, 0);
  assert.match(text(renderer), /not available for this card yet/);
  assert.equal(renderer.root.findAllByProps({ "data-search-secondary": "basket" }).length, 1);
  renderer.unmount();
  const sealed = await mountSearch({ asset: "sealed" }, [PRODUCT]);
  await type(sealed.renderer, "evolving");
  assert.equal(sealed.renderer.root.findAllByProps({ "data-search-primary": "detail" }).length, 1);
  sealed.renderer.unmount();
  // once the authority publishes canonicalCardId the SAME resolver produces a well-formed link
  const linked = resolveSearchResultAction({ ...CARD, metadata: { ...CARD.metadata, canonicalCardId: "can-1", setName: "Fossil" } });
  assert.match(linked.primary.href || "", /\/Cards\/can-1/);
});

// ------------------------------------------------------------------ named set image fixtures
import { resolveConstituentImage } from "../../lib/explore/marketExplorerConstituentPresentation.mjs";
import * as v2Doc from "node:fs";

const IMAGED = [
  ["Fossil", "set:fossil"], ["HeartGold & SoulSilver", "set:hgss"], ["Base Set 2", "set:base2"],
  ["Rare Ultra", "rarity:rareUltra"], ["Rare Secret", "rarity:rareSecret"],
];

test("named set image fixtures: V2 payload JSON -> resolver -> RENDERED constituent thumbnail; missing image -> placeholder; no Set-name special casing", () => {
  const code = v2Doc.readFileSync(new URL("../../lib/explore/marketExplorerConstituentPresentation.mjs", import.meta.url), "utf8")
    .replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");
  assert.doesNotMatch(code, /Fossil|HeartGold|Base Set 2|Rare Ultra|Rare Secret/, "resolver is row-driven, not name-driven");
  for (const [label, key] of IMAGED) {
    // exactly what the API returns for a V2 page row (JSON round trip)
    const wire = JSON.parse(JSON.stringify({ rank: 1, cardName: `${label} card`, canonicalCardId: "c1", cardVariantId: "v1", setName: label, marketPrice: 5,
      imageSmallUrl: `https://img/${key}/small.png`, imageUrl: `https://img/${key}/std.png`, imageLargeUrl: `https://img/${key}/large.png` }));
    let renderer;
    act(() => { renderer = TestRenderer.create(<ConstituentThumbnail row={wire} asset="cards" />); });
    const imgs = renderer.root.findAll((n) => n.type === "img");
    assert.equal(imgs.length, 1, label);
    assert.equal(imgs[0].props.src, `https://img/${key}/small.png`, `${label} small image is the row thumbnail`);
    assert.equal(resolveConstituentImage(wire).previewUrl, `https://img/${key}/large.png`);
    renderer.unmount();
    let empty;
    act(() => { empty = TestRenderer.create(<ConstituentThumbnail row={{ ...wire, imageSmallUrl: null, imageUrl: null, imageLargeUrl: null }} asset="cards" />); });
    assert.equal(empty.root.findAll((n) => n.type === "img").length, 0);
    assert.equal(empty.root.findAllByProps({ "data-market-constituent-image-placeholder": true }).length, 1, `${label} placeholder`);
    empty.unmount();
  }
});

// ------------------------------------------------------------------ client wiring (source contract)
import { readFileSync } from "node:fs";
const client = readFileSync(new URL("./MarketExplorerClient.jsx", import.meta.url), "utf8").replace(/\r\n/g, "\n");

test("Client: activeBrowseAsset is browsing state, never fed to the chart selection; interaction seams preserved", () => {
  assert.match(client, /const \[activeBrowseAsset, setActiveBrowseAsset\] = useState\("cards"\)/);
  // selection / loader / workspace reducers never receive it
  assert.doesNotMatch(client, /useMarketExplorerSelection\([^)]*activeBrowseAsset/);
  assert.doesNotMatch(client, /preparedLoader\.(add|replace|remove|clear)\([^)]*activeBrowseAsset/);
  assert.doesNotMatch(client, /dispatchView\([^)]*activeBrowseAsset/);
  // one identity per visible market
  assert.match(client, /unifySeriesByKey\(\[/);
  // Rarity only for Cards; Sealed Types/Quick only for Sealed; Graded gets neither
  assert.match(client, /activeBrowseAsset === "cards" \? <MarketExplorerRarityMarkets/);
  // Sealed Types is a Browse category (single navigation layer), not a second control.
  assert.match(client, /sealedTypesPanel=\{\(\{ v2Mode, formatMarkets \}\) => <MarketExplorerSealedTypes/);
  assert.equal((client.match(/<MarketExplorerSealedTypes/g) || []).length, 1);
  assert.doesNotMatch(client, /<MarketExplorerSealedQuickMarkets/);
  // interaction foundation (e3d85bc1) still present
  for (const seam of ["createConstituentPageCache", "constituentPageCache.evictMarket(key)", "constituentPageCache.clear()", "onClearAll={clearGraph}", "onFocus={focusSeries}", "pageCache={constituentPageCache}"]) assert.ok(client.includes(seam), seam);
  // Exact Basket seeding goes through the same Premium-gated basket, not a new path
  assert.match(client, /seedItem=\{basketSeed\}/);
});
