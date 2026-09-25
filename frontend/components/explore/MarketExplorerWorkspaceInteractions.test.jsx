// Market Explorer workspace interactions: persistent Constituents & Comparison
// reopen, active-market switching, target preservation, Focus mode, the ONE
// workspace-level Clear All, thumbnail links, and the paging cache.
// Behavior tests: fetch is faked; nothing touches a network or database.
import "../../test-support/renderComponentRegister.mjs";
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import React, { useMemo, useState } from "react";
import TestRenderer, { act } from "react-test-renderer";

import MarketExplorerActiveMarkets from "./MarketExplorerActiveMarkets.jsx";
import MarketExplorerConstituents from "./MarketExplorerConstituents.jsx";
import MarketExplorerClient from "./MarketExplorerClient.jsx";
import MarketPerformanceChart from "./MarketPerformanceChart.jsx";
import ConstituentThumbnail from "./MarketExplorerConstituentPreview.jsx";
import { createConstituentPageCache } from "@/lib/explore/marketExplorerWorkspace.mjs";
import { resolveInitialExplorerState } from "@/lib/explore/marketExplorerState.mjs";
import { resolveMarketOverview } from "@/lib/explore/marketOverviewPresentation.mjs";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
globalThis.requestAnimationFrame = (callback) => { callback(); return 1; };
const read = (name) => fs.readFileSync(new URL(name, import.meta.url), "utf8").replace(/\r\n/g, "\n");

const find = (renderer, prop, value) => renderer.root.findAll(
  (node) => node.props?.[prop] !== undefined && (value === undefined || node.props[prop] === value), { deep: true });
const one = (renderer, prop, value) => find(renderer, prop, value)[0];
const click = (renderer, prop, value) => act(() => { one(renderer, prop, value).props.onClick?.({ stopPropagation() {} }); });
const flush = async (fn) => { await act(async () => { await fn?.(); for (let i = 0; i < 6; i += 1) await Promise.resolve(); }); };
const ids = (renderer, prop) => [...new Set(find(renderer, prop).map((node) => node.props[prop]))];

// ---------------------------------------------------------------------------
// ACTIVE MARKETS chips: focus action, accessibility, mobile availability
// ---------------------------------------------------------------------------
const chipSeries = (key, extra = {}) => ({ key, label: `Market ${key}`, shortLabel: key, color: "#22d3ee", trend: [], changes: {}, ...extra });

function mountChips(props = {}) {
  const calls = { focus: [], remove: [], visibility: [], inspect: [], clear: 0 };
  let renderer;
  act(() => {
    renderer = TestRenderer.create(
      <MarketExplorerActiveMarkets
        series={[chipSeries("A"), chipSeries("B"), chipSeries("C")]}
        activeSeriesId="A"
        onInspect={(key) => calls.inspect.push(key)}
        onRemove={(key) => calls.remove.push(key)}
        onToggleVisibility={(key) => calls.visibility.push(key)}
        onFocus={(key) => calls.focus.push(key)}
        onClearAll={() => { calls.clear += 1; }}
        {...props}
      />);
  });
  return { renderer, calls };
}

test("chip focus action: labelled, separate from visibility/remove, and touches nothing else", () => {
  const { renderer, calls } = mountChips();
  const focus = one(renderer, "data-market-explorer-active-focus", "B");
  assert.equal(focus.props["aria-label"], "Focus on Market B");
  const visibility = one(renderer, "data-market-explorer-active-visibility", "B");
  const remove = one(renderer, "data-market-explorer-active-remove", "B");
  assert.notEqual(focus.props["aria-label"], visibility.props["aria-label"]);
  assert.notEqual(focus.props["aria-label"], remove.props["aria-label"]);
  assert.match(remove.props["aria-label"], /Remove Market B/);
  assert.match(visibility.props["aria-label"], /Hide Market B/);
  act(() => focus.props.onClick());
  assert.deepEqual(calls, { focus: ["B"], remove: [], visibility: [], inspect: [], clear: 0 });
});

test("chip focus: the focused chip is marked, pressed, and offers to clear focus", () => {
  const { renderer } = mountChips({ focusedSeriesKey: "B" });
  const chip = one(renderer, "data-market-explorer-active-chip", "B");
  assert.equal(chip.props["data-market-explorer-active-chip-focused"], "true");
  assert.equal(one(renderer, "data-market-explorer-active-chip", "A").props["data-market-explorer-active-chip-focused"], "false");
  const focus = one(renderer, "data-market-explorer-active-focus", "B");
  assert.equal(focus.props["aria-pressed"], true);
  assert.equal(focus.props["aria-label"], "Clear focus on Market B");
});

test("chip focus is not hover-only: hidden by default only where a real hover exists, always for touch, and reveals on keyboard focus", () => {
  const source = read("./MarketExplorerActiveMarkets.jsx");
  const start = source.indexOf("data-market-explorer-active-focus=");
  const button = source.slice(start, source.indexOf("</button>", start));
  assert.match(button, /\[@media\(hover:hover\)\]:opacity-0/, "only devices that can hover start hidden");
  assert.match(button, /group-hover:opacity-100/);
  assert.match(button, /group-focus-within:opacity-100/);
  assert.match(button, /focus-visible:opacity-100/);
  assert.doesNotMatch(button, /(^|\s)(desk|tab|sm|md|lg):(hidden|opacity-0)/, "no viewport-width gating of the focus action");
});

test("chip target and visibility semantics stay distinct (aria-pressed on target and visibility, each labelled)", () => {
  const { renderer } = mountChips();
  assert.equal(one(renderer, "data-market-explorer-active-inspect", "A").props["aria-pressed"], true);
  assert.equal(one(renderer, "data-market-explorer-active-inspect", "B").props["aria-pressed"], false);
});

test("exactly ONE workspace-level Clear All exists, red, and it is available at every width", () => {
  const { renderer, calls } = mountChips();
  const buttons = find(renderer, "data-market-explorer-active-clear-all");
  assert.equal(buttons.length, 1);
  assert.match(buttons[0].props.className, /248,113,113/);
  assert.match(buttons[0].props["aria-label"], /Clear All/);
  assert.doesNotMatch(buttons[0].props.className, /(^|\s)(desk|tab):(hidden)/);
  act(() => buttons[0].props.onClick());
  assert.equal(calls.clear, 1);
});

// ---------------------------------------------------------------------------
// CONSTITUENT SWITCHER + PAGING CACHE
// ---------------------------------------------------------------------------
const preparedSeries = (key, extra = {}) => ({
  key, label: `Market ${key}`, shortLabel: key, color: "#a78bfa", available: true, marketType: "set",
  generationId: `gen-${key}`, asset: "cards", group: "card", ...extra,
});
const rowsFor = (key, count = 3) => Array.from({ length: count }, (_, i) => ({
  rank: i + 1, instrumentId: `${key}-${i}`, cardVariantId: `${key}-${i}`, canonicalCardId: `${key}-card-${i}`,
  cardName: `${key} Card ${i}`, setName: `${key} Set`, rarity: "Rare", marketPrice: 10 - i,
}));

function installConstituentFetch({ deferred = {}, mismatch = new Set() } = {}) {
  const calls = [];
  globalThis.fetch = async (url) => {
    const parsed = new URL(url, "http://localhost");
    const marketKey = parsed.searchParams.get("marketKey");
    calls.push({ marketKey, afterRank: parsed.searchParams.get("afterRank"), generationId: parsed.searchParams.get("generationId") });
    if (deferred[marketKey]) await deferred[marketKey].promise;
    if (mismatch.has(marketKey)) return { ok: false, status: 409, json: async () => ({ code: "GENERATION_MISMATCH" }) };
    return { ok: true, status: 200, json: async () => ({ availability: "available", generationId: `gen-${marketKey}`, rows: rowsFor(marketKey), nextCursor: null, totalCount: 3, priceAsOf: "2026-09-19", movementAvailable: false }) };
  };
  return calls;
}

function Harness({ series, initial, cache, onSelect, hidden, focused, onRefresh }) {
  const [target, setTarget] = useState(initial);
  return (
    <MarketExplorerConstituents
      selectedSeries={series}
      activeSeriesId={target}
      onSelectSeries={(key) => { onSelect?.(key); setTarget(key); }}
      pageCache={cache}
      hiddenSeriesKeys={hidden}
      focusedSeriesKey={focused}
      onRefreshPrepared={onRefresh}
    />
  );
}
const mountHarness = async (props) => {
  let renderer;
  await act(async () => { renderer = TestRenderer.create(<Harness {...props} />); });
  await flush();
  return renderer;
};
const shownRows = (renderer) => ids(renderer, "data-market-constituent");
const targetOf = (renderer) => find(renderer, "data-market-constituents-target").find((n) => n.props["aria-pressed"] === true)?.props["data-market-constituents-target"];

test("switcher A/B/C: target A shown, B, C, back to A; the target chip is the only pressed one; A page 1 is NOT refetched", async () => {
  const calls = installConstituentFetch();
  const series = [preparedSeries("A"), preparedSeries("B"), preparedSeries("C")];
  const cache = createConstituentPageCache();
  const selected = [];
  const renderer = await mountHarness({ series, initial: "A", cache, onSelect: (key) => selected.push(key) });
  assert.equal(targetOf(renderer), "A");
  assert.ok(shownRows(renderer).every((id) => id.startsWith("A-")));
  assert.equal(find(renderer, "data-market-constituents-target").filter((n) => n.props["aria-pressed"]).length, 1);

  click(renderer, "data-market-constituents-target", "B"); await flush();
  assert.equal(targetOf(renderer), "B");
  assert.ok(shownRows(renderer).every((id) => id.startsWith("B-")), "no stale rows from A");
  click(renderer, "data-market-constituents-target", "C"); await flush();
  assert.ok(shownRows(renderer).every((id) => id.startsWith("C-")));
  click(renderer, "data-market-constituents-target", "A"); await flush();
  assert.ok(shownRows(renderer).every((id) => id.startsWith("A-")));

  assert.deepEqual(selected, ["B", "C", "A"]);
  assert.equal(calls.filter((call) => call.marketKey === "A").length, 1, "A page 1 fetched once, restored from the cache");
  assert.equal(calls.length, 3, "one fetch per distinct target");
});

test("switcher: a chart-hidden market stays selectable and is labelled; a non-enumerable market is unavailable, not loading", async () => {
  installConstituentFetch();
  const series = [preparedSeries("A"), preparedSeries("B"), { key: "raw", label: "Raw Card Market", isParent: true, color: "#fff", available: true }];
  const renderer = await mountHarness({ series, initial: "A", cache: createConstituentPageCache(), hidden: new Set(["B"]) });
  const b = one(renderer, "data-market-constituents-target", "B");
  assert.equal(b.props["data-market-constituents-target-hidden"], "true");
  assert.equal(b.props.disabled, undefined, "hidden on the chart is still selectable");
  const raw = one(renderer, "data-market-constituents-target-unavailable", "raw");
  assert.equal(raw.props.disabled, true);
  assert.equal(raw.props["aria-disabled"], true);
  assert.equal(find(renderer, "data-market-constituents-target", "raw").length, 0);
  click(renderer, "data-market-constituents-target", "B"); await flush();
  assert.equal(targetOf(renderer), "B");
});

test("switcher is a real touch target below the desktop breakpoint and never removes or hides anything", () => {
  const source = read("./MarketExplorerConstituents.jsx");
  const chip = source.slice(source.indexOf("function ConstituentSwitcher"), source.indexOf("QUERY-BUILT market's constituents"));
  assert.match(chip, /min-h-11/, "44px target on touch widths");
  assert.match(chip, /desk:min-h-0/);
  assert.doesNotMatch(chip, /onRemove|onToggleVisibility|onFocus|onBuild/);
});

test("GENERATION_MISMATCH invalidates only the affected target's cache and asks the loader to refresh that market", async () => {
  installConstituentFetch({ mismatch: new Set(["A"]) });
  const cache = createConstituentPageCache();
  const refreshed = [];
  const series = [preparedSeries("A"), preparedSeries("B")];
  const renderer = await mountHarness({ series, initial: "B", cache, onRefresh: (key) => refreshed.push(key) });
  assert.equal(cache.keys().length, 1);
  click(renderer, "data-market-constituents-target", "A"); await flush();
  assert.deepEqual(refreshed, ["A"]);
  assert.deepEqual(cache.keys(), ["prepared:B:gen-B"], "B's pages survive; A's generation was invalidated");
});

test("a late response for the previous target never overwrites the displayed target", async () => {
  let release;
  const gate = { promise: new Promise((resolve) => { release = resolve; }) };
  installConstituentFetch({ deferred: { A: gate } });
  const series = [preparedSeries("A"), preparedSeries("B")];
  const renderer = await mountHarness({ series, initial: "A", cache: createConstituentPageCache() });
  click(renderer, "data-market-constituents-target", "B"); await flush();
  assert.ok(shownRows(renderer).every((id) => id.startsWith("B-")));
  await flush(async () => release());
  assert.ok(shownRows(renderer).length > 0);
  assert.ok(shownRows(renderer).every((id) => id.startsWith("B-")), "late A page dropped");
});

// ---------------------------------------------------------------------------
// THUMBNAIL: image normalization, new-tab detail link, row isolation
// ---------------------------------------------------------------------------
const mountThumb = (row, asset = "cards") => {
  let renderer;
  act(() => { renderer = TestRenderer.create(<ConstituentThumbnail row={row} asset={asset} />); });
  return renderer;
};

test("thumbnail (card): the SMALL image is a new-tab link with noopener/noreferrer, descriptive label, lazy + fixed size", () => {
  const renderer = mountThumb({ cardName: "Charizard", setName: "Base Set", canonicalCardId: "c1", cardVariantId: "v1", imageSmallUrl: "s.png", imageLargeUrl: "l.png" });
  const link = one(renderer, "data-market-constituent-link");
  assert.equal(link.props.href, "/TCGs/Pokemon/Sets/base-set/Cards/c1?variant=v1");
  assert.equal(link.props.target, "_blank");
  assert.equal(link.props.rel, "noopener noreferrer");
  assert.equal(link.props["aria-label"], "Open Charizard in a new tab");
  const img = one(renderer, "data-market-constituent-thumb");
  assert.equal(img.props.src, "s.png", "row loads the small image, not the large one");
  assert.equal(img.props.loading, "lazy");
  assert.match(img.props.className, /h-10 w-7/);
  assert.match(img.props.className, /object-contain/);
});

test("thumbnail (sealed): stable product route opens in a new tab", () => {
  const renderer = mountThumb({ productName: "Booster Box", sealedProductId: "p-9", imageUrl: "m.png" }, "sealed");
  const link = one(renderer, "data-market-constituent-link");
  assert.equal(link.props.href, "/sealed-products/p-9");
  assert.equal(link.props.target, "_blank");
  assert.equal(link.props.rel, "noopener noreferrer");
});

test("thumbnail: missing identity renders no link; missing image renders a neutral placeholder, not a broken image", () => {
  const renderer = mountThumb({ cardName: "Mystery", setName: "Nowhere" });
  assert.equal(find(renderer, "data-market-constituent-link").length, 0);
  assert.equal(find(renderer, "data-market-constituent-thumb").length, 0);
  assert.equal(find(renderer, "data-market-constituent-image-placeholder").length, 1);
});

test("thumbnail: clicking the image never reaches the parent row", () => {
  let rowClicks = 0;
  let renderer;
  act(() => {
    renderer = TestRenderer.create(
      <div onClick={() => { rowClicks += 1; }} data-row>
        <ConstituentThumbnail row={{ cardName: "X", setName: "S", canonicalCardId: "c", imageSmallUrl: "s.png" }} asset="cards" />
      </div>);
  });
  let stopped = false;
  act(() => one(renderer, "data-market-constituent-link").props.onClick({ stopPropagation() { stopped = true; } }));
  assert.equal(stopped, true);
  assert.equal(rowClicks, 0);
});

test("thumbnail preview: keyboard focus opens a non-modal tooltip preview, blur/Escape close it, and it never takes focus", () => {
  const renderer = mountThumb({ cardName: "Charizard", setName: "Base", canonicalCardId: "c1", marketPrice: 42, rarity: "Rare Holo", imageLargeUrl: "l.png", imageSmallUrl: "s.png" });
  const link = one(renderer, "data-market-constituent-link");
  assert.equal(find(renderer, "data-market-constituent-preview").length, 0);
  // Source-level assertions: react-test-renderer has no DOM for the portal target.
  const source = read("./MarketExplorerConstituentPreview.jsx");
  assert.match(source, /role="tooltip"/);
  assert.match(source, /pointer-events-none fixed/, "fixed + non-interactive: no clipping by table overflow, no focus trap");
  assert.match(source, /createPortal/);
  assert.match(source, /onFocus=/);
  assert.match(source, /onBlur=\{close\}/);
  assert.match(source, /event\.key === "Escape"/);
  assert.match(source, /pointerType === "mouse"/, "hover preview is mouse-only; touch taps go straight to the link");
  assert.doesNotMatch(source, /\.focus\(\)/, "the preview never moves focus");
  assert.equal(link.props.tabIndex, undefined, "the link is naturally focusable, not a custom trap");
});

// ---------------------------------------------------------------------------
// CHART FOCUS: presentation only
// ---------------------------------------------------------------------------
const chartModel = () => ({
  available: true,
  dates: ["2024-01-01", "2024-01-02", "2024-01-03"],
  series: [
    { key: "A", label: "A", color: "#22d3ee", values: [100, 101, 102] },
    { key: "B", label: "B", color: "#f472b6", values: [100, 99, 98] },
    { key: "C", label: "C", color: "#facc15", values: [100, 100.5, 103] },
  ],
});
const mountChart = (props = {}) => {
  let renderer;
  act(() => { renderer = TestRenderer.create(<MarketPerformanceChart model={chartModel()} viewMode="index" timeframe="7D" {...props} />); });
  return renderer;
};

test("chart with no focus renders exactly as before: original colours, no focus attributes", () => {
  const renderer = mountChart();
  const lines = find(renderer, "data-market-performance-series");
  assert.equal(lines.length, 3);
  assert.deepEqual(lines.map((n) => n.props.stroke), ["#22d3ee", "#f472b6", "#facc15"]);
  assert.ok(lines.every((n) => n.props["data-market-performance-focus"] === undefined && n.props.strokeWidth === "2" && n.props.strokeOpacity === undefined));
  assert.equal(find(renderer, "data-market-performance-focused").length, 0);
});

test("chart focus: focused line keeps colour and emphasis; others are grayscale, more transparent, and still drawn", () => {
  const renderer = mountChart({ focusedSeriesKey: "B" });
  const line = (key) => one(renderer, "data-market-performance-series", key);
  assert.equal(line("B").props.stroke, "#f472b6");
  assert.equal(line("B").props.strokeWidth, "3");
  assert.equal(line("B").props.strokeOpacity, undefined);
  assert.equal(line("B").props["data-market-performance-focus"], "focused");
  for (const key of ["A", "C"]) {
    assert.equal(line(key).props["data-market-performance-focus"], "dimmed");
    const [, r, g, b] = line(key).props.stroke.match(/^rgb\((\d+),(\d+),(\d+)\)$/);
    assert.ok(r === g && g === b, `${key} is grayscale`);
    assert.ok(line(key).props.strokeOpacity < 1);
  }
  assert.equal(find(renderer, "data-market-performance-series").length, 3, "nobody is removed from the chart");
  assert.equal(one(renderer, "data-market-performance-focused").props["data-market-performance-focused"], "B");
});

test("chart focus is presentational: grid, axes and reference line are untouched; the focused line paints last", () => {
  const baseline = mountChart();
  const focused = mountChart({ focusedSeriesKey: "A" });
  assert.equal(find(focused, "data-market-performance-grid").length, find(baseline, "data-market-performance-grid").length);
  assert.equal(find(focused, "data-market-performance-reference").length, find(baseline, "data-market-performance-reference").length);
  const order = find(focused, "data-market-performance-series").map((n) => n.props["data-market-performance-series"]);
  assert.equal(order[order.length - 1], "A");
  const domain = (r) => one(r, "data-market-performance-domain-min").props["data-market-performance-domain-min"];
  assert.equal(domain(focused), domain(baseline), "no data or scale change");
});

test("a focus key that is not drawn is ignored (comparison mode)", () => {
  const renderer = mountChart({ focusedSeriesKey: "ghost" });
  assert.equal(find(renderer, "data-market-performance-focus").length, 0);
});

// ---------------------------------------------------------------------------
// CLIENT: open / close / reopen, target, focus, hide, Clear All
// ---------------------------------------------------------------------------
const change = (percent) => ({ available: true, percent, startDate: "2024-01-01", endDate: "2024-01-05", coverage: "full" });
const changeSet = (percent) => ({ "1D": change(percent), "7D": change(percent), "30D": change(percent), "3M": change(percent), "6M": change(percent), "1Y": change(percent), SinceTracking: change(percent) });
const trend = (...values) => values.map((value, index) => [`2024-01-0${index + 1}`, value]);
const WINDOW = { targetStartDate: "2024-01-01", displayStartDate: "2024-01-01", displayEndDate: "2024-01-05", available: true };
const overview = resolveMarketOverview({ marketOverview: {
  marketDate: "2024-01-05",
  comparisonWindows: Object.fromEntries(["1D", "7D", "30D", "3M", "6M", "1Y", "SinceTracking"].map((k) => [k, WINDOW])),
  coverage: { eligibleSetCount: 3, rawCardCount: 512, chaseCardCount: 30 },
  raw: { basketValue: 8123.45, indexValue: 102.25, historyStartDate: "2024-01-01", trend: trend(100, 101, 99.5, 101.75, 102.25), basketChanges: changeSet(1), changes: changeSet(1), familyChanges: changeSet(1) },
  sealedMarket: { basketValue: 15550.25, indexValue: 106.18, historyStartDate: "2024-01-01", trend: trend(100, 103, 104, 105.5, 106.18), basketChanges: changeSet(1), changes: changeSet(1), familyChanges: changeSet(1) },
} });

const DIRECTORY = [
  { market_key: "era:wotc", market_type: "era", era_id: "wotc", label: "WotC", asset: "cards" },
  { market_key: "set:fossil", market_type: "set", parent_era_id: "wotc", label: "Fossil", asset: "cards" },
];

function installClientFetch() {
  const calls = [];
  globalThis.fetch = async (url, init = {}) => {
    const parsed = new URL(url, "http://localhost");
    const body = init.body ? JSON.parse(init.body) : null;
    calls.push({ path: parsed.pathname, method: init.method || "GET", marketKey: parsed.searchParams.get("marketKey"), body });
    const json = (payload) => ({ ok: true, status: 200, headers: { get: () => null }, json: async () => payload });
    if (parsed.pathname === "/api/market/explorer/prepared" && parsed.searchParams.get("kind") === "constituents") {
      return json({ availability: "available", generationId: "g1", rows: rowsFor("fossil"), nextCursor: null, totalCount: 3, priceAsOf: "2024-01-05" });
    }
    if (parsed.pathname === "/api/market/explorer/prepared") {
      return json({
        markets: [{ market_key: "set:fossil", label: "Fossil", asset: "cards", market_type: "set", generation_id: "g1", comparison_as_of: "2024-01-05", comparison_value: 100, comparison_index_value: 100, history_available: true, window_movements: {} }],
        history: [1, 2, 3, 4, 5].map((day) => ({ market_key: "set:fossil", market_date: `2024-01-0${day}`, index_value: 100 + day })),
      });
    }
    if (parsed.pathname === "/api/market/explorer/query/constituents") {
      return json({ items: rowsFor("query"), next_cursor: null, total_constituent_count: 3, as_of: "2024-01-05" });
    }
    if (parsed.pathname === "/api/market/explorer/query") {
      return json({ queryFingerprint: "qfp", queryKey: "qkey", displayLabel: "Custom Q", indexValue: 100, trackedValue: 1, historyStartDate: "2024-01-01", trend: trend(100, 101, 102, 103, 104), spec: { asset: "cards", mode: "all" }, scope: { resolvedSetCount: 1 }, reconciliation: { eligibleUniverseCount: 3 } });
    }
    return { ok: false, status: 404, headers: { get: () => null }, json: async () => ({}) };
  };
  return calls;
}

async function mountClient() {
  let renderer;
  const initialState = resolveInitialExplorerState(overview, { market: "raw,sealedMarket" }, [], []);
  await act(async () => {
    renderer = TestRenderer.create(React.createElement(MarketExplorerClient, {
      overview, sealedSegments: [], cardSegments: [], initialState,
      user: { id: "u", index_plan: "premium" }, preparedDirectory: DIRECTORY,
    }), { createNodeMock: () => ({ focus() {}, showModal() {}, close() {}, querySelector: () => null, querySelectorAll: () => [], matches: () => true, getBoundingClientRect: () => ({ left: 0, top: 0, right: 10, bottom: 10, width: 10, height: 10 }) }) });
  });
  await flush();
  return renderer;
}
async function addFossil(renderer) {
  click(renderer, "data-market-directory-category", "sets"); await flush();
  click(renderer, "data-compare-market", "set:fossil"); await flush();
}
async function addQuery(renderer) {
  // The Builder dialog opens on Cards & Products; Custom Filters owns the plain Build button.
  const tab = renderer.root.findAll((node) => node.props?.role === "tab" && JSON.stringify(node.children).includes("Custom Filters"))[0];
  act(() => tab.props.onClick()); await flush();
  const build = one(renderer, "data-market-builder-build");
  assert.equal(build.props.disabled, false, "Build Market is enabled for the default filter set");
  click(renderer, "data-market-builder-build", undefined); await flush();
}
const chipKeys = (renderer) => ids(renderer, "data-market-explorer-active-chip");
const workspaceAttr = (renderer, name) => one(renderer, "data-market-explorer-workspace").props[name];
const detailTarget = (renderer) => workspaceAttr(renderer, "data-market-explorer-detail-series");
const isOpen = (renderer) => find(renderer, "data-market-explorer-compare-results").length > 0;
const drawn = (renderer) => ids(renderer, "data-market-performance-series");

test("workspace: trigger renders while markets are active; open shows a centred top Hide control; close/reopen preserve markets, chart, target and loader state", async () => {
  const calls = installClientFetch();
  const renderer = await mountClient();
  await addFossil(renderer);
  await addQuery(renderer);
  const chips = chipKeys(renderer);
  assert.ok(chips.includes("set:fossil"));
  const queryKey = chips.find((key) => key !== "set:fossil" && key !== "raw" && key !== "sealedMarket");
  assert.ok(queryKey, "the query-built market is active");

  const trigger = one(renderer, "data-market-explorer-view-details");
  assert.equal(trigger.props["aria-expanded"], false);
  assert.match(trigger.props.className, /violet/);
  assert.equal(isOpen(renderer), false);

  act(() => trigger.props.onClick()); await flush();
  assert.equal(isOpen(renderer), true);
  const hide = one(renderer, "data-market-explorer-hide-details");
  assert.equal(hide.props["aria-expanded"], true);
  assert.match(hide.props.className, /violet/);
  // Centred at the TOP edge: the button is the first child of a column-centred header.
  const header = hide.parent;
  assert.match(header.props.className, /flex-col items-center/);
  assert.equal(header.children[0], hide, "Hide is the first (top) element of the expanded workspace");

  // Choose the query market as the target, then close.
  click(renderer, "data-market-constituents-target", queryKey); await flush();
  assert.equal(detailTarget(renderer), queryKey);
  const drawnBefore = drawn(renderer);
  act(() => hide.props.onClick()); await flush();
  assert.equal(isOpen(renderer), false);
  assert.deepEqual(chipKeys(renderer), chips, "closing removes no active market");
  assert.deepEqual(drawn(renderer), drawnBefore, "closing hides no chart line");
  assert.equal(detailTarget(renderer), queryKey, "the target is remembered while closed");
  assert.equal(find(renderer, "data-market-explorer-prepared-pending").length, 0);
  assert.equal(calls.filter((c) => c.path === "/api/market/explorer/query" && c.method === "POST").length, 1, "no query market was rebuilt");

  // Reopen restores the last valid target.
  act(() => one(renderer, "data-market-explorer-view-details").props.onClick()); await flush();
  assert.equal(isOpen(renderer), true);
  assert.equal(detailTarget(renderer), queryKey);
  assert.equal(one(renderer, "data-market-constituents-target", queryKey).props["aria-pressed"], true);
});

test("workspace: switching the constituent target changes ONLY the target and reuses the cached page", async () => {
  const calls = installClientFetch();
  const renderer = await mountClient();
  await addFossil(renderer); await addQuery(renderer);
  const queryKey = chipKeys(renderer).find((key) => !["set:fossil", "raw", "sealedMarket"].includes(key));
  act(() => one(renderer, "data-market-explorer-view-details").props.onClick()); await flush();
  const before = { chips: chipKeys(renderer), drawn: drawn(renderer), focus: find(renderer, "data-market-explorer-focus-strip").length };
  const fossilFetches = () => calls.filter((c) => c.marketKey === "set:fossil" && c.path === "/api/market/explorer/prepared" && c.method === "GET").length;
  const start = detailTarget(renderer);
  const other = start === "set:fossil" ? queryKey : "set:fossil";
  click(renderer, "data-market-constituents-target", other); await flush();
  click(renderer, "data-market-constituents-target", start); await flush();
  click(renderer, "data-market-constituents-target", other); await flush();
  assert.deepEqual(chipKeys(renderer), before.chips);
  assert.deepEqual(drawn(renderer), before.drawn, "visibility untouched");
  assert.equal(find(renderer, "data-market-explorer-focus-strip").length, before.focus, "focus untouched");
  assert.ok(fossilFetches() <= 1, "the prepared roster is fetched at most once across target switches");
  assert.equal(calls.filter((c) => c.path === "/api/market/explorer/query" && c.method === "POST").length, 1, "no rebuild");
  // Non-enumerable parents are shown unavailable, never selectable.
  assert.equal(find(renderer, "data-market-constituents-target", "raw").length, 0);
  assert.equal(one(renderer, "data-market-constituents-target-unavailable", "raw").props.disabled, true);
});

test("workspace: removing a non-target keeps the target; removing the target falls back deterministically; no enumerable market leaves no stale key", async () => {
  installClientFetch();
  const renderer = await mountClient();
  await addFossil(renderer); await addQuery(renderer);
  const queryKey = chipKeys(renderer).find((key) => !["set:fossil", "raw", "sealedMarket"].includes(key));
  act(() => one(renderer, "data-market-explorer-view-details").props.onClick()); await flush();
  click(renderer, "data-market-constituents-target", "set:fossil"); await flush();
  assert.equal(detailTarget(renderer), "set:fossil");
  click(renderer, "data-market-explorer-active-remove", "raw"); await flush();
  assert.equal(detailTarget(renderer), "set:fossil", "non-target removal leaves the target alone");
  click(renderer, "data-market-explorer-active-remove", "set:fossil"); await flush();
  assert.equal(chipKeys(renderer).includes("set:fossil"), false);
  assert.equal(detailTarget(renderer), queryKey, "target removal falls back to the first remaining enumerable market");
  click(renderer, "data-market-explorer-active-remove", queryKey); await flush();
  assert.deepEqual(chipKeys(renderer), ["sealedMarket"]);
  assert.equal(detailTarget(renderer), "", "no stale target key once nothing is enumerable");
  assert.equal(one(renderer, "data-market-explorer-active-chip", "sealedMarket") !== undefined, true);
});

test("workspace: Clear All with nothing enumerable left closes the panel and drops the trigger (no crash)", async () => {
  installClientFetch();
  const renderer = await mountClient();
  act(() => one(renderer, "data-market-explorer-view-details").props.onClick()); await flush();
  assert.equal(isOpen(renderer), true);
  click(renderer, "data-market-explorer-active-clear-all", undefined); await flush();
  assert.equal(isOpen(renderer), false);
  assert.equal(find(renderer, "data-market-explorer-view-details").length, 0);
  assert.equal(detailTarget(renderer), "");
});

test("focus: focusing B dims the others on the chart without removing, retargeting or hiding; clear focus restores", async () => {
  installClientFetch();
  const renderer = await mountClient();
  await addFossil(renderer);
  act(() => one(renderer, "data-market-explorer-view-details").props.onClick()); await flush();
  const targetBefore = detailTarget(renderer);
  act(() => one(renderer, "data-market-explorer-hide-details").props.onClick()); await flush();
  const chips = chipKeys(renderer);
  const lines = drawn(renderer);
  assert.ok(lines.length >= 2);
  const focusKey = lines[lines.length - 1];

  click(renderer, "data-market-explorer-active-focus", focusKey); await flush();
  assert.equal(one(renderer, "data-market-explorer-active-chip", focusKey).props["data-market-explorer-active-chip-focused"], "true");
  assert.match(JSON.stringify(one(renderer, "data-market-explorer-focus-label").children), new RegExp("Focused"));
  assert.equal(one(renderer, "data-market-performance-series", focusKey).props["data-market-performance-focus"], "focused");
  for (const key of lines.filter((k) => k !== focusKey)) {
    assert.equal(one(renderer, "data-market-performance-series", key).props["data-market-performance-focus"], "dimmed");
  }
  assert.deepEqual(chipKeys(renderer), chips, "no market removed");
  assert.deepEqual(drawn(renderer).sort(), [...lines].sort(), "others stay visible");
  assert.equal(workspaceAttr(renderer, "data-market-explorer-detail-series"), targetBefore, "focus never retargets constituents");

  // Focusing the same market again clears focus; so does the explicit control.
  click(renderer, "data-market-explorer-active-focus", focusKey); await flush();
  assert.equal(find(renderer, "data-market-explorer-focus-strip").length, 0);
  click(renderer, "data-market-explorer-active-focus", focusKey); await flush();
  assert.equal(find(renderer, "data-market-explorer-focus-strip").length, 1);
  click(renderer, "data-market-explorer-clear-focus", undefined); await flush();
  assert.equal(find(renderer, "data-market-explorer-focus-strip").length, 0);
  assert.equal(find(renderer, "data-market-performance-focus").length, 0);
});

test("focus rules in the workspace: focusing a hidden market unhides it; hiding the focused market clears focus; removing it clears focus", async () => {
  installClientFetch();
  const renderer = await mountClient();
  click(renderer, "data-market-explorer-active-visibility", "sealedMarket"); await flush();
  assert.equal(one(renderer, "data-market-explorer-active-chip", "sealedMarket").props["data-market-explorer-active-chip-hidden"], "true");
  click(renderer, "data-market-explorer-active-focus", "sealedMarket"); await flush();
  assert.equal(one(renderer, "data-market-explorer-active-chip", "sealedMarket").props["data-market-explorer-active-chip-hidden"], "false", "unhidden by focus");
  assert.equal(one(renderer, "data-market-explorer-active-chip", "sealedMarket").props["data-market-explorer-active-chip-focused"], "true");
  click(renderer, "data-market-explorer-active-visibility", "sealedMarket"); await flush();
  assert.equal(find(renderer, "data-market-explorer-focus-strip").length, 0, "hiding the focused market clears focus");
  click(renderer, "data-market-explorer-active-focus", "raw"); await flush();
  assert.equal(find(renderer, "data-market-explorer-focus-strip").length, 1);
  click(renderer, "data-market-explorer-active-remove", "raw"); await flush();
  assert.equal(find(renderer, "data-market-explorer-focus-strip").length, 0, "removing the focused market clears focus");
});

test("Clear All: one control; removes prepared + query + hidden + focused markets, focus, bookkeeping and the open panel; keeps the Builder draft", async () => {
  installClientFetch();
  const renderer = await mountClient();
  await addFossil(renderer); await addQuery(renderer);
  const draftBefore = one(renderer, "data-market-builder-preview")?.props["data-market-builder-preview"];
  click(renderer, "data-market-explorer-active-visibility", "raw"); await flush();
  click(renderer, "data-market-explorer-active-focus", "set:fossil"); await flush();
  act(() => one(renderer, "data-market-explorer-view-details").props.onClick()); await flush();
  assert.equal(isOpen(renderer), true);
  assert.equal(find(renderer, "data-market-explorer-active-clear-all").length, 1, "exactly one workspace-level Clear All");
  assert.equal(find(renderer, "data-market-explorer-clear-graph").length, 0, "the competing Clear Graph is gone");

  click(renderer, "data-market-explorer-active-clear-all", undefined); await flush();
  assert.deepEqual(chipKeys(renderer), []);
  assert.equal(find(renderer, "data-market-explorer-focus-strip").length, 0);
  assert.equal(find(renderer, "data-market-explorer-focus-label").length, 0);
  assert.equal(isOpen(renderer), false);
  assert.equal(detailTarget(renderer), "");
  assert.equal(workspaceAttr(renderer, "data-market-explorer-series"), "");
  assert.equal(find(renderer, "data-market-explorer-constituents").length, 0, "constituents no longer shown");
  assert.equal(one(renderer, "data-market-builder-preview")?.props["data-market-builder-preview"], draftBefore, "Builder draft survives");
  assert.equal(find(renderer, "data-market-explorer-active-clear-all").length, 0, "nothing left to clear");
  // Browse context (its own state) is intact: the Sets popover we opened is still open.
  assert.equal(find(renderer, "data-market-directory-popover").length, 1, "asset Browse context survives");
});

test("mobile + accessibility contracts: the controls that matter are present without hover or desktop-only breakpoints", () => {
  const client = read("./MarketExplorerClient.jsx");
  const chart = read("./MarketExplorerChart.jsx");
  const active = read("./MarketExplorerActiveMarkets.jsx");
  // Open / Hide constituents: real buttons, no breakpoint gating, aria-expanded.
  assert.match(chart, /data-market-explorer-view-details\n\s+aria-expanded=\{detailsOpen\}/);
  const hide = client.slice(client.indexOf("data-market-explorer-hide-details"), client.indexOf("Hide Constituents &amp; Comparison"));
  assert.match(hide, /aria-expanded=\{true\}/);
  assert.doesNotMatch(hide + chart.slice(chart.indexOf("data-market-explorer-view-details"), chart.indexOf("View Constituents")), /\b(desk|tab):hidden|max-desk:hidden/);
  // Clear All has no width gating; chip strip scrolls horizontally on narrow screens.
  assert.doesNotMatch(active.slice(active.indexOf("active-clear-all")), /^[^>]*\b(desk|tab|sm):hidden/);
  assert.match(active, /data-market-explorer-active-chip-scroll className="min-w-0 overflow-x-auto"/);
  // Focus control strip: Clear Focus is a 32px+ target and wraps on narrow widths.
  assert.match(chart, /flex flex-wrap items-center/);
  assert.match(chart, /data-market-explorer-clear-focus[\s\S]*min-h-8/);
  // Architectural seam for future analytical tools; nothing named/exposed today.
  assert.match(chart, /focusTools = \[\]/);
  assert.doesNotMatch(chart + client + active, /Demand Pressure|Fair Value/);
  // No plan-quota conditionals were introduced in the workspace state.
  assert.doesNotMatch(client, /plan\s*===\s*["'](plus|premium)["']\s*&&\s*\w*\.length/);
});
