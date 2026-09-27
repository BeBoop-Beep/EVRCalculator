import test from "node:test";
import assert from "node:assert/strict";
import {
  WORKSPACE_VIEW_ACTIONS as A,
  buildConstituentSwitcherEntries,
  constituentPageCacheKey,
  createConstituentPageCache,
  createWorkspaceViewState,
  reduceWorkspaceView,
} from "./marketExplorerWorkspace.mjs";
import { resolveActiveDetailSeriesId } from "./marketExplorerConstituents.mjs";

const run = (state, ...actions) => actions.reduce((current, action) => reduceWorkspaceView(current, action), state);
const fresh = () => createWorkspaceViewState();

test("focus: focusing B sets focus only; nothing is hidden or removed", () => {
  const state = run(fresh(), { type: A.focus, key: "B" });
  assert.equal(state.focused, "B");
  assert.equal(state.hidden.size, 0);
});

test("focus: focusing C moves focus; focusing the focused market clears it; clear focus is idempotent", () => {
  let state = run(fresh(), { type: A.focus, key: "B" }, { type: A.focus, key: "C" });
  assert.equal(state.focused, "C");
  state = run(state, { type: A.focus, key: "C" });
  assert.equal(state.focused, null);
  state = run(state, { type: A.focus, key: "A" }, { type: A.clearFocus });
  assert.equal(state.focused, null);
  const same = run(state, { type: A.clearFocus });
  assert.equal(same, state, "no-op returns the same state object");
});

test("focus: focusing a HIDDEN market automatically UNHIDES it", () => {
  const hidden = run(fresh(), { type: A.toggleVisibility, key: "B" }, { type: A.toggleVisibility, key: "C" });
  const state = run(hidden, { type: A.focus, key: "B" });
  assert.equal(state.focused, "B");
  assert.equal(state.hidden.has("B"), false, "B was unhidden");
  assert.equal(state.hidden.has("C"), true, "other hidden markets stay hidden");
});

test("focus: explicitly hiding the focused market CLEARS focus; hiding another does not", () => {
  const focused = run(fresh(), { type: A.focus, key: "B" });
  const hideOther = run(focused, { type: A.toggleVisibility, key: "A" });
  assert.equal(hideOther.focused, "B");
  const hideFocused = run(focused, { type: A.toggleVisibility, key: "B" });
  assert.equal(hideFocused.focused, null);
  assert.equal(hideFocused.hidden.has("B"), true);
  const hideAll = run(focused, { type: A.hideAll, keys: ["A", "B", "C"] });
  assert.equal(hideAll.focused, null);
});

test("focus: showing all leaves focus alone; reconcile drops focus and bookkeeping for removed markets", () => {
  const state = run(fresh(), { type: A.toggleVisibility, key: "A" }, { type: A.focus, key: "B" });
  assert.equal(run(state, { type: A.showAll }).focused, "B");
  const removedB = run(state, { type: A.reconcile, activeKeys: ["A", "C"] });
  assert.equal(removedB.focused, null);
  assert.equal(removedB.hidden.has("A"), true);
  const removedA = run(state, { type: A.reconcile, activeKeys: ["B", "C"] });
  assert.equal(removedA.focused, "B");
  assert.equal(removedA.hidden.size, 0);
  const unchanged = run(state, { type: A.reconcile, activeKeys: ["A", "B", "C"] });
  assert.equal(unchanged, state);
});

test("reset (Clear All) clears visibility bookkeeping and focus together", () => {
  const state = run(fresh(), { type: A.toggleVisibility, key: "A" }, { type: A.focus, key: "B" }, { type: A.reset });
  assert.equal(state.focused, null);
  assert.equal(state.hidden.size, 0);
});

const fixture = (key, extra = {}) => ({ key, label: key, shortLabel: key, color: "#fff", available: true, ...extra });

test("switcher: every active market listed; target is the strongest state; hidden stays selectable; non-enumerable is disabled", () => {
  const series = [fixture("A"), fixture("B"), fixture("C"), fixture("raw", { isParent: true })];
  const entries = buildConstituentSwitcherEntries(series, { targetKey: "A", hiddenKeys: new Set(["B"]), focusedKey: "C" });
  assert.deepEqual(entries.map((entry) => entry.key), ["A", "B", "C", "raw"]);
  assert.equal(entries.find((entry) => entry.key === "A").isTarget, true);
  assert.equal(entries.filter((entry) => entry.isTarget).length, 1, "exactly one target");
  const b = entries.find((entry) => entry.key === "B");
  assert.equal(b.isHidden, true);
  assert.equal(b.disabled, false, "a chart-hidden market stays selectable");
  assert.equal(entries.find((entry) => entry.key === "C").isFocused, true);
  assert.equal(entries.find((entry) => entry.key === "raw").disabled, true);
});

test("target resolution: non-target removal keeps it; target removal falls back deterministically; last removal yields null", () => {
  const abc = [fixture("A"), fixture("B"), fixture("C")];
  assert.equal(resolveActiveDetailSeriesId(abc, "B"), "B");
  assert.equal(resolveActiveDetailSeriesId([fixture("A"), fixture("B")], "B"), "B", "removing non-target C keeps B");
  assert.equal(resolveActiveDetailSeriesId([fixture("A"), fixture("C")], "B"), "A", "removing target B falls back to first enumerable");
  assert.equal(resolveActiveDetailSeriesId([], "B"), null, "no markets: no stale key");
  assert.equal(resolveActiveDetailSeriesId([fixture("raw", { isParent: true }), fixture("B")], null), "B", "parents cannot be the target");
});

test("page cache: keyed by generationId + marketKey; a new generation is a different key; evict/clear work", () => {
  const g1 = constituentPageCacheKey({ marketKey: "set:fossil", generationId: "g1" });
  const g2 = constituentPageCacheKey({ marketKey: "set:fossil", generationId: "g2" });
  assert.notEqual(g1, g2);
  const cache = createConstituentPageCache();
  cache.set(g1, { rows: [1] }); cache.set(g2, { rows: [2] });
  cache.set(constituentPageCacheKey({ marketKey: "set:base", generationId: "g1" }), { rows: [3] });
  cache.delete(g1);
  assert.equal(cache.get(g1), undefined);
  assert.deepEqual(cache.get(g2), { rows: [2] }, "only the affected generation was invalidated");
  cache.evictMarket("set:fossil");
  assert.equal(cache.size, 1);
  cache.clear();
  assert.equal(cache.size, 0);
  assert.equal(constituentPageCacheKey(null), null);
});
